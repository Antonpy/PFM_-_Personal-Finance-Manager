import tempfile
import unittest
from pathlib import Path

import pandas as pd

from anomaly import (
    AnomalyThresholds,
    build_user_stats,
    detect_anomalies,
    load_anomaly_feedback,
    save_anomaly_feedback,
    summarize_feedback,
)


class TestAnomalyDetection(unittest.TestCase):
    def _build_df(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "transaction_id": "1",
                    "date": "2026-03-01T10:00:00Z",
                    "amount": -10000,
                    "currency": "RUB",
                    "merchant": "Пятёрочка",
                    "description": "Продукты",
                    "country": "RU",
                },
                {
                    "transaction_id": "2",
                    "date": "2026-03-01T20:00:00Z",
                    "amount": -12000,
                    "currency": "RUB",
                    "merchant": "Пятёрочка",
                    "description": "Продукты",
                    "country": "RU",
                },
                {
                    "transaction_id": "3",
                    "date": "2026-03-02T08:00:00Z",
                    "amount": -90000,
                    "currency": "RUB",
                    "merchant": "Unknown Store",
                    "description": "Large purchase",
                    "country": "US",
                },
                {
                    "transaction_id": "4",
                    "date": "2026-03-04T08:00:00Z",
                    "amount": 1500000,
                    "currency": "RUB",
                    "merchant": "Employer",
                    "description": "Salary",
                    "country": "RU",
                },
            ]
        )

    def test_build_user_stats(self):
        df = self._build_df()

        stats = build_user_stats(df)

        self.assertEqual(stats.expense_transactions, 3)
        # (10000 + 12000 + 90000) / 3 = 37333.33 -> 37333
        self.assertEqual(stats.avg_expense_minor, 37333)
        self.assertGreater(stats.merchant_expense_ratio.get("Unknown Store", 0), 0)

    def test_detect_anomalies_flags_meaningful_rows(self):
        df = self._build_df()
        thresholds = AnomalyThresholds(
            high_amount_multiplier=2,
            rare_merchant_max_ratio=0.10,
            rare_merchant_max_tx_count=1,
            country_switch_max_gap_hours=24,
        )

        result = detect_anomalies(df, thresholds=thresholds)
        flagged = result.dataframe[result.dataframe["is_anomaly"]]

        self.assertFalse(flagged.empty)
        row_3 = flagged[flagged["transaction_id"] == "3"].iloc[0]

        self.assertTrue(bool(row_3["anomaly_high_amount"]))
        self.assertTrue(bool(row_3["anomaly_rare_merchant"]))
        self.assertTrue(bool(row_3["anomaly_country_switch"]))
        self.assertIn("high_amount", str(row_3["anomaly_reasons"]))
        self.assertIn("rare_merchant", str(row_3["anomaly_reasons"]))
        self.assertIn("country_switch", str(row_3["anomaly_reasons"]))
        self.assertGreaterEqual(int(row_3["anomaly_score"]), 3)

        self.assertGreaterEqual(result.metadata["anomaly_rows"], 1)
        self.assertGreaterEqual(result.metadata["high_amount_rows"], 1)
        self.assertGreaterEqual(result.metadata["rare_merchant_rows"], 1)
        self.assertGreaterEqual(result.metadata["country_switch_rows"], 1)

    def test_feedback_persistence_and_summary(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            feedback_path = Path(tmp_dir) / "anomaly_feedback.json"

            saved_fraud = save_anomaly_feedback(
                transaction_id="tx-100",
                verdict="fraud",
                feedback_path=feedback_path,
                reasons=["high_amount", "country_switch"],
                comment="Подтверждено пользователем",
                context={"currency": "RUB", "amount_minor": -90000},
            )
            self.assertTrue(saved_fraud)

            saved_ok = save_anomaly_feedback(
                transaction_id="tx-101",
                verdict="ok",
                feedback_path=feedback_path,
                reasons=["rare_merchant"],
                comment="Легитимная покупка",
                context={"currency": "USD", "amount_minor": -12000},
            )
            self.assertTrue(saved_ok)

            # Проверяем upsert по transaction_id
            saved_fraud_update = save_anomaly_feedback(
                transaction_id="tx-100",
                verdict="fraud",
                feedback_path=feedback_path,
                reasons=["high_amount"],
                comment="Обновлённый комментарий",
            )
            self.assertTrue(saved_fraud_update)

            loaded = load_anomaly_feedback(feedback_path)
            self.assertEqual(len(loaded), 2)

            fraud_entries = [entry for entry in loaded if entry.get("transaction_id") == "tx-100"]
            self.assertEqual(len(fraud_entries), 1)
            self.assertEqual(fraud_entries[0].get("comment"), "Обновлённый комментарий")

            summary = summarize_feedback(loaded)
            self.assertEqual(summary["total_feedback"], 2)
            self.assertEqual(summary["fraud_count"], 1)
            self.assertEqual(summary["ok_count"], 1)

            scoped_summary = summarize_feedback(loaded, transaction_ids={"tx-100"})
            self.assertEqual(scoped_summary["total_feedback"], 1)
            self.assertEqual(scoped_summary["fraud_count"], 1)
            self.assertEqual(scoped_summary["ok_count"], 0)


if __name__ == "__main__":
    unittest.main()

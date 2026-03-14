from __future__ import annotations

import io
import unittest
from pathlib import Path

from categorizer import categorize_transactions
from io_utils import import_transactions


class TestE2EBankStatements(unittest.TestCase):
    """E2E-проверки импорта и категоризации по образцам банковских выписок."""

    FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

    def _load_fixture_upload(self, fixture_name: str):
        fixture_path = self.FIXTURES_DIR / fixture_name
        payload = fixture_path.read_bytes()

        uploaded = io.BytesIO(payload)
        uploaded.name = fixture_name
        return uploaded

    def _assert_transaction_category(self, dataframe, merchant: str, expected_category: str):
        matches = dataframe[dataframe["merchant"].str.contains(merchant, case=False, na=False)]
        self.assertFalse(matches.empty, msg=f"Транзакция с merchant='{merchant}' не найдена")

        actual_category = str(matches.iloc[0]["category"])
        self.assertEqual(actual_category, expected_category)

    def test_sber_fixture_end_to_end(self):
        upload = self._load_fixture_upload("sber_statement.csv")

        import_result = import_transactions(upload)
        self.assertEqual(import_result.errors, [])
        self.assertIsNotNone(import_result.dataframe)

        dataframe = import_result.dataframe
        self.assertEqual(int(dataframe.shape[0]), 3)

        categorized, metadata = categorize_transactions(dataframe)

        self._assert_transaction_category(categorized, "Пят", "groceries")
        self._assert_transaction_category(categorized, "Яндекс Go", "taxi")
        self._assert_transaction_category(categorized, "Тинькофф", "salary")
        self.assertGreaterEqual(float(metadata["coverage_ratio"]), 1.0)

    def test_tinkoff_fixture_end_to_end(self):
        upload = self._load_fixture_upload("tinkoff_statement.csv")

        import_result = import_transactions(upload)
        self.assertEqual(import_result.errors, [])
        self.assertIsNotNone(import_result.dataframe)

        dataframe = import_result.dataframe
        self.assertEqual(int(dataframe.shape[0]), 3)

        categorized, metadata = categorize_transactions(dataframe)

        self._assert_transaction_category(categorized, "Яндекс Go", "taxi")
        self._assert_transaction_category(categorized, "Ozon", "shopping")
        self._assert_transaction_category(categorized, "Tinkoff", "salary")
        self.assertGreaterEqual(float(metadata["coverage_ratio"]), 1.0)

    def test_alfa_fixture_end_to_end(self):
        upload = self._load_fixture_upload("alfa_statement.csv")

        import_result = import_transactions(upload)
        self.assertEqual(import_result.errors, [])
        self.assertIsNotNone(import_result.dataframe)

        dataframe = import_result.dataframe
        self.assertEqual(int(dataframe.shape[0]), 3)

        amounts = dataframe["amount"].astype("Int64").tolist()
        self.assertEqual(amounts, [-2350, -450, 120000])
        self.assertEqual(import_result.metadata.get("amount_mode_interpreted"), "minor")

        categorized, metadata = categorize_transactions(dataframe)

        self._assert_transaction_category(categorized, "Magnit", "groceries")
        self._assert_transaction_category(categorized, "Лукойл", "fuel")
        self._assert_transaction_category(categorized, "Employer", "salary")
        self.assertGreaterEqual(float(metadata["coverage_ratio"]), 1.0)


if __name__ == "__main__":
    unittest.main()

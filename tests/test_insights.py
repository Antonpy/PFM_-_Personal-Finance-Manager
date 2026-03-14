import unittest

import pandas as pd

from insights import generate_financial_insights


class TestInsights(unittest.TestCase):
    def _build_df(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "transaction_id": "1",
                    "date": "2026-01-10",
                    "amount": -99000,
                    "currency": "RUB",
                    "merchant": "Netflix",
                    "description": "Subscription",
                    "category": "subscriptions",
                },
                {
                    "transaction_id": "2",
                    "date": "2026-02-10",
                    "amount": -99000,
                    "currency": "RUB",
                    "merchant": "Netflix",
                    "description": "Subscription",
                    "category": "subscriptions",
                },
                {
                    "transaction_id": "3",
                    "date": "2026-03-10",
                    "amount": -99000,
                    "currency": "RUB",
                    "merchant": "Netflix",
                    "description": "Subscription",
                    "category": "subscriptions",
                },
                {
                    "transaction_id": "4",
                    "date": "2026-02-05",
                    "amount": -10000,
                    "currency": "RUB",
                    "merchant": "Yandex Go",
                    "description": "Taxi",
                    "category": "taxi",
                },
                {
                    "transaction_id": "5",
                    "date": "2026-03-05",
                    "amount": -18000,
                    "currency": "RUB",
                    "merchant": "Yandex Go",
                    "description": "Taxi",
                    "category": "taxi",
                },
                {
                    "transaction_id": "6",
                    "date": "2026-03-20",
                    "amount": 1500000,
                    "currency": "RUB",
                    "merchant": "Employer",
                    "description": "Salary",
                    "category": "salary",
                },
            ]
        )

    def test_generate_financial_insights_returns_actionable_entries(self):
        df = self._build_df()

        result = generate_financial_insights(df, amount_column="amount", currency="RUB")

        self.assertGreaterEqual(result.metadata.get("total_insights", 0), 3)
        self.assertGreater(result.total_potential_save_minor, 0)

        codes = [item.code for item in result.insights]
        self.assertIn("subscription_detected", codes)
        self.assertIn("category_growth", codes)
        self.assertIn("savings_recommendation", codes)

        for insight in result.insights:
            self.assertTrue(insight.title)
            self.assertTrue(insight.message)
            self.assertTrue(insight.action)
            self.assertGreaterEqual(int(insight.potential_save_minor), 0)

    def test_growth_insight_contains_budget_action(self):
        df = self._build_df()

        result = generate_financial_insights(df, amount_column="amount", currency="RUB")
        growth_items = [item for item in result.insights if item.code == "category_growth"]

        self.assertTrue(growth_items)
        taxi_growth = [item for item in growth_items if item.metadata.get("category") == "taxi"]
        self.assertTrue(taxi_growth)
        self.assertIn("Поставить бюджет", taxi_growth[0].action)

    def test_returns_no_insights_for_empty_expense_history(self):
        df = pd.DataFrame(
            [
                {
                    "transaction_id": "1",
                    "date": "2026-03-20",
                    "amount": 100000,
                    "currency": "RUB",
                    "merchant": "Employer",
                    "description": "Salary",
                    "category": "salary",
                }
            ]
        )

        result = generate_financial_insights(df, amount_column="amount", currency="RUB")

        self.assertEqual(result.metadata.get("total_insights"), 0)
        self.assertEqual(result.total_potential_save_minor, 0)
        self.assertEqual(result.insights, [])


if __name__ == "__main__":
    unittest.main()

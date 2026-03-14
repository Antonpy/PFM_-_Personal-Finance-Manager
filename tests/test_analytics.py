import unittest

import pandas as pd

from analytics import (
    ALL_FILTER_VALUE,
    aggregate_expenses_by_category,
    aggregate_monthly_expenses,
    aggregate_top_merchants,
    calculate_budget_usage,
    compare_expenses_with_previous_period,
    convert_transactions_to_base_currency,
    detect_recurring_expenses,
    filter_transactions,
    parse_major_amount_to_minor,
)


class TestAnalytics(unittest.TestCase):
    def _build_df(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "transaction_id": "1",
                    "date": "2026-01-05",
                    "amount": -10000,
                    "currency": "RUB",
                    "merchant": "Пятёрочка",
                    "description": "Продукты",
                    "category": "groceries",
                    "account": "card_1",
                },
                {
                    "transaction_id": "2",
                    "date": "2026-01-15",
                    "amount": -5000,
                    "currency": "RUB",
                    "merchant": "Магнит",
                    "description": "Продукты",
                    "category": "groceries",
                    "account": "card_1",
                },
                {
                    "transaction_id": "3",
                    "date": "2026-01-22",
                    "amount": -1990,
                    "currency": "RUB",
                    "merchant": "Yandex Go",
                    "description": "Taxi",
                    "category": "taxi",
                    "account": "card_1",
                },
                {
                    "transaction_id": "4",
                    "date": "2026-02-05",
                    "amount": -15000,
                    "currency": "RUB",
                    "merchant": "Пятёрочка",
                    "description": "Продукты",
                    "category": "groceries",
                    "account": "card_1",
                },
                {
                    "transaction_id": "5",
                    "date": "2026-02-14",
                    "amount": -29900,
                    "currency": "RUB",
                    "merchant": "Landlord",
                    "description": "Rent",
                    "category": "rent",
                    "account": "card_1",
                },
                {
                    "transaction_id": "6",
                    "date": "2026-02-20",
                    "amount": 12000000,
                    "currency": "RUB",
                    "merchant": "Employer",
                    "description": "Salary",
                    "category": "salary",
                    "account": "card_1",
                },
                {
                    "transaction_id": "7",
                    "date": "2026-03-01",
                    "amount": -99900,
                    "currency": "RUB",
                    "merchant": "Trip Store",
                    "description": "Travel",
                    "category": "travel",
                    "account": "card_1",
                },
                {
                    "transaction_id": "8",
                    "date": "2026-03-03",
                    "amount": -129900,
                    "currency": "USD",
                    "merchant": "Amazon",
                    "description": "Shopping",
                    "category": "shopping",
                    "account": "card_2",
                },
                # Recurring monthly subscription (30-31 days interval)
                {
                    "transaction_id": "9",
                    "date": "2026-01-10",
                    "amount": -99900,
                    "currency": "RUB",
                    "merchant": "Netflix",
                    "description": "Subscription",
                    "category": "subscriptions",
                    "account": "card_1",
                },
                {
                    "transaction_id": "10",
                    "date": "2026-02-10",
                    "amount": -99900,
                    "currency": "RUB",
                    "merchant": "Netflix",
                    "description": "Subscription",
                    "category": "subscriptions",
                    "account": "card_1",
                },
                {
                    "transaction_id": "11",
                    "date": "2026-03-10",
                    "amount": -99900,
                    "currency": "RUB",
                    "merchant": "Netflix",
                    "description": "Subscription",
                    "category": "subscriptions",
                    "account": "card_1",
                },
            ]
        )

    def test_filter_transactions_by_currency_and_account(self):
        df = self._build_df()

        rub_only = filter_transactions(df, currency="RUB", account=ALL_FILTER_VALUE)
        self.assertTrue((rub_only["currency"] == "RUB").all())

        rub_card_1 = filter_transactions(df, currency="RUB", account="card_1")
        self.assertTrue((rub_card_1["currency"] == "RUB").all())
        self.assertTrue((rub_card_1["account"] == "card_1").all())

    def test_aggregate_expenses_by_category(self):
        df = self._build_df()
        filtered = filter_transactions(df, currency="RUB", account="card_1")

        by_category = aggregate_expenses_by_category(filtered)

        groceries_row = by_category[by_category["category"] == "groceries"].iloc[0]
        # 10000 + 5000 + 15000 = 30000
        self.assertEqual(int(groceries_row["expense_minor"]), 30000)

        self.assertAlmostEqual(float(by_category["share_percent"].sum()), 100.0, places=1)

    def test_monthly_trend_and_period_comparison(self):
        df = self._build_df()
        filtered = filter_transactions(df, currency="RUB", account="card_1")

        monthly = aggregate_monthly_expenses(filtered)
        self.assertEqual(monthly.shape[0], 3)
        self.assertListEqual(monthly["month_label"].tolist(), ["2026-01", "2026-02", "2026-03"])

        comparison = compare_expenses_with_previous_period(filtered, months=1)
        # Current (Mar): 99900 + 99900 = 199800
        self.assertEqual(comparison.current_total_minor, 199800)
        # Previous (Feb): 15000 + 29900 + 99900 = 144800
        self.assertEqual(comparison.previous_total_minor, 144800)
        self.assertEqual(comparison.delta_minor, 55000)

    def test_top_merchants(self):
        df = self._build_df()
        filtered = filter_transactions(df, currency="RUB", account="card_1")

        top_merchants = aggregate_top_merchants(filtered, limit=3)

        self.assertEqual(top_merchants.shape[0], 3)
        self.assertEqual(top_merchants.iloc[0]["merchant"], "Netflix")
        self.assertEqual(int(top_merchants.iloc[0]["transactions"]), 3)

    def test_detect_recurring_expenses(self):
        df = self._build_df()
        filtered = filter_transactions(df, currency="RUB", account="card_1")

        recurring = detect_recurring_expenses(filtered)

        self.assertFalse(recurring.empty)
        netflix_row = recurring[recurring["merchant"] == "Netflix"].iloc[0]
        self.assertEqual(int(netflix_row["amount_minor"]), 99900)
        self.assertEqual(int(netflix_row["occurrences"]), 3)
        self.assertGreaterEqual(float(netflix_row["avg_interval_days"]), 29.0)
        self.assertLessEqual(float(netflix_row["avg_interval_days"]), 31.0)

    def test_budget_usage(self):
        df = self._build_df()
        filtered = filter_transactions(df, currency="RUB", account="card_1")

        budgets_minor = {
            "groceries": 25000,
            "subscriptions": 250000,
            "rent": 40000,
        }
        usage = calculate_budget_usage(filtered, budgets_minor=budgets_minor)

        groceries = usage[usage["category"] == "groceries"].iloc[0]
        self.assertTrue(bool(groceries["is_over_budget"]))
        self.assertEqual(int(groceries["remaining_minor"]), -5000)

        subscriptions = usage[usage["category"] == "subscriptions"].iloc[0]
        self.assertTrue(bool(subscriptions["is_over_budget"]))

    def test_parse_major_amount_to_minor(self):
        self.assertEqual(parse_major_amount_to_minor("123.45"), 12345)
        self.assertEqual(parse_major_amount_to_minor("1 234,56"), 123456)
        self.assertEqual(parse_major_amount_to_minor(""), 0)

    def test_convert_transactions_to_base_currency(self):
        df = pd.DataFrame(
            [
                {
                    "transaction_id": "t1",
                    "date": "2026-01-01",
                    "amount": -12345,
                    "currency": "USD",
                    "merchant": "Amazon",
                    "description": "order",
                    "category": "shopping",
                },
                {
                    "transaction_id": "t2",
                    "date": "2026-01-02",
                    "amount": -10000,
                    "currency": "EUR",
                    "merchant": "Ikea",
                    "description": "home",
                    "category": "shopping",
                },
                {
                    "transaction_id": "t3",
                    "date": "2026-01-03",
                    "amount": -5000,
                    "currency": "RUB",
                    "merchant": "Кофейня",
                    "description": "coffee",
                    "category": "food",
                },
            ]
        )

        result = convert_transactions_to_base_currency(
            df,
            base_currency="RUB",
            rates_major_to_base={"USD": "90.25", "EUR": "98.40"},
        )

        self.assertEqual(result.warnings, [])
        converted = result.dataframe

        usd_row = converted[converted["transaction_id"] == "t1"].iloc[0]
        eur_row = converted[converted["transaction_id"] == "t2"].iloc[0]
        rub_row = converted[converted["transaction_id"] == "t3"].iloc[0]

        # amount_base_minor = round(amount_minor * rate)
        self.assertEqual(int(usd_row["amount_base"]), -1114136)
        self.assertEqual(int(eur_row["amount_base"]), -984000)
        self.assertEqual(int(rub_row["amount_base"]), -5000)
        self.assertEqual(str(rub_row["base_currency"]), "RUB")
        self.assertAlmostEqual(float(result.metadata["conversion_coverage_percent"]), 100.0)

    def test_convert_transactions_to_base_currency_missing_rate_and_amount_column_analytics(self):
        df = pd.DataFrame(
            [
                {
                    "transaction_id": "m1",
                    "date": "2026-01-10",
                    "amount": -10000,
                    "currency": "USD",
                    "merchant": "Amazon",
                    "description": "shopping",
                    "category": "shopping",
                },
                {
                    "transaction_id": "m2",
                    "date": "2026-02-10",
                    "amount": -15000,
                    "currency": "EUR",
                    "merchant": "Store",
                    "description": "shopping",
                    "category": "shopping",
                },
                {
                    "transaction_id": "m3",
                    "date": "2026-03-10",
                    "amount": -3000,
                    "currency": "RUB",
                    "merchant": "Кофе",
                    "description": "food",
                    "category": "food",
                },
            ]
        )

        conversion = convert_transactions_to_base_currency(
            df,
            base_currency="RUB",
            rates_major_to_base={"USD": "91.10"},
        )

        self.assertTrue(any("Нет курсов" in warning for warning in conversion.warnings))

        converted = conversion.dataframe
        eur_row = converted[converted["transaction_id"] == "m2"].iloc[0]
        self.assertTrue(pd.isna(eur_row["amount_base"]))

        consolidated = converted[converted["amount_base"].notna()].copy()
        by_category = aggregate_expenses_by_category(consolidated, amount_column="amount_base")

        # USD: -10000 * 91.10 = -911000, RUB: -3000
        shopping_row = by_category[by_category["category"] == "shopping"].iloc[0]
        food_row = by_category[by_category["category"] == "food"].iloc[0]

        self.assertEqual(int(shopping_row["expense_minor"]), 911000)
        self.assertEqual(int(food_row["expense_minor"]), 3000)

        monthly = aggregate_monthly_expenses(consolidated, amount_column="amount_base")
        self.assertListEqual(monthly["month_label"].tolist(), ["2026-01", "2026-03"])


if __name__ == "__main__":
    unittest.main()

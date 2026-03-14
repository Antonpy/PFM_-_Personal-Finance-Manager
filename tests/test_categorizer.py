import tempfile
import unittest
from pathlib import Path

import pandas as pd

from categorizer import categorize_transactions, save_user_rule


class TestCategorizer(unittest.TestCase):
    def test_builtin_rules_cover_russian_merchants(self):
        df = pd.DataFrame(
            [
                {"transaction_id": "1", "merchant": "Пятёрочка", "description": "", "amount": -12500},
                {"transaction_id": "2", "merchant": "Магнит", "description": "", "amount": -2300},
                {"transaction_id": "3", "merchant": "Яндекс Go", "description": "Поездка", "amount": -990},
                {"transaction_id": "4", "merchant": "Ozon", "description": "Покупка", "amount": -4590},
                {"transaction_id": "5", "merchant": "Тинькофф", "description": "Зарплата за месяц", "amount": 15000000},
                {"transaction_id": "6", "merchant": "ЛУКОЙЛ", "description": "АЗС", "amount": -3200},
            ]
        )

        categorized_df, meta = categorize_transactions(df)

        self.assertEqual(categorized_df.loc[0, "category"], "groceries")
        self.assertEqual(categorized_df.loc[1, "category"], "groceries")
        self.assertEqual(categorized_df.loc[2, "category"], "taxi")
        self.assertEqual(categorized_df.loc[3, "category"], "shopping")
        self.assertEqual(categorized_df.loc[4, "category"], "salary")
        self.assertEqual(categorized_df.loc[5, "category"], "fuel")
        self.assertGreaterEqual(meta["coverage_ratio"], 0.8)

    def test_transliteration_matches(self):
        df = pd.DataFrame(
            [
                {"transaction_id": "1", "merchant": "Pyaterochka", "description": "", "amount": -1500},
                {"transaction_id": "2", "merchant": "Yandex Go", "description": "Taxi ride", "amount": -790},
                {"transaction_id": "3", "merchant": "Vaildberriz", "description": "", "amount": -4100},
            ]
        )

        categorized_df, meta = categorize_transactions(df)

        self.assertEqual(categorized_df.loc[0, "category"], "groceries")
        self.assertEqual(categorized_df.loc[1, "category"], "taxi")
        # Преднамеренно искаженное написание не обязано матчиться в MVP.
        self.assertIn(categorized_df.loc[2, "category"], {"shopping", "uncategorized"})
        self.assertGreaterEqual(meta["coverage_ratio"], 2 / 3)

    def test_user_rule_has_higher_priority_than_builtin(self):
        df = pd.DataFrame(
            [
                {
                    "transaction_id": "1",
                    "merchant": "Пятёрочка",
                    "description": "Продукты",
                    "amount": -3500,
                }
            ]
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            rules_path = Path(tmp_dir) / "user_rules.json"
            is_added = save_user_rule(
                pattern="Пятёрочка",
                category="family_budget",
                field="merchant",
                match_type="contains",
                direction="expense",
                rules_path=rules_path,
            )
            self.assertTrue(is_added)

            categorized_df, meta = categorize_transactions(df, rules_path=rules_path)

            self.assertEqual(categorized_df.loc[0, "category"], "family_budget")
            self.assertEqual(categorized_df.loc[0, "category_source"], "user")
            self.assertEqual(meta["rules_user"], 1)

    def test_save_user_rule_deduplicates(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            rules_path = Path(tmp_dir) / "user_rules.json"

            first_add = save_user_rule(
                pattern="ozon",
                category="shopping",
                field="merchant",
                match_type="contains",
                direction="expense",
                rules_path=rules_path,
            )
            second_add = save_user_rule(
                pattern="OZON",
                category="shopping",
                field="merchant",
                match_type="contains",
                direction="expense",
                rules_path=rules_path,
            )

            self.assertTrue(first_add)
            self.assertFalse(second_add)


if __name__ == "__main__":
    unittest.main()

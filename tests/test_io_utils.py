import io
import unittest

from io_utils import import_transactions


class TestImportTransactions(unittest.TestCase):
    def _build_upload(self, content_bytes: bytes, name: str):
        uploaded = io.BytesIO(content_bytes)
        uploaded.name = name
        return uploaded

    def test_ru_cp1251_semicolon_with_comma_decimal(self):
        csv_text = (
            "Дата;Сумма;Валюта;Магазин;Описание\n"
            "01.02.2026;-1 234,56;RUB;Пятёрочка;Продукты\n"
            "02.02.2026;120 000,00;RUB;;Зарплата\n"
        )
        upload = self._build_upload(csv_text.encode("cp1251"), "ru_export.csv")

        result = import_transactions(upload)

        self.assertEqual(result.errors, [])
        self.assertIsNotNone(result.dataframe)

        df = result.dataframe
        self.assertEqual(df.shape[0], 2)
        self.assertEqual(int(df.loc[0, "amount"]), -123456)
        self.assertEqual(int(df.loc[1, "amount"]), 12000000)
        self.assertEqual(df.loc[0, "currency"], "RUB")
        self.assertEqual(df.loc[0, "merchant"], "Пятёрочка")

    def test_us_decimal_and_generated_ids(self):
        csv_text = (
            "date,amount,currency,merchant,description\n"
            "2026-02-01,-23.50,USD,Target,Groceries\n"
            "2026-02-02,1200.00,USD,Employer,Salary\n"
        )
        upload = self._build_upload(csv_text.encode("utf-8"), "us_export.csv")

        result = import_transactions(upload)

        self.assertEqual(result.errors, [])
        df = result.dataframe
        self.assertIsNotNone(df)

        self.assertEqual(int(df.loc[0, "amount"]), -2350)
        self.assertEqual(int(df.loc[1, "amount"]), 120000)
        self.assertTrue(str(df.loc[0, "transaction_id"]).startswith("us_export.csv:"))

    def test_auto_mode_detects_minor_for_plain_int_amount(self):
        csv_text = (
            "date,amount,currency,merchant,description\n"
            "2026-02-01,-2350,RUB,,\n"
            "2026-02-02,-450,RUB,Go,\n"
            "2026-02-03,120000,RUB,,\n"
        )
        upload = self._build_upload(csv_text.encode("utf-8"), "minor_style.csv")

        result = import_transactions(upload, amount_mode="auto")

        self.assertEqual(result.errors, [])
        df = result.dataframe
        self.assertIsNotNone(df)

        self.assertEqual(int(df.loc[0, "amount"]), -2350)
        self.assertEqual(int(df.loc[1, "amount"]), -450)
        self.assertEqual(int(df.loc[2, "amount"]), 120000)
        self.assertEqual(result.metadata.get("amount_mode_interpreted"), "minor")
        self.assertFalse(any("already-minor" in warning for warning in result.warnings))

    def test_forced_major_mode_multiplies_plain_int_by_100(self):
        csv_text = (
            "date,amount,currency,merchant,description\n"
            "2026-02-01,-2350,RUB,,\n"
            "2026-02-02,120000,RUB,Employer,Salary\n"
        )
        upload = self._build_upload(csv_text.encode("utf-8"), "major_mode.csv")

        result = import_transactions(upload, amount_mode="major")

        self.assertEqual(result.errors, [])
        df = result.dataframe
        self.assertIsNotNone(df)

        self.assertEqual(int(df.loc[0, "amount"]), -235000)
        self.assertEqual(int(df.loc[1, "amount"]), 12000000)
        self.assertEqual(result.metadata.get("amount_mode_interpreted"), "major")

    def test_missing_required_columns(self):
        csv_text = "merchant,description\nStore,Only text\n"
        upload = self._build_upload(csv_text.encode("utf-8"), "broken.csv")

        result = import_transactions(upload)

        self.assertIsNone(result.dataframe)
        self.assertTrue(any("Отсутствуют обязательные колонки" in error for error in result.errors))


if __name__ == "__main__":
    unittest.main()

import unittest
from datetime import UTC, datetime

import pandas as pd

from export_utils import export_report_tables


class TestExportUtils(unittest.TestCase):
    def _build_tables(self) -> dict[str, pd.DataFrame]:
        return {
            "expenses_by_category": pd.DataFrame(
                [
                    {"category": "groceries", "expense_minor": 12345, "expense_major": 123.45},
                    {"category": "taxi", "expense_minor": 2345, "expense_major": 23.45},
                ]
            ),
            "monthly_expenses": pd.DataFrame(
                [
                    {
                        "month": pd.Timestamp("2026-01-01", tz="UTC"),
                        "expense_minor": 50000,
                        "expense_major": 500.0,
                        "month_label": "2026-01",
                    }
                ]
            ),
        }

    def test_export_all_formats_success(self):
        tables = self._build_tables()

        result = export_report_tables(
            report_name="PFM Demo Report",
            tables=tables,
            formats=("csv", "xlsx", "pdf"),
            generated_at=datetime(2026, 1, 2, 12, 0, tzinfo=UTC),
        )

        self.assertEqual(result.errors, [])
        self.assertGreaterEqual(len(result.artifacts), 4)

        formats = [artifact.format for artifact in result.artifacts]
        self.assertIn("csv", formats)
        self.assertIn("xlsx", formats)
        self.assertIn("pdf", formats)

        csv_artifacts = [artifact for artifact in result.artifacts if artifact.format == "csv"]
        self.assertEqual(len(csv_artifacts), 2)
        self.assertTrue(all(artifact.file_name.endswith(".csv") for artifact in csv_artifacts))

        xlsx_artifacts = [artifact for artifact in result.artifacts if artifact.format == "xlsx"]
        self.assertEqual(len(xlsx_artifacts), 1)
        self.assertTrue(xlsx_artifacts[0].content.startswith(b"PK"))

        pdf_artifacts = [artifact for artifact in result.artifacts if artifact.format == "pdf"]
        self.assertEqual(len(pdf_artifacts), 1)
        self.assertTrue(pdf_artifacts[0].content.startswith(b"%PDF-1.4"))

    def test_export_unsupported_format_warning(self):
        tables = self._build_tables()

        result = export_report_tables(
            report_name="PFM Demo Report",
            tables=tables,
            formats=("csv", "xml"),
        )

        self.assertEqual(result.errors, [])
        self.assertTrue(any("Неподдерживаемый формат" in warning for warning in result.warnings))
        self.assertTrue(any(artifact.format == "csv" for artifact in result.artifacts))

    def test_export_empty_tables_returns_error(self):
        result = export_report_tables(
            report_name="Empty",
            tables={},
            formats=("csv", "xlsx", "pdf"),
        )

        self.assertEqual(result.artifacts, [])
        self.assertTrue(any("Нет валидных таблиц" in error for error in result.errors))

    def test_export_skips_invalid_table_type(self):
        result = export_report_tables(
            report_name="Mixed",
            tables={
                "valid": pd.DataFrame([{"value": 1}]),
                "invalid": "not_a_dataframe",
            },
            formats=("csv",),
        )

        self.assertEqual(result.errors, [])
        self.assertTrue(any("неподдерживаемый тип" in warning for warning in result.warnings))
        self.assertEqual(len(result.artifacts), 1)
        self.assertEqual(result.artifacts[0].format, "csv")


if __name__ == "__main__":
    unittest.main()

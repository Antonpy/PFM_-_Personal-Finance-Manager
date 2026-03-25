from __future__ import annotations

import io
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from importlib import util as importlib_util
from typing import Any

import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from i18n import tr


@dataclass(frozen=True)
class ExportArtifact:
    """Отдельный сгенерированный артефакт экспорта."""

    file_name: str
    format: str
    mime_type: str
    content: bytes
    table_name: str | None = None


@dataclass(frozen=True)
class ExportResult:
    """Единый контракт результата экспорта Stage H."""

    artifacts: list[ExportArtifact] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


FONT_PATH = "DejaVuSans.ttf"
if os.path.exists(FONT_PATH):
    pdfmetrics.registerFont(TTFont("DejaVuSans", FONT_PATH))
    DEFAULT_FONT = "DejaVuSans"
else:
    DEFAULT_FONT = "Helvetica"


def _slugify(value: str) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9а-яё]+", "_", text, flags=re.IGNORECASE)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "report"


def _sanitize_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    prepared = dataframe.copy()

    for column in prepared.columns:
        if pd.api.types.is_datetime64_any_dtype(prepared[column]):
            prepared[column] = pd.to_datetime(prepared[column], errors="coerce", utc=True)
            prepared[column] = prepared[column].dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    return prepared


def _normalize_tables(tables: dict[str, pd.DataFrame], language: str) -> tuple[dict[str, pd.DataFrame], list[str]]:
    warnings: list[str] = []
    normalized: dict[str, pd.DataFrame] = {}

    for table_name, table_df in tables.items():
        normalized_name = str(table_name or "").strip()
        if not normalized_name:
            warnings.append(tr("export.empty_table_name", language))
            continue

        if not isinstance(table_df, pd.DataFrame):
            warnings.append(tr("export.invalid_table_type", language, table=normalized_name))
            continue

        normalized[normalized_name] = _sanitize_dataframe(table_df)

    return normalized, warnings


def _build_csv_artifacts(report_slug: str, tables: dict[str, pd.DataFrame]) -> list[ExportArtifact]:
    artifacts: list[ExportArtifact] = []

    for table_name, table_df in tables.items():
        table_slug = _slugify(table_name)
        file_name = f"{report_slug}__{table_slug}.csv"
        content = table_df.to_csv(index=False).encode("utf-8-sig")
        artifacts.append(
            ExportArtifact(
                file_name=file_name,
                format="csv",
                mime_type="text/csv",
                content=content,
                table_name=table_name,
            )
        )

    return artifacts


def _available_excel_writer_engines() -> list[str]:
    """Возвращает доступные движки для записи XLSX в порядке приоритета."""
    engines: list[str] = []

    if importlib_util.find_spec("openpyxl") is not None:
        engines.append("openpyxl")

    if importlib_util.find_spec("xlsxwriter") is not None:
        engines.append("xlsxwriter")

    return engines


def _build_xlsx_artifact(report_slug: str, tables: dict[str, pd.DataFrame]) -> ExportArtifact:
    file_name = f"{report_slug}.xlsx"
    engines = _available_excel_writer_engines()

    if not engines:
        raise ModuleNotFoundError("No module named 'openpyxl' or 'xlsxwriter'")

    errors: list[str] = []
    for engine in engines:
        buffer = io.BytesIO()
        try:
            with pd.ExcelWriter(buffer, engine=engine) as writer:
                for table_name, table_df in tables.items():
                    sheet_name = _slugify(table_name)[:31] or "sheet"
                    table_df.to_excel(writer, index=False, sheet_name=sheet_name)

            return ExportArtifact(
                file_name=file_name,
                format="xlsx",
                mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                content=buffer.getvalue(),
                table_name=None,
            )
        except Exception as error:  # noqa: BLE001
            errors.append(f"{engine}: {error}")

    raise RuntimeError("Failed to write XLSX with available engines: " + " | ".join(errors))


def _build_pdf_artifact(report_slug: str, tables: dict[str, pd.DataFrame]) -> ExportArtifact:
    buffer = io.BytesIO()
    report = canvas.Canvas(buffer, pagesize=A4, pdfVersion=(1, 4))
    _, height = A4

    report.setFont(DEFAULT_FONT, 8)

    y = height - 50
    line_height = 12

    report.setFont(DEFAULT_FONT, 12)
    report.drawString(50, y, f"PFM Export report: {report_slug}")
    y -= line_height * 2
    report.setFont(DEFAULT_FONT, 8)

    for table_name, table_df in tables.items():
        report.setFont(DEFAULT_FONT, 10)
        report.drawString(50, y, f"Table: {table_name} (rows={table_df.shape[0]}, columns={table_df.shape[1]})")
        y -= line_height
        report.setFont(DEFAULT_FONT, 8)

        if table_df.empty:
            report.drawString(70, y, "<empty>")
            y -= line_height * 2
            continue

        headers = list(table_df.columns)
        x_pos = 50
        for header in headers[:5]:
            report.drawString(x_pos, y, str(header)[:15])
            x_pos += 100
        y -= line_height

        preview_rows = min(10, table_df.shape[0])
        for i in range(preview_rows):
            x_pos = 50
            row = table_df.iloc[i]
            for value in row[:5]:
                report.drawString(x_pos, y, str(value)[:20])
                x_pos += 100
            y -= line_height

            if y < 50:
                report.showPage()
                report.setFont(DEFAULT_FONT, 8)
                y = height - 50

        y -= line_height

        if y < 100:
            report.showPage()
            report.setFont(DEFAULT_FONT, 8)
            y = height - 50

    report.save()

    return ExportArtifact(
        file_name=f"{report_slug}.pdf",
        format="pdf",
        mime_type="application/pdf",
        content=buffer.getvalue(),
        table_name=None,
    )


def export_report_tables(
    report_name: str,
    tables: dict[str, pd.DataFrame],
    formats: tuple[str, ...] = ("csv", "xlsx", "pdf"),
    generated_at: datetime | None = None,
    language: str = "ru",
) -> ExportResult:
    """
    Экспортирует готовые агрегаты/таблицы в набор артефактов CSV/XLSX/PDF.

    Контракт Stage H:
    - artifacts: готовые бинарные файлы,
    - warnings/errors: диагностические сообщения,
    - metadata: служебные параметры экспорта.
    """
    active_generated_at = generated_at or datetime.now(UTC)
    normalized_formats = [str(item).strip().lower() for item in formats if str(item).strip()]
    normalized_tables, warnings = _normalize_tables(tables, language=language)

    if not normalized_tables:
        return ExportResult(
            artifacts=[],
            warnings=warnings,
            errors=[tr("export.no_valid_tables", language)],
            metadata={
                "report_name": report_name,
                "requested_formats": normalized_formats,
                "generated_at": active_generated_at.isoformat(),
                "tables": [],
            },
        )

    report_slug = _slugify(report_name)
    artifacts: list[ExportArtifact] = []
    errors: list[str] = []

    for export_format in normalized_formats:
        if export_format == "csv":
            artifacts.extend(_build_csv_artifacts(report_slug, normalized_tables))
            continue

        if export_format == "xlsx":
            try:
                artifacts.append(_build_xlsx_artifact(report_slug, normalized_tables))
            except Exception as error:  # noqa: BLE001
                errors.append(tr("export.xlsx_failed", language, error=error))
            continue

        if export_format == "pdf":
            try:
                artifacts.append(_build_pdf_artifact(report_slug, normalized_tables))
            except Exception as error:  # noqa: BLE001
                errors.append(tr("export.pdf_failed", language, error=error))
            continue

        warnings.append(tr("export.unsupported_format", language, format=export_format))

    metadata = {
        "report_name": report_name,
        "report_slug": report_slug,
        "requested_formats": normalized_formats,
        "generated_at": active_generated_at.isoformat(),
        "tables": [
            {
                "name": table_name,
                "rows": int(table_df.shape[0]),
                "columns": int(table_df.shape[1]),
            }
            for table_name, table_df in normalized_tables.items()
        ],
        "artifacts_count": len(artifacts),
    }

    return ExportResult(artifacts=artifacts, warnings=warnings, errors=errors, metadata=metadata)

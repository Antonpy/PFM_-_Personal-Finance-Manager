from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

import pandas as pd

from i18n import tr

import os


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

# Регистрируем шрифт с кириллицей (нужен файл шрифта)

FONT_PATH = "DejaVuSans.ttf"
if os.path.exists(FONT_PATH):
    pdfmetrics.registerFont(TTFont('DejaVuSans', FONT_PATH))
    DEFAULT_FONT = 'DejaVuSans'
else:
    DEFAULT_FONT = 'Helvetica'  # fallback

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


def _build_xlsx_artifact(report_slug: str, tables: dict[str, pd.DataFrame]) -> ExportArtifact:
    file_name = f"{report_slug}.xlsx"
    buffer = io.BytesIO()

    with pd.ExcelWriter(buffer) as writer:
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


def _pdf_escape(text: str) -> str:
    escaped = str(text).replace("\\", "\\\\")
    escaped = escaped.replace("(", "\\(").replace(")", "\\)")
    return escaped


def _build_simple_pdf(lines: list[str]) -> bytes:
    encoded_lines = [f"({_pdf_escape(line)}) Tj" for line in lines]
    text_stream = "BT\n/F1 9 Tf\n36 806 Td\n12 TL\n"

    for index, line in enumerate(encoded_lines):
        if index == 0:
            text_stream += f"{line}\n"
        else:
            text_stream += f"T* {line}\n"

    text_stream += "ET"
    stream_bytes = text_stream.encode("latin-1", errors="replace")

    objects = [
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n",
        (
            b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj\n"
        ),
        b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n",
        (
            f"5 0 obj << /Length {len(stream_bytes)} >> stream\n".encode("ascii")
            + stream_bytes
            + b"\nendstream endobj\n"
        ),
    ]

    header = b"%PDF-1.4\n"
    body = bytearray(header)
    offsets = [0]

    for obj in objects:
        offsets.append(len(body))
        body.extend(obj)

    xref_offset = len(body)
    xref = [f"0 {len(objects) + 1}\n", "0000000000 65535 f \n"]
    for offset in offsets[1:]:
        xref.append(f"{offset:010d} 00000 n \n")

    body.extend(b"xref\n")
    body.extend("".join(xref).encode("ascii"))
    trailer = f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n"
    body.extend(trailer.encode("ascii"))

    return bytes(body)


def _build_pdf_artifact(report_slug: str, tables: dict[str, pd.DataFrame]) -> ExportArtifact:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    # Используем зарегистрированный шрифт с кириллицей
    c.setFont(DEFAULT_FONT, 8)

    y = height - 50  # Начинаем сверху
    line_height = 12

    # Заголовок
    c.setFont(DEFAULT_FONT, 12)
    c.drawString(50, y, f"PFM Export report: {report_slug}")
    y -= line_height * 2
    c.setFont(DEFAULT_FONT, 8)

    for table_name, table_df in tables.items():
        # Заголовок таблицы
        c.setFont(DEFAULT_FONT, 10)
        c.drawString(50, y, f"Table: {table_name} (rows={table_df.shape[0]}, columns={table_df.shape[1]})")
        y -= line_height
        c.setFont(DEFAULT_FONT, 8)

        if table_df.empty:
            c.drawString(70, y, "<empty>")
            y -= line_height * 2
            continue

        # Заголовки колонок
        headers = list(table_df.columns)
        x_pos = 50
        for header in headers[:5]:  # Ограничиваем до 5 колонок для читаемости
            c.drawString(x_pos, y, str(header)[:15])
            x_pos += 100
        y -= line_height

        # Данные (первые 10 строк)
        preview_rows = min(10, table_df.shape[0])
        for i in range(preview_rows):
            x_pos = 50
            row = table_df.iloc[i]
            for value in row[:5]:  # Ограничиваем до 5 колонок
                text = str(value)[:20]  # Обрезаем длинные значения
                c.drawString(x_pos, y, text)
                x_pos += 100
            y -= line_height

            # Если места мало, новая страница
            if y < 50:
                c.showPage()
                c.setFont(DEFAULT_FONT, 8)
                y = height - 50

        y -= line_height  # Отступ между таблицами

        # Если места мало для следующей таблицы, новая страница
        if y < 100:
            c.showPage()
            c.setFont(DEFAULT_FONT, 8)
            y = height - 50

    c.save()

    return ExportArtifact(
        file_name=f"{report_slug}.pdf",
        format="pdf",
        mime_type="application/pdf",
        content=buffer.getvalue(),
        table_name=None,
    )

#def _build_pdf_artifact(report_slug: str, tables: dict[str, pd.DataFrame]) -> ExportArtifact:
    lines: list[str] = [f"PFM Export report: {report_slug}"]

    for table_name, table_df in tables.items():
        lines.append(f"Table: {table_name} (rows={table_df.shape[0]}, columns={table_df.shape[1]})")
        preview_rows = min(5, table_df.shape[0])
        if preview_rows == 0:
            lines.append("  <empty>")
            continue

        preview = table_df.head(preview_rows).fillna("")
        header_line = " | ".join(str(column) for column in preview.columns)
        lines.append(f"  {header_line}")

        for _, row in preview.iterrows():
            row_line = " | ".join(str(value) for value in row.tolist())
            lines.append(f"  {row_line}")

    content = _build_simple_pdf(lines)
    return ExportArtifact(
        file_name=f"{report_slug}.pdf",
        format="pdf",
        mime_type="application/pdf",
        content=content,
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

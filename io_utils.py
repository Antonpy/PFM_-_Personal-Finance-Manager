import csv
import io
import logging
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

import pandas as pd

from i18n import tr


LOGGER = logging.getLogger(__name__)


@dataclass
class ImportResult:
    """Результат импорта транзакций с данными и диагностикой."""

    dataframe: pd.DataFrame | None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


COLUMN_ALIASES: dict[str, list[str]] = {
    "transaction_id": ["transaction_id", "id", "operation_id", "txid", "transactionid"],
    "date": [
        "date",
        "transaction_date",
        "operation_date",
        "booking_date",
        "posted_date",
        "дата",
        "датаоперации",
        "датаплатежа",
    ],
    "amount": ["amount", "sum", "value", "сумма", "суммаоперации"],
    "currency": ["currency", "curr", "ccy", "валюта"],
    "merchant": [
        "merchant",
        "payee",
        "counterparty",
        "recipient",
        "магазин",
        "мерчант",
        "получатель",
        "merchant_name",
    ],
    "description": [
        "description",
        "details",
        "memo",
        "note",
        "назначение",
        "комментарий",
        "описание",
        "операция",
    ],
}

SUPPORTED_ENCODINGS: list[str] = ["utf-8-sig", "utf-8", "cp1251", "latin1"]
COMMON_DELIMITERS: list[str] = [";", ",", "\t", "|"]
REQUIRED_CORE_COLUMNS: tuple[str, ...] = ("date", "amount")
ALLOWED_AMOUNT_MODES: tuple[str, ...] = ("auto", "major", "minor")


@dataclass
class ParsedAmount:
    """Промежуточный результат парсинга суммы."""

    value: int | None
    has_explicit_decimal: bool


def import_transactions(
    uploaded_file: Any,
    default_currency: str = "RUB",
    language: str = "ru",
    amount_mode: str = "auto",
) -> ImportResult:
    """
    Универсальный импорт транзакций из CSV/XLSX.

    Выходной DataFrame содержит колонки:
    transaction_id, date, amount, currency, merchant, description, raw_source
    где amount = int в minor units (копейки/центы).

    amount_mode:
    - auto: автоопределение по данным;
    - major: целые суммы интерпретируются как major units (например, RUB);
    - minor: целые суммы интерпретируются как already-minor units.
    """
    warnings: list[str] = []
    errors: list[str] = []

    normalized_amount_mode = str(amount_mode or "auto").strip().lower()
    if normalized_amount_mode not in ALLOWED_AMOUNT_MODES:
        normalized_amount_mode = "auto"

    filename = _get_filename(uploaded_file)
    raw_source = filename or "uploaded_file"

    raw = _read_uploaded_bytes(uploaded_file)
    if raw is None:
        return ImportResult(dataframe=None, errors=[tr("io.read_failed", language)])
    if not raw:
        return ImportResult(dataframe=None, errors=[tr("io.file_empty", language)])

    dataframe, read_meta, read_error = _read_dataframe(raw=raw, filename=filename)
    if read_error is not None:
        LOGGER.exception("Ошибка чтения файла %s: %s", raw_source, read_error)
        errors.append(tr("io.file_parse_failed", language))
        return ImportResult(dataframe=None, warnings=warnings, errors=errors, metadata={"raw_source": raw_source})

    mapped_df, mapping_warnings = _map_columns(dataframe, language=language)
    warnings.extend(mapping_warnings)

    missing_core = [column for column in REQUIRED_CORE_COLUMNS if column not in mapped_df.columns]
    if missing_core:
        errors.append(tr("io.missing_required_columns", language, columns=", ".join(missing_core)))
        return ImportResult(dataframe=None, warnings=warnings, errors=errors, metadata={"raw_source": raw_source})

    if "currency" not in mapped_df.columns:
        warnings.append(tr("io.currency_fallback", language, currency=default_currency))
        mapped_df["currency"] = default_currency

    if "merchant" not in mapped_df.columns and "description" not in mapped_df.columns:
        warnings.append(tr("io.merchant_desc_missing", language))

    normalized_df, normalize_warnings, normalize_meta = _normalize_dataframe(
        mapped_df,
        raw_source=raw_source,
        default_currency=default_currency,
        language=language,
        amount_mode=normalized_amount_mode,
    )
    warnings.extend(normalize_warnings)

    metadata = {
        "raw_source": raw_source,
        **read_meta,
        **normalize_meta,
        "rows": int(normalized_df.shape[0]),
    }
    return ImportResult(dataframe=normalized_df, warnings=warnings, errors=errors, metadata=metadata)


def _read_uploaded_bytes(uploaded_file: Any) -> bytes | None:
    try:
        if hasattr(uploaded_file, "seek"):
            uploaded_file.seek(0)
        return uploaded_file.read()
    except Exception:  # noqa: BLE001
        LOGGER.exception("Не удалось прочитать бинарное содержимое uploaded_file")
        return None


def _read_dataframe(raw: bytes, filename: str) -> tuple[pd.DataFrame | None, dict[str, Any], Exception | None]:
    lower_name = (filename or "").lower()
    read_meta: dict[str, Any] = {"detected_format": "unknown"}

    is_excel = lower_name.endswith((".xlsx", ".xls", ".xlsm")) or raw[:2] == b"PK"
    if is_excel:
        try:
            excel_buffer = io.BytesIO(raw)
            excel_df = pd.read_excel(excel_buffer)
            read_meta["detected_format"] = "excel"
            return excel_df, read_meta, None
        except Exception as excel_error:  # noqa: BLE001
            LOGGER.warning("Чтение как Excel не удалось, пробуем CSV: %s", excel_error)

    for encoding in SUPPORTED_ENCODINGS:
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError:
            continue

        delimiter = _detect_delimiter(text)
        if delimiter is None:
            delimiter = ","

        try:
            csv_df = pd.read_csv(io.StringIO(text), sep=delimiter, engine="python")
            if csv_df.shape[1] == 0:
                continue
            read_meta.update(
                {
                    "detected_format": "csv",
                    "detected_encoding": encoding,
                    "detected_delimiter": delimiter,
                }
            )
            return csv_df, read_meta, None
        except Exception as csv_error:  # noqa: BLE001
            LOGGER.warning(
                "Ошибка CSV-парсинга (encoding=%s, delimiter=%s): %s",
                encoding,
                delimiter,
                csv_error,
            )

    return None, read_meta, ValueError("Невозможно определить формат или корректно прочитать данные")


def _detect_delimiter(text: str) -> str | None:
    sample = text[:8192]

    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t|,")
        return dialect.delimiter
    except Exception:  # noqa: BLE001
        pass

    scores: dict[str, int] = {}
    lines = [line for line in sample.splitlines() if line.strip()][:10]
    if not lines:
        return None

    for delimiter in COMMON_DELIMITERS:
        scores[delimiter] = sum(line.count(delimiter) for line in lines)

    best_delimiter = max(scores, key=scores.get)
    return best_delimiter if scores[best_delimiter] > 0 else None


def _normalize_column_name(name: str) -> str:
    lowered = str(name).strip().lower()
    normalized = re.sub(r"[\s\-/.]+", "", lowered)
    normalized = normalized.replace("(", "").replace(")", "")
    return normalized


def _map_columns(df: pd.DataFrame, language: str) -> tuple[pd.DataFrame, list[str]]:
    warnings: list[str] = []
    normalized_to_original = {_normalize_column_name(column): column for column in df.columns}

    rename_map: dict[str, str] = {}
    for target, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            key = _normalize_column_name(alias)
            if key in normalized_to_original:
                rename_map[normalized_to_original[key]] = target
                break

    mapped_df = df.rename(columns=rename_map).copy()
    mapped_df = mapped_df.loc[:, ~mapped_df.columns.duplicated()]

    if "date" not in mapped_df.columns:
        warnings.append(tr("io.date_column_missing", language))
    if "amount" not in mapped_df.columns:
        warnings.append(tr("io.amount_column_missing", language))
    if "currency" not in mapped_df.columns:
        warnings.append(tr("io.currency_column_missing", language))

    return mapped_df, warnings


def _parse_amount_candidate(value: Any, assume_major_for_plain_int: bool) -> ParsedAmount:
    if pd.isna(value):
        return ParsedAmount(value=None, has_explicit_decimal=False)

    if isinstance(value, int):
        if assume_major_for_plain_int:
            return ParsedAmount(value=value * 100, has_explicit_decimal=False)
        return ParsedAmount(value=value, has_explicit_decimal=False)

    if isinstance(value, float):
        decimal_value = Decimal(str(value))
        minor = int((decimal_value * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        return ParsedAmount(value=minor, has_explicit_decimal=True)

    raw = str(value).strip()
    if not raw:
        return ParsedAmount(value=None, has_explicit_decimal=False)

    negative_by_brackets = raw.startswith("(") and raw.endswith(")")
    cleaned = raw.replace("(", "").replace(")", "")
    cleaned = cleaned.replace("\u00a0", "").replace(" ", "")
    cleaned = re.sub(r"[^0-9,.-]", "", cleaned)

    if cleaned.count("-") > 1:
        return ParsedAmount(value=None, has_explicit_decimal=False)

    has_explicit_decimal = False

    if "," in cleaned and "." in cleaned:
        has_explicit_decimal = True
        decimal_sep = "," if cleaned.rfind(",") > cleaned.rfind(".") else "."
        thousands_sep = "." if decimal_sep == "," else ","
        cleaned = cleaned.replace(thousands_sep, "")
        cleaned = cleaned.replace(decimal_sep, ".")
    elif "," in cleaned:
        comma_parts = cleaned.split(",")
        if len(comma_parts) == 2 and 0 < len(comma_parts[1]) <= 2:
            has_explicit_decimal = True
            cleaned = cleaned.replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "." in cleaned:
        dot_parts = cleaned.split(".")
        if len(dot_parts) == 2 and 0 < len(dot_parts[1]) <= 2:
            has_explicit_decimal = True
        else:
            cleaned = cleaned.replace(".", "")

    if negative_by_brackets and not cleaned.startswith("-"):
        cleaned = f"-{cleaned}"

    try:
        decimal_value = Decimal(cleaned)
    except InvalidOperation:
        return ParsedAmount(value=None, has_explicit_decimal=has_explicit_decimal)

    if has_explicit_decimal:
        minor = int((decimal_value * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        return ParsedAmount(value=minor, has_explicit_decimal=True)

    integer_value = int(decimal_value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if assume_major_for_plain_int:
        return ParsedAmount(value=integer_value * 100, has_explicit_decimal=False)

    return ParsedAmount(value=integer_value, has_explicit_decimal=False)


def _detect_plain_integer_mode(amount_series: pd.Series) -> bool:
    """
    Определяет, интерпретировать ли суммы без явной дробной части как major units.

    Логика:
    - Если есть хотя бы одна запись с явным десятичным разделителем -> plain int считаем major.
    - Иначе анализируем распределение последних двух цифр:
      если много значений НЕ кратны 100, считаем, что это already-minor формат.
    """
    explicit_decimal_found = False
    plain_int_values: list[int] = []

    for value in amount_series.tolist():
        if pd.isna(value):
            continue

        if isinstance(value, float):
            explicit_decimal_found = True
            continue

        raw = str(value).strip()
        if not raw:
            continue

        cleaned = raw.replace("\u00a0", "").replace(" ", "")
        cleaned = re.sub(r"[^0-9,.-]", "", cleaned)

        has_decimal = False
        if "," in cleaned and "." in cleaned:
            has_decimal = True
        elif "," in cleaned:
            parts = cleaned.split(",")
            has_decimal = len(parts) == 2 and 0 < len(parts[1]) <= 2
        elif "." in cleaned:
            parts = cleaned.split(".")
            has_decimal = len(parts) == 2 and 0 < len(parts[1]) <= 2

        if has_decimal:
            explicit_decimal_found = True
            continue

        try:
            plain_int_values.append(int(Decimal(cleaned.replace(",", "").replace(".", ""))))
        except Exception:  # noqa: BLE001
            continue

    if explicit_decimal_found:
        return True

    if not plain_int_values:
        return True

    not_multiple_100 = sum(1 for number in plain_int_values if abs(number) % 100 != 0)
    ratio = not_multiple_100 / len(plain_int_values)

    return ratio < 0.30


def _resolve_plain_int_mode(amount_series: pd.Series, amount_mode: str) -> tuple[bool, str]:
    normalized_mode = str(amount_mode or "auto").strip().lower()

    if normalized_mode == "major":
        return True, "major"
    if normalized_mode == "minor":
        return False, "minor"

    assume_major = _detect_plain_integer_mode(amount_series)
    return assume_major, "major" if assume_major else "minor"


def _normalize_currency(value: Any, default_currency: str) -> str:
    if pd.isna(value):
        return default_currency

    currency = str(value).strip().upper()
    if not currency:
        return default_currency

    currency = re.sub(r"[^A-Z]", "", currency)
    if len(currency) != 3:
        return default_currency

    return currency


def _normalize_text(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _normalize_date_series(date_series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(date_series, errors="coerce", utc=True)

    missing_mask = parsed.isna()
    if missing_mask.any():
        parsed_dayfirst = pd.to_datetime(
            date_series[missing_mask],
            errors="coerce",
            utc=True,
            dayfirst=True,
        )
        parsed.loc[missing_mask] = parsed_dayfirst

    return parsed


def _normalize_amount_series(amount_series: pd.Series, amount_mode: str) -> tuple[pd.Series, str]:
    assume_major_for_plain_int, interpreted_mode = _resolve_plain_int_mode(amount_series, amount_mode=amount_mode)
    parsed = amount_series.apply(
        lambda value: _parse_amount_candidate(
            value=value,
            assume_major_for_plain_int=assume_major_for_plain_int,
        )
    )
    result_series = parsed.apply(lambda item: item.value)
    return result_series, interpreted_mode


def _normalize_dataframe(
    df: pd.DataFrame,
    raw_source: str,
    default_currency: str,
    language: str,
    amount_mode: str,
) -> tuple[pd.DataFrame, list[str], dict[str, Any]]:
    warnings: list[str] = []
    normalized = df.copy()

    if "merchant" not in normalized.columns:
        normalized["merchant"] = ""
    if "description" not in normalized.columns:
        normalized["description"] = ""
    if "currency" not in normalized.columns:
        normalized["currency"] = default_currency

    normalized["date"] = _normalize_date_series(normalized["date"])
    invalid_dates = int(normalized["date"].isna().sum())
    if invalid_dates > 0:
        warnings.append(tr("io.date_parse_failed", language, count=invalid_dates))

    normalized_amount, interpreted_amount_mode = _normalize_amount_series(normalized["amount"], amount_mode=amount_mode)
    normalized["amount"] = normalized_amount
    invalid_amounts = int(normalized["amount"].isna().sum())
    if invalid_amounts > 0:
        warnings.append(tr("io.amount_parse_failed", language, count=invalid_amounts))

    normalized["currency"] = normalized["currency"].apply(
        lambda value: _normalize_currency(value, default_currency)
    )
    normalized["merchant"] = normalized["merchant"].apply(_normalize_text)
    normalized["description"] = normalized["description"].apply(_normalize_text)
    normalized["raw_source"] = raw_source

    if "transaction_id" in normalized.columns:
        normalized["transaction_id"] = normalized["transaction_id"].apply(_normalize_text)
    else:
        normalized["transaction_id"] = ""

    empty_id_mask = normalized["transaction_id"] == ""
    if empty_id_mask.any():
        generated_ids = pd.RangeIndex(start=1, stop=empty_id_mask.sum() + 1, step=1)
        normalized.loc[empty_id_mask, "transaction_id"] = [
            f"{raw_source}:{index}" for index in generated_ids
        ]

    output_columns = [
        "transaction_id",
        "date",
        "amount",
        "currency",
        "merchant",
        "description",
        "raw_source",
    ]

    normalized = normalized[output_columns].copy()

    before_drop = normalized.shape[0]
    normalized = normalized.dropna(subset=["date", "amount"], how="all").reset_index(drop=True)
    dropped_rows = before_drop - normalized.shape[0]
    if dropped_rows > 0:
        warnings.append(tr("io.empty_rows_dropped", language, count=dropped_rows))

    normalized["amount"] = normalized["amount"].astype("Int64")

    meta = {
        "amount_mode_requested": amount_mode,
        "amount_mode_interpreted": interpreted_amount_mode,
    }

    return normalized, warnings, meta


def _get_filename(uploaded_file: Any) -> str:
    name = getattr(uploaded_file, "name", "")
    return str(name) if name else "uploaded_file"

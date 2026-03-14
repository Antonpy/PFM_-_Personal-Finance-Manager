from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

import pandas as pd

from i18n import tr


ALL_FILTER_VALUE = "__all__"


@dataclass(frozen=True)
class PeriodComparison:
    """Сводка сравнения расходов текущего и предыдущего периодов."""

    months: int
    current_total_minor: int
    previous_total_minor: int
    delta_minor: int
    delta_percent: float | None


@dataclass(frozen=True)
class CurrencyConversionResult:
    """Результат конвертации транзакций в базовую валюту."""

    dataframe: pd.DataFrame
    warnings: list[str]
    metadata: dict[str, Any]


def parse_major_amount_to_minor(value: Any) -> int:
    """
    Преобразует сумму в major units (например, 1234.56) в minor units (123456).

    Использует Decimal без float-арифметики для финансовой точности.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return 0

    text = str(value).strip()
    if not text:
        return 0

    normalized = text.replace("\u00a0", "").replace(" ", "").replace(",", ".")
    try:
        decimal_value = Decimal(normalized)
    except InvalidOperation:
        return 0

    minor = (decimal_value * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(minor)


def minor_to_major(minor_value: Any) -> float:
    """Безопасно преобразует minor units в major units для UI-отображения."""
    if pd.isna(minor_value):
        return 0.0
    return int(minor_value) / 100.0


def _month_start_utc(series: pd.Series) -> pd.Series:
    """
    Нормализует даты к началу месяца в UTC без предупреждений pandas о timezone.

    Важно: сначала делаем даты tz-naive, затем применяем to_period('M').
    """
    utc_series = pd.to_datetime(series, errors="coerce", utc=True)
    naive_utc = utc_series.dt.tz_convert("UTC").dt.tz_localize(None)
    month_start_naive = naive_utc.dt.to_period("M").dt.to_timestamp()
    return month_start_naive.dt.tz_localize("UTC")


def _ensure_required_columns(dataframe: pd.DataFrame) -> pd.DataFrame:
    prepared = dataframe.copy()

    if "transaction_id" not in prepared.columns:
        prepared["transaction_id"] = prepared.index.astype(str)
    if "date" not in prepared.columns:
        prepared["date"] = pd.NaT
    if "amount" not in prepared.columns:
        prepared["amount"] = pd.NA
    if "amount_base" not in prepared.columns:
        prepared["amount_base"] = pd.NA
    if "category" not in prepared.columns:
        prepared["category"] = "uncategorized"
    if "merchant" not in prepared.columns:
        prepared["merchant"] = ""
    if "description" not in prepared.columns:
        prepared["description"] = ""
    if "currency" not in prepared.columns:
        prepared["currency"] = ""
    if "base_currency" not in prepared.columns:
        prepared["base_currency"] = ""

    prepared["transaction_id"] = prepared["transaction_id"].fillna("").astype(str)
    prepared["date"] = pd.to_datetime(prepared["date"], errors="coerce", utc=True)
    prepared["amount"] = pd.to_numeric(prepared["amount"], errors="coerce")
    prepared["amount_base"] = pd.to_numeric(prepared["amount_base"], errors="coerce")
    prepared["category"] = prepared["category"].fillna("uncategorized").astype(str)
    prepared["merchant"] = prepared["merchant"].fillna("").astype(str).str.strip()
    prepared["description"] = prepared["description"].fillna("").astype(str).str.strip()
    prepared["currency"] = prepared["currency"].fillna("").astype(str).str.upper().str.strip()
    prepared["base_currency"] = prepared["base_currency"].fillna("").astype(str).str.upper().str.strip()

    if "account" in prepared.columns:
        prepared["account"] = prepared["account"].fillna("").astype(str).str.strip()

    return prepared


def _prepare_amount_column(prepared: pd.DataFrame, amount_column: str) -> pd.DataFrame:
    normalized = prepared.copy()
    if amount_column not in normalized.columns:
        normalized[amount_column] = pd.NA
    normalized[amount_column] = pd.to_numeric(normalized[amount_column], errors="coerce")
    return normalized


def _normalize_rates(
    base_currency: str,
    rates_major_to_base: dict[str, Any] | None,
) -> tuple[dict[str, Decimal], list[str]]:
    parsed_rates: dict[str, Decimal] = {base_currency: Decimal("1")}
    invalid_rate_currencies: list[str] = []

    source = rates_major_to_base or {}
    for currency, rate_value in source.items():
        normalized_currency = str(currency).upper().strip()
        if not normalized_currency:
            continue

        try:
            parsed = Decimal(str(rate_value).strip())
        except (InvalidOperation, ValueError):
            invalid_rate_currencies.append(normalized_currency)
            continue

        if parsed <= 0:
            invalid_rate_currencies.append(normalized_currency)
            continue

        parsed_rates[normalized_currency] = parsed

    return parsed_rates, sorted(set(invalid_rate_currencies))


def convert_transactions_to_base_currency(
    dataframe: pd.DataFrame,
    base_currency: str,
    rates_major_to_base: dict[str, Any] | None,
    language: str = "ru",
) -> CurrencyConversionResult:
    """
    Конвертирует amount (minor units исходной валюты) в amount_base (minor units базовой валюты).

    Правило курса: 1 major unit валюты транзакции = rate major units базовой валюты.
    Формула для minor->minor: amount_base_minor = round(amount_minor * rate).
    """
    prepared = _ensure_required_columns(dataframe)
    normalized_base = str(base_currency or "RUB").upper().strip() or "RUB"

    rates, invalid_rate_currencies = _normalize_rates(normalized_base, rates_major_to_base)
    converted = prepared.copy()
    converted["amount_base"] = pd.Series([pd.NA] * converted.shape[0], dtype="Int64")
    converted["base_currency"] = normalized_base

    missing_rate_currencies: set[str] = set()
    converted_rows = 0

    for row_index, row in converted.iterrows():
        amount_minor = row.get("amount")
        currency = str(row.get("currency", "")).upper().strip()

        if pd.isna(amount_minor):
            continue

        if not currency:
            missing_rate_currencies.add("<EMPTY>")
            continue

        rate = rates.get(currency)
        if rate is None:
            missing_rate_currencies.add(currency)
            continue

        amount_major = Decimal(int(amount_minor)) / Decimal("100")
        amount_base_major = amount_major / rate  # ДЕЛИМ, а не умножаем!
        amount_base_minor = (amount_base_major * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)

        converted.at[row_index, "amount_base"] = int(amount_base_minor)
        converted_rows += 1

    warnings: list[str] = []
    if invalid_rate_currencies:
        warnings.append(
            tr("analytics.invalid_rates", language, currencies=", ".join(invalid_rate_currencies))
        )

    missing_sorted = sorted(missing_rate_currencies)
    if missing_sorted:
        warnings.append(
            tr("analytics.missing_rates", language, currencies=", ".join(missing_sorted))
        )

    metadata = {
        "base_currency": normalized_base,
        "total_rows": int(converted.shape[0]),
        "converted_rows": int(converted_rows),
        "conversion_coverage_percent": (
            round((converted_rows / converted.shape[0]) * 100, 2) if converted.shape[0] > 0 else 0.0
        ),
        "missing_rate_currencies": missing_sorted,
        "invalid_rate_currencies": invalid_rate_currencies,
        "rates_applied": {currency: str(rate) for currency, rate in sorted(rates.items())},
    }

    return CurrencyConversionResult(dataframe=converted, warnings=warnings, metadata=metadata)


def filter_transactions(
    dataframe: pd.DataFrame,
    currency: str = ALL_FILTER_VALUE,
    account: str = ALL_FILTER_VALUE,
) -> pd.DataFrame:
    """
    Фильтрует транзакции по валюте и аккаунту (если аккаунт присутствует в данных).

    Если account-колонка отсутствует, фильтр по аккаунту пропускается.
    """
    filtered = _ensure_required_columns(dataframe)

    if currency != ALL_FILTER_VALUE:
        filtered = filtered[filtered["currency"] == str(currency).upper().strip()]

    if account != ALL_FILTER_VALUE and "account" in filtered.columns:
        filtered = filtered[filtered["account"] == str(account).strip()]

    return filtered.reset_index(drop=True)


def aggregate_expenses_by_category(dataframe: pd.DataFrame, amount_column: str = "amount") -> pd.DataFrame:
    """Агрегирует расходы (amount_column < 0) по категориям."""
    prepared = _prepare_amount_column(_ensure_required_columns(dataframe), amount_column)
    expenses = prepared[prepared[amount_column] < 0].copy()
    if expenses.empty:
        return pd.DataFrame(columns=["category", "expense_minor", "expense_major", "share_percent"])

    grouped = (
        expenses.assign(expense_minor=expenses[amount_column].abs())
        .groupby("category", dropna=False, as_index=False)["expense_minor"]
        .sum()
        .sort_values("expense_minor", ascending=False)
        .reset_index(drop=True)
    )

    total_minor = int(grouped["expense_minor"].sum())
    grouped["expense_major"] = grouped["expense_minor"].apply(minor_to_major)
    grouped["share_percent"] = (
        grouped["expense_minor"].apply(lambda value: round((int(value) / total_minor) * 100, 2))
        if total_minor > 0
        else 0.0
    )
    return grouped


def aggregate_monthly_expenses(dataframe: pd.DataFrame, amount_column: str = "amount") -> pd.DataFrame:
    """Строит помесячный ряд расходов (abs(sum(amount_column<0)))."""
    prepared = _prepare_amount_column(_ensure_required_columns(dataframe), amount_column)
    expenses = prepared[(prepared[amount_column] < 0) & prepared["date"].notna()].copy()
    if expenses.empty:
        return pd.DataFrame(columns=["month", "expense_minor", "expense_major", "month_label"])

    expenses["month"] = _month_start_utc(expenses["date"])
    monthly = (
        expenses.assign(expense_minor=expenses[amount_column].abs())
        .groupby("month", as_index=False)["expense_minor"]
        .sum()
        .sort_values("month")
        .reset_index(drop=True)
    )
    monthly["expense_major"] = monthly["expense_minor"].apply(minor_to_major)
    monthly["month_label"] = monthly["month"].dt.strftime("%Y-%m")
    return monthly


def compare_expenses_with_previous_period(
    dataframe: pd.DataFrame,
    months: int = 3,
    amount_column: str = "amount",
) -> PeriodComparison:
    """
    Сравнивает расходы последних N месяцев с предыдущими N месяцами.

    Берется последний доступный месяц в данных как конец текущего периода.
    """
    if months <= 0:
        months = 1

    monthly = aggregate_monthly_expenses(dataframe, amount_column=amount_column)
    if monthly.empty:
        return PeriodComparison(
            months=months,
            current_total_minor=0,
            previous_total_minor=0,
            delta_minor=0,
            delta_percent=None,
        )

    last_month = monthly["month"].max()
    current_start = (last_month - pd.DateOffset(months=months - 1)).normalize()
    previous_start = (current_start - pd.DateOffset(months=months)).normalize()
    previous_end = (current_start - pd.DateOffset(days=1)).normalize()

    current_mask = (monthly["month"] >= current_start) & (monthly["month"] <= last_month)
    previous_mask = (monthly["month"] >= previous_start) & (monthly["month"] <= previous_end)

    current_total = int(monthly.loc[current_mask, "expense_minor"].sum())
    previous_total = int(monthly.loc[previous_mask, "expense_minor"].sum())
    delta_minor = current_total - previous_total

    if previous_total == 0:
        delta_percent = None
    else:
        delta_percent = round((delta_minor / previous_total) * 100, 2)

    return PeriodComparison(
        months=months,
        current_total_minor=current_total,
        previous_total_minor=previous_total,
        delta_minor=delta_minor,
        delta_percent=delta_percent,
    )


def aggregate_top_merchants(
    dataframe: pd.DataFrame,
    limit: int = 10,
    amount_column: str = "amount",
) -> pd.DataFrame:
    """Возвращает топ мерчантов по расходам."""
    prepared = _prepare_amount_column(_ensure_required_columns(dataframe), amount_column)
    expenses = prepared[prepared[amount_column] < 0].copy()
    if expenses.empty:
        return pd.DataFrame(columns=["merchant", "transactions", "expense_minor", "expense_major"])

    expenses["merchant_display"] = expenses["merchant"]
    empty_merchant = expenses["merchant_display"].str.strip() == ""
    expenses.loc[empty_merchant, "merchant_display"] = expenses.loc[empty_merchant, "description"]
    expenses.loc[expenses["merchant_display"].str.strip() == "", "merchant_display"] = "Unknown"

    grouped = (
        expenses.assign(expense_minor=expenses[amount_column].abs())
        .groupby("merchant_display", as_index=False)
        .agg(expense_minor=("expense_minor", "sum"), transactions=("transaction_id", "count"))
        .sort_values(["expense_minor", "transactions"], ascending=[False, False])
        .head(max(limit, 1))
        .reset_index(drop=True)
        .rename(columns={"merchant_display": "merchant"})
    )

    grouped["expense_major"] = grouped["expense_minor"].apply(minor_to_major)
    return grouped[["merchant", "transactions", "expense_minor", "expense_major"]]


def detect_recurring_expenses(
    dataframe: pd.DataFrame,
    min_occurrences: int = 3,
    min_interval_days: int = 20,
    max_interval_days: int = 40,
    amount_column: str = "amount",
) -> pd.DataFrame:
    """
    Ищет регулярные списания: одинаковый мерчант + одинаковая сумма + регулярный интервал.

    MVP-правило: медианный интервал между платежами лежит в диапазоне [min_interval_days, max_interval_days].
    Дополнительно защищаемся от ложноположительных срабатываний на редких больших паузах:
    - не менее 80% интервалов должны лежать в целевом диапазоне;
    - максимальный интервал не должен превышать верхнюю границу более чем в 2 раза.
    """
    prepared = _prepare_amount_column(_ensure_required_columns(dataframe), amount_column)
    expenses = prepared[(prepared[amount_column] < 0) & prepared["date"].notna()].copy()
    if expenses.empty:
        return pd.DataFrame(
            columns=[
                "merchant",
                "amount_minor",
                "amount_major",
                "occurrences",
                "avg_interval_days",
                "last_date",
                "next_expected_date",
            ]
        )

    expenses["merchant_display"] = expenses["merchant"]
    no_merchant = expenses["merchant_display"].str.strip() == ""
    expenses.loc[no_merchant, "merchant_display"] = expenses.loc[no_merchant, "description"]
    expenses.loc[expenses["merchant_display"].str.strip() == "", "merchant_display"] = "Unknown"

    expenses["amount_abs"] = expenses[amount_column].abs().astype("Int64")
    rows: list[dict[str, Any]] = []

    for (merchant, amount_minor), group in expenses.groupby(["merchant_display", "amount_abs"], dropna=False):
        if pd.isna(amount_minor):
            continue

        ordered = group.sort_values("date")
        if ordered.shape[0] < min_occurrences:
            continue

        intervals = ordered["date"].diff().dropna().dt.days
        if intervals.empty:
            continue

        avg_interval = float(intervals.mean())
        median_interval = float(intervals.median())

        if not (min_interval_days <= median_interval <= max_interval_days):
            continue

        in_range_ratio = float(((intervals >= min_interval_days) & (intervals <= max_interval_days)).mean())
        max_interval_observed = float(intervals.max())

        if in_range_ratio < 0.8:
            continue

        if max_interval_observed > float(max_interval_days) * 2:
            continue

        last_date = ordered["date"].max()
        next_expected = last_date + pd.Timedelta(days=round(avg_interval))

        rows.append(
            {
                "merchant": str(merchant),
                "amount_minor": int(amount_minor),
                "amount_major": minor_to_major(amount_minor),
                "occurrences": int(ordered.shape[0]),
                "avg_interval_days": round(avg_interval, 2),
                "last_date": last_date,
                "next_expected_date": next_expected,
            }
        )

    if not rows:
        return pd.DataFrame(
            columns=[
                "merchant",
                "amount_minor",
                "amount_major",
                "occurrences",
                "avg_interval_days",
                "last_date",
                "next_expected_date",
            ]
        )

    recurring_df = pd.DataFrame(rows).sort_values(["occurrences", "amount_minor"], ascending=[False, False])
    recurring_df = recurring_df.reset_index(drop=True)
    return recurring_df


def calculate_budget_usage(
    dataframe: pd.DataFrame,
    budgets_minor: dict[str, int],
    amount_column: str = "amount",
) -> pd.DataFrame:
    """Рассчитывает использование бюджета по категориям на основе фактических расходов."""
    category_expenses = aggregate_expenses_by_category(dataframe, amount_column=amount_column)
    if category_expenses.empty:
        return pd.DataFrame(
            columns=[
                "category",
                "expense_minor",
                "expense_major",
                "budget_minor",
                "budget_major",
                "usage_percent",
                "is_over_budget",
                "remaining_minor",
                "remaining_major",
            ]
        )

    usage = category_expenses.copy()
    usage["budget_minor"] = usage["category"].map(lambda category: int(budgets_minor.get(category, 0)))
    usage["budget_major"] = usage["budget_minor"].apply(minor_to_major)

    def _usage_percent(row: pd.Series) -> float | None:
        budget_minor = int(row["budget_minor"])
        if budget_minor <= 0:
            return None
        return round((int(row["expense_minor"]) / budget_minor) * 100, 2)

    usage["usage_percent"] = usage.apply(_usage_percent, axis=1)
    usage["is_over_budget"] = usage.apply(
        lambda row: int(row["budget_minor"]) > 0 and int(row["expense_minor"]) > int(row["budget_minor"]),
        axis=1,
    )
    usage["remaining_minor"] = usage["budget_minor"] - usage["expense_minor"]
    usage["remaining_major"] = usage["remaining_minor"].apply(minor_to_major)

    return usage[
        [
            "category",
            "expense_minor",
            "expense_major",
            "budget_minor",
            "budget_major",
            "usage_percent",
            "is_over_budget",
            "remaining_minor",
            "remaining_major",
        ]
    ]

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

import pandas as pd

from analytics import detect_recurring_expenses
from i18n import tr


@dataclass(frozen=True)
class InsightsThresholds:
    """Пороговые значения для генерации финансовых инсайтов."""

    min_subscription_occurrences: int = 3
    subscription_interval_min_days: int = 20
    subscription_interval_max_days: int = 40
    max_subscription_insights: int = 3

    min_category_growth_percent: float = 20.0
    min_category_growth_minor: int = 1_000
    max_growth_insights: int = 3

    savings_recommendation_ratio: Decimal = Decimal("1.00")


@dataclass(frozen=True)
class FinancialInsight:
    """Короткий, actionable-инсайт для UI."""

    code: str
    title: str
    message: str
    action: str
    potential_save_minor: int
    potential_save_major: float
    severity: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class InsightsResult:
    """Результат генерации инсайтов."""

    insights: list[FinancialInsight]
    total_potential_save_minor: int
    total_potential_save_major: float
    metadata: dict[str, Any]


def _minor_to_major(minor_value: int) -> float:
    return int(minor_value) / 100.0


def _format_major(minor_value: int, currency: str) -> str:
    major = _minor_to_major(minor_value)
    return f"{major:.2f} {currency}"


def _month_start_utc(series: pd.Series) -> pd.Series:
    """Нормализует даты к началу месяца в UTC без предупреждений pandas о timezone."""
    utc_series = pd.to_datetime(series, errors="coerce", utc=True)
    naive_utc = utc_series.dt.tz_convert("UTC").dt.tz_localize(None)
    month_start_naive = naive_utc.dt.to_period("M").dt.to_timestamp()
    return month_start_naive.dt.tz_localize("UTC")


def _prepare_dataframe(dataframe: pd.DataFrame, amount_column: str) -> pd.DataFrame:
    prepared = dataframe.copy()

    if "date" not in prepared.columns:
        prepared["date"] = pd.NaT
    if amount_column not in prepared.columns:
        prepared[amount_column] = pd.NA
    if "category" not in prepared.columns:
        prepared["category"] = "uncategorized"

    prepared["date"] = pd.to_datetime(prepared["date"], errors="coerce", utc=True)
    prepared[amount_column] = pd.to_numeric(prepared[amount_column], errors="coerce")
    prepared["category"] = prepared["category"].fillna("uncategorized").astype(str)

    return prepared


def _detect_subscription_insights(
    dataframe: pd.DataFrame,
    amount_column: str,
    thresholds: InsightsThresholds,
    currency: str,
    language: str,
) -> list[FinancialInsight]:
    recurring = detect_recurring_expenses(
        dataframe,
        min_occurrences=max(2, thresholds.min_subscription_occurrences),
        min_interval_days=max(1, thresholds.subscription_interval_min_days),
        max_interval_days=max(thresholds.subscription_interval_min_days, thresholds.subscription_interval_max_days),
        amount_column=amount_column,
    )
    if recurring.empty:
        return []

    recurring = recurring.sort_values(["amount_minor", "occurrences"], ascending=[False, False]).head(
        max(1, thresholds.max_subscription_insights)
    )

    insights: list[FinancialInsight] = []
    for _, row in recurring.iterrows():
        merchant = str(row.get("merchant", "Unknown"))
        amount_minor = int(row.get("amount_minor", 0))
        occurrences = int(row.get("occurrences", 0))
        avg_interval_days = float(row.get("avg_interval_days", 0.0))

        if amount_minor <= 0:
            continue

        message = tr(
            "insights.subscription_message",
            language,
            merchant=merchant,
            amount=_format_major(amount_minor, currency),
            occurrences=occurrences,
            interval=avg_interval_days,
        )

        insights.append(
            FinancialInsight(
                code=tr("insights.subscription_code", language),
                title=tr("insights.subscription_title", language, merchant=merchant),
                message=message,
                action=tr("insights.subscription_action", language),
                potential_save_minor=amount_minor,
                potential_save_major=_minor_to_major(amount_minor),
                severity="medium",
                metadata={
                    "merchant": merchant,
                    "occurrences": occurrences,
                    "avg_interval_days": avg_interval_days,
                },
            )
        )

    return insights


def _detect_growth_insights(
    dataframe: pd.DataFrame,
    amount_column: str,
    thresholds: InsightsThresholds,
    currency: str,
    language: str,
) -> list[FinancialInsight]:
    prepared = _prepare_dataframe(dataframe, amount_column)
    expenses = prepared[(prepared[amount_column] < 0) & prepared["date"].notna()].copy()
    if expenses.empty:
        return []

    expenses["month"] = _month_start_utc(expenses["date"])
    expenses["expense_minor"] = expenses[amount_column].abs().astype("Int64")

    monthly_category = (
        expenses.groupby(["month", "category"], as_index=False)["expense_minor"]
        .sum()
        .sort_values(["month", "expense_minor"], ascending=[True, False])
    )
    if monthly_category.empty:
        return []

    last_month = monthly_category["month"].max()
    previous_month = (last_month - pd.DateOffset(months=1)).normalize()

    current = monthly_category[monthly_category["month"] == last_month][["category", "expense_minor"]].rename(
        columns={"expense_minor": "current_minor"}
    )
    previous = monthly_category[monthly_category["month"] == previous_month][["category", "expense_minor"]].rename(
        columns={"expense_minor": "previous_minor"}
    )

    if current.empty or previous.empty:
        return []

    merged = current.merge(previous, on="category", how="left")
    merged["previous_minor"] = merged["previous_minor"].fillna(0).astype(int)
    merged["current_minor"] = merged["current_minor"].fillna(0).astype(int)
    merged["delta_minor"] = merged["current_minor"] - merged["previous_minor"]

    positive_growth = merged[(merged["delta_minor"] > 0) & (merged["previous_minor"] > 0)].copy()
    if positive_growth.empty:
        return []

    positive_growth["growth_percent"] = (
        positive_growth["delta_minor"] / positive_growth["previous_minor"] * 100
    ).round(2)

    filtered = positive_growth[
        (positive_growth["growth_percent"] >= thresholds.min_category_growth_percent)
        & (positive_growth["delta_minor"] >= thresholds.min_category_growth_minor)
    ].copy()

    if filtered.empty:
        return []

    filtered = filtered.sort_values(["delta_minor", "growth_percent"], ascending=[False, False]).head(
        max(1, thresholds.max_growth_insights)
    )

    insights: list[FinancialInsight] = []
    for _, row in filtered.iterrows():
        category = str(row.get("category", "uncategorized"))
        previous_minor = int(row.get("previous_minor", 0))
        current_minor = int(row.get("current_minor", 0))
        delta_minor = int(row.get("delta_minor", 0))
        growth_percent = float(row.get("growth_percent", 0.0))

        message = tr(
            "insights.growth_message",
            language,
            category=category,
            percent=growth_percent,
            previous=_format_major(previous_minor, currency),
            current=_format_major(current_minor, currency),
        )

        insights.append(
            FinancialInsight(
                code=tr("insights.growth_code", language),
                title=tr("insights.growth_title", language, category=category),
                message=message,
                action=tr("insights.growth_action", language),
                potential_save_minor=delta_minor,
                potential_save_major=_minor_to_major(delta_minor),
                severity="high",
                metadata={
                    "category": category,
                    "growth_percent": growth_percent,
                    "previous_minor": previous_minor,
                    "current_minor": current_minor,
                },
            )
        )

    return insights


def _build_savings_summary(
    insights: list[FinancialInsight],
    thresholds: InsightsThresholds,
    currency: str,
    language: str,
) -> FinancialInsight | None:
    total_minor = sum(max(0, int(item.potential_save_minor)) for item in insights)
    if total_minor <= 0:
        return None

    ratio = thresholds.savings_recommendation_ratio
    if ratio <= 0:
        ratio = Decimal("1")

    recommended_minor = int(
        (Decimal(total_minor) * ratio).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )

    message = tr(
        "insights.savings_message",
        language,
        detected=_format_major(total_minor, currency),
        recommended=_format_major(recommended_minor, currency),
    )

    return FinancialInsight(
        code=tr("insights.savings_code", language),
        title=tr("insights.savings_title", language),
        message=message,
        action=tr("insights.savings_action", language),
        potential_save_minor=recommended_minor,
        potential_save_major=_minor_to_major(recommended_minor),
        severity="high",
        metadata={
            "total_detected_minor": total_minor,
            "recommended_minor": recommended_minor,
            "recommendation_ratio": str(ratio),
        },
    )


def generate_financial_insights(
    dataframe: pd.DataFrame,
    amount_column: str = "amount",
    currency: str = "RUB",
    thresholds: InsightsThresholds | None = None,
    language: str = "ru",
) -> InsightsResult:
    """
    Генерирует короткие инсайты и действия по экономии.

    Логика MVP:
    - повторяющиеся подписки (merchant + amount + регулярный интервал),
    - категории с заметным ростом расходов месяц-к-месяцу,
    - итоговая рекомендация по накоплениям.
    """
    active_thresholds = thresholds or InsightsThresholds()

    subscription_insights = _detect_subscription_insights(
        dataframe,
        amount_column=amount_column,
        thresholds=active_thresholds,
        currency=currency,
        language=language,
    )
    growth_insights = _detect_growth_insights(
        dataframe,
        amount_column=amount_column,
        thresholds=active_thresholds,
        currency=currency,
        language=language,
    )

    insights = [*subscription_insights, *growth_insights]
    savings_summary = _build_savings_summary(
        insights,
        thresholds=active_thresholds,
        currency=currency,
        language=language,
    )
    if savings_summary is not None:
        insights.append(savings_summary)

    # В total учитываем только прямые потенциальные экономии, без дублирования сводным инсайтом.
    total_potential_minor = sum(max(0, int(item.potential_save_minor)) for item in insights)

    metadata = {
        "total_insights": len(insights),
        "subscription_insights": len(subscription_insights),
        "growth_insights": len(growth_insights),
        "has_savings_summary": savings_summary is not None,
        "amount_column": amount_column,
        "currency": currency,
    }

    return InsightsResult(
        insights=insights,
        total_potential_save_minor=total_potential_minor,
        total_potential_save_major=_minor_to_major(total_potential_minor),
        metadata=metadata,
    )

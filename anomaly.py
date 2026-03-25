from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, UTC
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Literal

import pandas as pd


FeedbackVerdict = Literal["ok", "fraud"]
DEFAULT_FEEDBACK_PATH = Path("models") / "anomaly_feedback.json"


@dataclass(frozen=True)
class AnomalyThresholds:
    """Пороговые параметры rule-based обнаружения аномалий."""

    high_amount_multiplier: Decimal = Decimal("3")
    rare_merchant_max_ratio: Decimal = Decimal("0.05")
    rare_merchant_max_tx_count: int = 1
    country_switch_max_gap_hours: int = 48


@dataclass(frozen=True)
class UserStats:
    """Агрегированная пользовательская статистика для antifraud правил."""

    avg_expense_minor: int
    merchant_expense_ratio: dict[str, Decimal]
    merchant_tx_count: dict[str, int]
    expense_transactions: int


@dataclass(frozen=True)
class AnomalyDetectionResult:
    """Результат детекции аномалий."""

    dataframe: pd.DataFrame
    metadata: dict[str, Any]


def _normalize_text(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _ensure_columns(dataframe: pd.DataFrame) -> pd.DataFrame:
    prepared = dataframe.copy()

    if "transaction_id" not in prepared.columns:
        prepared["transaction_id"] = prepared.index.astype(str)
    if "date" not in prepared.columns:
        prepared["date"] = pd.NaT
    if "amount" not in prepared.columns:
        prepared["amount"] = pd.NA
    if "merchant" not in prepared.columns:
        prepared["merchant"] = ""
    if "description" not in prepared.columns:
        prepared["description"] = ""
    if "country" not in prepared.columns:
        prepared["country"] = ""
    if "currency" not in prepared.columns:
        prepared["currency"] = ""

    prepared["transaction_id"] = prepared["transaction_id"].fillna("").astype(str)
    prepared["date"] = pd.to_datetime(prepared["date"], errors="coerce", utc=True)
    prepared["amount"] = pd.to_numeric(prepared["amount"], errors="coerce")
    prepared["merchant"] = prepared["merchant"].apply(_normalize_text)
    prepared["description"] = prepared["description"].apply(_normalize_text)
    prepared["country"] = prepared["country"].apply(_normalize_text).str.upper()
    prepared["currency"] = prepared["currency"].apply(_normalize_text).str.upper()

    return prepared


def _prepare_amount_column(prepared: pd.DataFrame, amount_column: str) -> pd.DataFrame:
    normalized = prepared.copy()
    if amount_column not in normalized.columns:
        normalized[amount_column] = pd.NA
    normalized[amount_column] = pd.to_numeric(normalized[amount_column], errors="coerce")
    return normalized


def _merchant_display(row: pd.Series) -> str:
    merchant = _normalize_text(row.get("merchant", ""))
    if merchant:
        return merchant

    description = _normalize_text(row.get("description", ""))
    return description if description else "Unknown"


def _safe_ratio(numerator: int, denominator: int) -> Decimal:
    if denominator <= 0:
        return Decimal("0")
    return Decimal(numerator) / Decimal(denominator)


def build_user_stats(dataframe: pd.DataFrame, amount_column: str = "amount") -> UserStats:
    """
    Строит агрегированную статистику пользователя по расходным операциям.

    Все суммы рассчитываются в minor units без float-арифметики.
    """
    prepared = _prepare_amount_column(_ensure_columns(dataframe), amount_column)
    expenses = prepared[prepared[amount_column] < 0].copy()

    if expenses.empty:
        return UserStats(
            avg_expense_minor=0,
            merchant_expense_ratio={},
            merchant_tx_count={},
            expense_transactions=0,
        )

    expenses["merchant_display"] = expenses.apply(_merchant_display, axis=1)
    expenses["expense_minor"] = expenses[amount_column].abs().astype("Int64")

    total_expense_minor = int(expenses["expense_minor"].sum())
    expense_transactions = int(expenses.shape[0])

    if expense_transactions == 0:
        avg_expense_minor = 0
    else:
        avg_expense_minor = int(
            (Decimal(total_expense_minor) / Decimal(expense_transactions)).quantize(
                Decimal("1"),
                rounding=ROUND_HALF_UP,
            )
        )

    merchant_grouped = (
        expenses.groupby("merchant_display", as_index=False)
        .agg(
            expense_minor=("expense_minor", "sum"),
            tx_count=("transaction_id", "count"),
        )
        .reset_index(drop=True)
    )

    merchant_ratio = {
        str(row["merchant_display"]): _safe_ratio(int(row["expense_minor"]), total_expense_minor)
        for _, row in merchant_grouped.iterrows()
    }
    merchant_tx_count = {
        str(row["merchant_display"]): int(row["tx_count"])
        for _, row in merchant_grouped.iterrows()
    }

    return UserStats(
        avg_expense_minor=avg_expense_minor,
        merchant_expense_ratio=merchant_ratio,
        merchant_tx_count=merchant_tx_count,
        expense_transactions=expense_transactions,
    )


def detect_anomalies(
    dataframe: pd.DataFrame,
    user_stats: UserStats | None = None,
    thresholds: AnomalyThresholds | None = None,
    amount_column: str = "amount",
) -> AnomalyDetectionResult:
    """
    Выполняет rule-based детекцию аномалий.

    Правила MVP:
    1) high_amount: расход > N * средний расход пользователя;
    2) rare_merchant: мерчант редкий по доле и/или количеству транзакций;
    3) country_switch: подряд идущие транзакции в разных странах (в пределах окна часов).
    """
    applied_thresholds = thresholds or AnomalyThresholds()
    prepared = _prepare_amount_column(_ensure_columns(dataframe), amount_column)
    stats = user_stats or build_user_stats(prepared, amount_column=amount_column)

    analyzed = prepared.copy()
    analyzed["merchant_display"] = analyzed.apply(_merchant_display, axis=1)

    analyzed["anomaly_high_amount"] = False
    analyzed["anomaly_rare_merchant"] = False
    analyzed["anomaly_country_switch"] = False
    analyzed["anomaly_score"] = 0
    analyzed["anomaly_reasons"] = ""
    analyzed["is_anomaly"] = False

    avg_expense = stats.avg_expense_minor
    if avg_expense > 0:
        high_amount_threshold_minor = int(
            (Decimal(avg_expense) * applied_thresholds.high_amount_multiplier).quantize(
                Decimal("1"),
                rounding=ROUND_HALF_UP,
            )
        )
    else:
        high_amount_threshold_minor = 0

    for row_index, row in analyzed.iterrows():
        reasons: list[str] = []

        amount_value = row.get(amount_column)
        merchant_name = str(row.get("merchant_display", "Unknown"))

        is_expense = pd.notna(amount_value) and int(amount_value) < 0
        expense_minor = abs(int(amount_value)) if is_expense else 0

        if is_expense and high_amount_threshold_minor > 0 and expense_minor > high_amount_threshold_minor:
            analyzed.at[row_index, "anomaly_high_amount"] = True
            reasons.append(
                f"high_amount>{high_amount_threshold_minor}"
            )

        if is_expense and stats.expense_transactions > 0:
            merchant_ratio = stats.merchant_expense_ratio.get(merchant_name, Decimal("0"))
            merchant_tx_count = stats.merchant_tx_count.get(merchant_name, 0)
            if (
                merchant_ratio <= applied_thresholds.rare_merchant_max_ratio
                or merchant_tx_count <= applied_thresholds.rare_merchant_max_tx_count
            ):
                analyzed.at[row_index, "anomaly_rare_merchant"] = True
                reasons.append("rare_merchant")

        analyzed.at[row_index, "anomaly_score"] = len(reasons)
        if reasons:
            analyzed.at[row_index, "anomaly_reasons"] = ";".join(reasons)

    dated = analyzed[analyzed["date"].notna() & (analyzed["country"].str.strip() != "")].copy()
    if not dated.empty:
        dated = dated.sort_values("date")
        previous_country = None
        previous_date = None

        for row_index, row in dated.iterrows():
            current_country = str(row.get("country", "")).strip().upper()
            current_date = row.get("date")

            if previous_country and current_country and previous_country != current_country:
                if previous_date is not None and pd.notna(current_date):
                    gap_hours = (current_date - previous_date).total_seconds() / 3600
                    if gap_hours <= applied_thresholds.country_switch_max_gap_hours:
                        analyzed.at[row_index, "anomaly_country_switch"] = True
                        current_reasons = str(analyzed.at[row_index, "anomaly_reasons"]).strip(";")
                        updated_reasons = (
                            f"{current_reasons};country_switch"
                            if current_reasons
                            else "country_switch"
                        )
                        analyzed.at[row_index, "anomaly_reasons"] = updated_reasons
                        analyzed.at[row_index, "anomaly_score"] = int(analyzed.at[row_index, "anomaly_score"]) + 1

            previous_country = current_country
            previous_date = current_date

    analyzed["is_anomaly"] = analyzed["anomaly_score"] > 0

    metadata = {
        "total_rows": int(analyzed.shape[0]),
        "anomaly_rows": int(analyzed["is_anomaly"].sum()),
        "high_amount_rows": int(analyzed["anomaly_high_amount"].sum()),
        "rare_merchant_rows": int(analyzed["anomaly_rare_merchant"].sum()),
        "country_switch_rows": int(analyzed["anomaly_country_switch"].sum()),
        "avg_expense_minor": int(stats.avg_expense_minor),
        "high_amount_threshold_minor": int(high_amount_threshold_minor),
        "expense_transactions": int(stats.expense_transactions),
    }

    return AnomalyDetectionResult(dataframe=analyzed, metadata=metadata)


def load_anomaly_feedback(feedback_path: str | Path = DEFAULT_FEEDBACK_PATH) -> list[dict[str, Any]]:
    """Загружает журнал ручной antifraud валидации."""
    path = Path(feedback_path)
    if not path.exists():
        return []

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []

    if not isinstance(payload, list):
        return []

    return [entry for entry in payload if isinstance(entry, dict)]


def save_anomaly_feedback(
    transaction_id: str,
    verdict: FeedbackVerdict,
    feedback_path: str | Path = DEFAULT_FEEDBACK_PATH,
    reasons: list[str] | None = None,
    comment: str = "",
    context: dict[str, Any] | None = None,
) -> bool:
    """
    Сохраняет пользовательскую пометку транзакции (ok/fraud).

    Для одного transaction_id хранится одна актуальная запись (upsert).
    """
    tx_id = str(transaction_id).strip()
    normalized_verdict = str(verdict).strip().lower()

    if not tx_id or normalized_verdict not in {"ok", "fraud"}:
        return False

    path = Path(feedback_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = load_anomaly_feedback(path)

    entry = {
        "transaction_id": tx_id,
        "verdict": normalized_verdict,
        "reasons": [str(reason).strip() for reason in (reasons or []) if str(reason).strip()],
        "comment": str(comment).strip(),
        "context": context or {},
        "updated_at": datetime.now(UTC).isoformat(),
    }

    existing_index = next(
        (index for index, item in enumerate(payload) if str(item.get("transaction_id", "")).strip() == tx_id),
        None,
    )

    if existing_index is None:
        payload.append(entry)
    else:
        payload[existing_index] = entry

    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def summarize_feedback(
    feedback_entries: list[dict[str, Any]],
    transaction_ids: set[str] | None = None,
) -> dict[str, int]:
    """Строит компактную сводку по ручной валидации аномалий."""
    scoped = feedback_entries
    if transaction_ids is not None:
        scoped = [
            item
            for item in feedback_entries
            if str(item.get("transaction_id", "")).strip() in transaction_ids
        ]

    fraud_count = sum(1 for item in scoped if str(item.get("verdict", "")).lower() == "fraud")
    ok_count = sum(1 for item in scoped if str(item.get("verdict", "")).lower() == "ok")

    return {
        "total_feedback": len(scoped),
        "fraud_count": fraud_count,
        "ok_count": ok_count,
    }

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import streamlit as st

from analytics import ALL_FILTER_VALUE, convert_transactions_to_base_currency, filter_transactions
from state_manager import get_current_language, t


@dataclass(frozen=True)
class AnalyticsScope:
    base_filtered_df: pd.DataFrame
    converted_df: pd.DataFrame
    available_currencies: list[str]
    selected_account: str
    selected_base_currency: str


def render_scope_filters(categorized_df: pd.DataFrame, page_key: str) -> AnalyticsScope | None:
    has_account_column = "account" in categorized_df.columns
    selected_account = ALL_FILTER_VALUE

    if has_account_column:
        available_accounts = sorted(
            value for value in categorized_df["account"].dropna().astype(str).unique().tolist() if value
        )
        account_options = [ALL_FILTER_VALUE, *available_accounts]
        selected_account = st.selectbox(
            t("ui.account_filter"),
            options=account_options,
            format_func=lambda value: t("ui.all_accounts") if value == ALL_FILTER_VALUE else value,
            key=f"account_filter::{page_key}",
        )

    base_filtered_df = filter_transactions(
        categorized_df,
        currency=ALL_FILTER_VALUE,
        account=selected_account,
    )

    if base_filtered_df.empty:
        st.warning(t("ui.empty_after_account_filter"))
        return None

    available_currencies = sorted(
        value for value in base_filtered_df["currency"].dropna().astype(str).str.upper().unique().tolist() if value
    )
    if not available_currencies:
        st.warning(t("ui.currency_missing"))
        return None

    base_currency_options = sorted(set(["RUB", "USD", "EUR", *available_currencies]))
    selected_base_currency = st.selectbox(
        t("ui.base_currency"),
        options=base_currency_options,
        index=base_currency_options.index("RUB") if "RUB" in base_currency_options else 0,
        key=f"base_currency::{page_key}",
    )

    st.markdown(f"#### {t('ui.manual_rates')}")
    st.caption(t("ui.manual_rates_caption"))

    rates_store: dict[str, float] = st.session_state["fx_rates_major_to_base"]
    rates_major_to_base: dict[str, float] = {}

    rate_columns = st.columns(min(3, max(1, len(available_currencies))))
    for index, currency_code in enumerate(available_currencies):
        if currency_code == selected_base_currency:
            continue

        rate_key = f"{currency_code}->{selected_base_currency}"
        default_rate = float(rates_store.get(rate_key, 0.0))

        with rate_columns[index % len(rate_columns)]:
            entered_rate = st.number_input(
                t("ui.rate_input", from_currency=currency_code, to_currency=selected_base_currency),
                min_value=0.0,
                value=default_rate,
                step=0.01,
                format="%.6f",
                key=f"fx_input::{page_key}::{rate_key}",
            )

        rates_store[rate_key] = float(entered_rate)
        if entered_rate > 0:
            rates_major_to_base[currency_code] = float(entered_rate)

    conversion_result = convert_transactions_to_base_currency(
        base_filtered_df,
        base_currency=selected_base_currency,
        rates_major_to_base=rates_major_to_base,
        language=get_current_language(),
    )

    for warning_text in conversion_result.warnings:
        st.warning(warning_text)

    return AnalyticsScope(
        base_filtered_df=base_filtered_df,
        converted_df=conversion_result.dataframe,
        available_currencies=available_currencies,
        selected_account=selected_account,
        selected_base_currency=selected_base_currency,
    )

from __future__ import annotations

from pathlib import Path

import streamlit as st

from analytics import ALL_FILTER_VALUE, filter_transactions
from handlers import anomaly_feedback_path, get_categorized_transactions_df
from pages.shared import render_scope_filters
from state_manager import t
from ui_components import render_dashboard_blocks


def render_budgets_page(user_id: str, user_rules_file: Path) -> None:
    categorized_df, _ = get_categorized_transactions_df(rules_path=user_rules_file)
    if categorized_df is None or categorized_df.empty:
        st.info(t("ui.need_data_to_continue"))
        return

    st.subheader(t("ui.budget_usage"))
    scope = render_scope_filters(categorized_df, page_key="budgets")
    if scope is None:
        return

    feedback_path = anomaly_feedback_path(user_id)

    tab_titles = [*scope.available_currencies, t("ui.consolidated_tab", currency=scope.selected_base_currency)]
    tabs = st.tabs(tab_titles)

    for currency_code, tab in zip(scope.available_currencies, tabs[:-1]):
        with tab:
            currency_df = filter_transactions(
                scope.base_filtered_df,
                currency=currency_code,
                account=ALL_FILTER_VALUE,
            )
            render_dashboard_blocks(
                analytics_df=currency_df,
                amount_column="amount",
                display_currency=currency_code,
                budget_scope_key=f"budget_source::{scope.selected_account}::{currency_code}",
                anomaly_feedback_file=feedback_path,
                mode="budgets",
            )

    with tabs[-1]:
        consolidated_df = scope.converted_df[scope.converted_df["amount_base"].notna()].copy()
        if consolidated_df.empty:
            st.info(t("ui.consolidated_empty"))
        else:
            render_dashboard_blocks(
                analytics_df=consolidated_df,
                amount_column="amount_base",
                display_currency=scope.selected_base_currency,
                budget_scope_key=f"budget_base::{scope.selected_account}::{scope.selected_base_currency}",
                anomaly_feedback_file=feedback_path,
                mode="budgets",
            )

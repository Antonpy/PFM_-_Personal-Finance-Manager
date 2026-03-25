from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import altair as alt
import pandas as pd
import streamlit as st

from analytics import (
    aggregate_expenses_by_category,
    aggregate_monthly_expenses,
    aggregate_top_merchants,
    calculate_budget_usage,
    compare_expenses_with_previous_period,
    detect_recurring_expenses,
    parse_major_amount_to_minor,
)
from anomaly import (
    AnomalyThresholds,
    detect_anomalies,
    load_anomaly_feedback,
    save_anomaly_feedback,
    summarize_feedback,
)
from auth import (
    DEFAULT_USERS_PATH,
    delete_user_account,
    derive_user_encryption_key,
    login_user,
    register_user,
    update_user_consent,
)
from export_utils import export_report_tables
from handlers import (
    anomaly_feedback_path,
    clear_authenticated_session,
    set_authenticated_session,
    user_rules_path,
)
from insights import generate_financial_insights
from secure_store import delete_user_secure_data
from state_manager import get_current_language, t


USER_DATA_DIR = Path("models") / "user_data"


def render_language_switcher() -> None:
    current_language = get_current_language()

    with st.sidebar:
        st.markdown(f"## {t('ui.language_section')}")
        selected_label = st.selectbox(
            t("ui.language_label"),
            options=[t("ui.language_ru"), t("ui.language_en")],
            index=0 if current_language == "ru" else 1,
            key="language_selector",
        )

        selected_code = "ru" if selected_label == t("ui.language_ru") else "en"
        if selected_code != current_language:
            st.session_state["ui_language"] = selected_code
            st.rerun()


def render_auth_panel() -> dict[str, Any] | None:
    current_language = get_current_language()

    with st.sidebar:
        st.markdown(f"## {t('ui.account')}")

        current_user = st.session_state.get("auth_user")
        if current_user is None:
            login_tab, register_tab = st.tabs([t("ui.tab_login"), t("ui.tab_register")])

            with login_tab:
                with st.form("login_form", clear_on_submit=False):
                    login_email = st.text_input(t("ui.email"), key="login_email_input")
                    login_password = st.text_input(t("ui.password"), type="password", key="login_password_input")
                    login_submit = st.form_submit_button(t("ui.login"), type="primary")

                if login_submit:
                    login_result = login_user(
                        login_email,
                        login_password,
                        users_path=DEFAULT_USERS_PATH,
                        language=current_language,
                    )
                    if not login_result.success or login_result.user is None:
                        st.error(login_result.message)
                    else:
                        encryption_key = derive_user_encryption_key(
                            user_id=str(login_result.user.get("user_id", "")),
                            password=login_password,
                            users_path=DEFAULT_USERS_PATH,
                        )
                        if encryption_key is None:
                            st.error(t("ui.encryption_key_prepare_failed"))
                        else:
                            set_authenticated_session(login_result.user, encryption_key)
                            st.success(t("ui.login_success"))
                            st.rerun()

            with register_tab:
                with st.form("register_form", clear_on_submit=False):
                    register_email = st.text_input(t("ui.email"), key="register_email_input")
                    register_password = st.text_input(
                        t("ui.password"),
                        type="password",
                        key="register_password_input",
                    )
                    register_submit = st.form_submit_button(t("ui.register"), type="primary")

                if register_submit:
                    register_result = register_user(
                        register_email,
                        register_password,
                        users_path=DEFAULT_USERS_PATH,
                        language=current_language,
                    )
                    if not register_result.success or register_result.user is None:
                        st.error(register_result.message)
                    else:
                        encryption_key = derive_user_encryption_key(
                            user_id=str(register_result.user.get("user_id", "")),
                            password=register_password,
                            users_path=DEFAULT_USERS_PATH,
                        )
                        if encryption_key is None:
                            st.error(t("ui.encryption_key_prepare_partial"))
                        else:
                            set_authenticated_session(register_result.user, encryption_key)
                            st.success(t("ui.register_success_logged_in"))
                            st.rerun()

            st.info(t("ui.auth_required_info"))
            return None

        st.success(t("ui.logged_in_as", email=current_user.get("email", "")))
        st.caption(t("ui.user_id", user_id=current_user.get("user_id", "")))

        consent_value = st.checkbox(
            t("ui.consent_checkbox"),
            value=bool(current_user.get("consent_pii_storage", False)),
            key=f"consent_checkbox::{current_user.get('user_id', '')}",
        )
        if st.button(t("ui.save_consent"), key=f"consent_save::{current_user.get('user_id', '')}"):
            is_updated = update_user_consent(
                user_id=str(current_user.get("user_id", "")),
                consent_pii_storage=consent_value,
                users_path=DEFAULT_USERS_PATH,
            )
            if is_updated:
                current_user["consent_pii_storage"] = bool(consent_value)
                st.session_state["auth_user"] = current_user
                st.success(t("ui.consent_saved"))
                st.rerun()
            else:
                st.error(t("ui.consent_save_failed"))

        if st.button(t("ui.logout"), key=f"logout::{current_user.get('user_id', '')}"):
            clear_authenticated_session()
            st.rerun()

        with st.expander(t("ui.delete_account_expander"), expanded=False):
            st.warning(t("ui.delete_account_warning"))
            with st.form("delete_account_form", clear_on_submit=True):
                confirm_text = st.text_input(t("ui.delete_account_confirm"))
                confirm_submit = st.form_submit_button(t("ui.delete_account_button"), type="primary")

            if confirm_submit:
                if confirm_text.strip() != "DELETE":
                    st.error(t("ui.delete_account_confirm_failed"))
                else:
                    user_id = str(current_user.get("user_id", "")).strip()
                    delete_user_secure_data(user_id=user_id, base_dir=USER_DATA_DIR)

                    user_rules = user_rules_path(user_id)
                    feedback_file = anomaly_feedback_path(user_id)
                    if user_rules.exists():
                        user_rules.unlink(missing_ok=True)
                    if feedback_file.exists():
                        feedback_file.unlink(missing_ok=True)

                    is_deleted = delete_user_account(user_id=user_id, users_path=DEFAULT_USERS_PATH)
                    if is_deleted:
                        clear_authenticated_session()
                        st.success(t("ui.delete_account_success"))
                        st.rerun()
                    else:
                        st.error(t("ui.delete_account_failed"))

        return current_user


def insights_to_dataframe(insights_result: Any, currency: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for insight in insights_result.insights:
        rows.append(
            {
                "code": insight.code,
                "title": insight.title,
                "message": insight.message,
                "action": insight.action,
                "potential_save_minor": int(insight.potential_save_minor),
                f"potential_save_{currency}": float(insight.potential_save_major),
                "severity": insight.severity,
                "metadata": str(insight.metadata),
            }
        )

    return pd.DataFrame(rows)


def render_export_section(report_name: str, export_tables: dict[str, pd.DataFrame], scope_key: str) -> None:
    st.markdown(t("ui.export_title"))

    selected_formats = st.multiselect(
        t("ui.export_formats"),
        options=["csv", "xlsx", "pdf"],
        default=["csv", "xlsx", "pdf"],
        key=f"export_formats::{scope_key}",
    )

    if not selected_formats:
        st.info(t("ui.export_select_one"))
        return

    export_result = export_report_tables(
        report_name=report_name,
        tables=export_tables,
        formats=tuple(selected_formats),
        language=get_current_language(),
    )

    for warning_text in export_result.warnings:
        st.warning(warning_text)

    if export_result.errors:
        for error_text in export_result.errors:
            st.error(error_text)
        return

    if not export_result.artifacts:
        st.info(t("ui.export_no_artifacts"))
        return

    for artifact in export_result.artifacts:
        st.download_button(
            label=t("ui.download", file_name=artifact.file_name),
            data=artifact.content,
            file_name=artifact.file_name,
            mime=artifact.mime_type,
            key=f"download::{scope_key}::{artifact.file_name}",
            use_container_width=True,
        )


def _translate_anomaly_reasons(raw_reasons: str) -> str:
    translated: list[str] = []
    for reason in str(raw_reasons).split(";"):
        cleaned = reason.strip()
        if not cleaned:
            continue
        reason_code = cleaned.split(">")[0].split("<")[0].strip()
        translated.append(t(f"anomaly.reason.{reason_code}"))

    return ", ".join(translated)


def _minor_series_to_major(series: pd.Series) -> pd.Series:
    numeric_series = pd.to_numeric(series, errors="coerce")
    return (numeric_series / 100).round(2)


def render_dashboard_blocks(
    analytics_df: pd.DataFrame,
    amount_column: str,
    display_currency: str,
    budget_scope_key: str,
    anomaly_feedback_file: Path,
    mode: str = "full",
) -> None:
    if analytics_df.empty:
        st.warning(t("ui.no_data_after_filters"))
        return

    export_tables: dict[str, pd.DataFrame] = {}

    expense_col_name = f"{t('ui.col_expense')} ({display_currency})"
    share_col_name = t("ui.col_share")
    amount_col_name = f"{t('ui.col_amount')} ({display_currency})"
    budget_col_name = f"{t('ui.col_budget')} ({display_currency})"
    remaining_col_name = f"{t('ui.col_remaining')} ({display_currency})"

    st.markdown(t("ui.expenses_by_category"))
    category_expenses = aggregate_expenses_by_category(analytics_df, amount_column=amount_column)

    if category_expenses.empty:
        st.info(t("ui.no_expenses_for_category"))
        export_tables["expenses_by_category"] = pd.DataFrame(
            columns=["category", "expense_minor", "expense_major", "share_percent"]
        )
    else:
        category_display = category_expenses[["category", "expense_major", "share_percent"]].rename(
            columns={"expense_major": expense_col_name, "share_percent": share_col_name}
        )
        export_tables["expenses_by_category"] = category_expenses.copy()
        st.dataframe(category_display, use_container_width=True)

        if mode == "full":
            total_expenses_minor = category_expenses["expense_minor"].sum()
            total_expenses_major = total_expenses_minor / 100

            total_income_minor = analytics_df[analytics_df[amount_column] > 0][amount_column].sum()
            total_income_major = total_income_minor / 100
            balance_major = total_income_major - total_expenses_major

            st.markdown("---")
            col1, col2, col3 = st.columns(3)
            col1.metric(t("ui.col_expense"), f"{total_expenses_major:.2f} {display_currency}")
            col2.metric(t("ui.income_period"), f"{total_income_major:.2f} {display_currency}")
            col3.metric(
                t("ui.delta"),
                f"{balance_major:.2f} {display_currency}",
                delta_color="off" if balance_major >= 0 else "inverse",
            )

            pie_chart = (
                alt.Chart(category_expenses)
                .mark_arc()
                .encode(
                    theta=alt.Theta(field="expense_major", type="quantitative"),
                    color=alt.Color(field="category", type="nominal"),
                    tooltip=["category", "expense_major", "share_percent"],
                )
                .properties(height=320)
            )
            st.altair_chart(pie_chart, use_container_width=True)

    if mode == "full":
        st.markdown(t("ui.monthly_trend"))
        st.caption(t("ui.monthly_trend_caption"))
        monthly_expenses = aggregate_monthly_expenses(analytics_df, amount_column=amount_column)

        months_for_comparison = st.selectbox(
            t("ui.months_comparison", currency=display_currency),
            options=[1, 3, 6, 12],
            index=1,
            key=f"months_comparison::{budget_scope_key}",
        )
        comparison = compare_expenses_with_previous_period(
            analytics_df,
            months=months_for_comparison,
            amount_column=amount_column,
        )

        comparison_df = pd.DataFrame(
            [
                {
                    "months": int(comparison.months),
                    "current_total_minor": int(comparison.current_total_minor),
                    "previous_total_minor": int(comparison.previous_total_minor),
                    "delta_minor": int(comparison.delta_minor),
                    "delta_percent": comparison.delta_percent,
                }
            ]
        )
        export_tables["monthly_period_comparison"] = comparison_df
        export_tables["monthly_expenses"] = monthly_expenses.copy()

        kpi_1, kpi_2, kpi_3, kpi_4 = st.columns(4)
        kpi_1.metric(t("ui.current_period"), f"{comparison.current_total_minor / 100:.2f} {display_currency}")
        kpi_2.metric(t("ui.previous_period"), f"{comparison.previous_total_minor / 100:.2f} {display_currency}")

        delta_text = t("ui.not_available") if comparison.delta_percent is None else f"{comparison.delta_percent}%"
        kpi_3.metric(t("ui.delta"), f"{comparison.delta_minor / 100:.2f} {display_currency}", delta=delta_text)

        last_date = pd.to_datetime(analytics_df["date"]).max()
        period_start = last_date - pd.DateOffset(months=months_for_comparison)

        period_income = analytics_df[
            (analytics_df[amount_column] > 0)
            & (pd.to_datetime(analytics_df["date"]) >= period_start)
            & (pd.to_datetime(analytics_df["date"]) <= last_date)
        ][amount_column].sum() / 100
        kpi_4.metric(t("ui.income_period"), f"{period_income:.2f} {display_currency}")

        if monthly_expenses.empty:
            st.info(t("ui.no_monthly_data"))
        else:
            trend_chart = (
                alt.Chart(monthly_expenses)
                .mark_line(point=True)
                .encode(
                    x=alt.X("month_label:N", title=t("ui.month_axis")),
                    y=alt.Y("expense_major:Q", title=t("ui.expenses_axis", currency=display_currency)),
                    tooltip=["month_label", "expense_major"],
                )
                .properties(height=320)
            )
            st.altair_chart(trend_chart, use_container_width=True)

        st.markdown(t("ui.top_merchants"))
        top_merchants = aggregate_top_merchants(analytics_df, limit=10, amount_column=amount_column)
        export_tables["top_merchants"] = top_merchants.copy()

        if top_merchants.empty:
            st.info(t("ui.no_top_merchants"))
        else:
            st.dataframe(
                top_merchants[["merchant", "transactions", "expense_major"]].rename(
                    columns={"expense_major": expense_col_name}
                ),
                use_container_width=True,
            )

        recurring_df = detect_recurring_expenses(analytics_df, amount_column=amount_column)
        export_tables["recurring_expenses"] = recurring_df.copy()
        st.caption(t("ui.recurring_caption"))
        if recurring_df.empty:
            st.info(t("ui.no_recurring"))
        else:
            recurring_display = recurring_df[
                ["merchant", "amount_major", "occurrences", "avg_interval_days", "last_date", "next_expected_date"]
            ].rename(columns={"amount_major": amount_col_name})
            st.dataframe(recurring_display, use_container_width=True)

    st.markdown(t("ui.budget_usage"))
    category_list = category_expenses["category"].tolist() if not category_expenses.empty else []

    budgets_store: dict[str, dict[str, float]] = st.session_state["category_budgets_major_by_scope"]
    scope_budgets = budgets_store.get(budget_scope_key, {})

    with st.expander(t("ui.budget_limits"), expanded=False):
        for category_name in category_list:
            state_key = f"budget_major::{budget_scope_key}::{category_name}"
            existing_value = scope_budgets.get(category_name, 0.0)
            budget_major = st.number_input(
                f"{category_name} ({display_currency})",
                min_value=0.0,
                value=float(existing_value),
                step=10.0,
                format="%.2f",
                key=state_key,
            )
            scope_budgets[category_name] = float(budget_major)

    budgets_store[budget_scope_key] = scope_budgets
    budgets_minor = {category: parse_major_amount_to_minor(value) for category, value in scope_budgets.items()}

    budget_usage = calculate_budget_usage(analytics_df, budgets_minor=budgets_minor, amount_column=amount_column)
    export_tables["budget_usage"] = budget_usage.copy()
    if budget_usage.empty:
        st.info(t("ui.no_budget_data"))
    else:
        budget_display = budget_usage[
            ["category", "expense_major", "budget_major", "usage_percent", "is_over_budget", "remaining_major"]
        ].rename(
            columns={
                "expense_major": expense_col_name,
                "budget_major": budget_col_name,
                "remaining_major": remaining_col_name,
            }
        )
        st.dataframe(budget_display, use_container_width=True)

        exceeded = budget_usage[budget_usage["is_over_budget"]]
        if exceeded.empty:
            st.success(t("ui.no_budget_overruns"))
        else:
            st.error(t("ui.budget_overrun", categories=", ".join(exceeded["category"].astype(str).tolist())))

    if mode == "full":
        st.markdown(t("ui.insights_title"))
        insights_result = generate_financial_insights(
            analytics_df,
            amount_column=amount_column,
            currency=display_currency,
            language=get_current_language(),
        )
        export_tables["insights"] = insights_to_dataframe(insights_result, currency=display_currency)

        insight_metrics_col1, insight_metrics_col2 = st.columns(2)
        insight_metrics_col1.metric(t("ui.insights_metric"), str(insights_result.metadata.get("total_insights", 0)))
        insight_metrics_col2.metric(
            t("ui.savings_metric"),
            f"{insights_result.total_potential_save_major:.2f} {display_currency}",
        )

        if not insights_result.insights:
            st.info(t("ui.no_insights"))
        else:
            for insight in insights_result.insights:
                with st.container(border=True):
                    st.markdown(f"**{insight.title}**")
                    st.write(insight.message)
                    st.caption(
                        t(
                            "ui.insight_action_caption",
                            action=insight.action,
                            amount=insight.potential_save_major,
                            currency=display_currency,
                        )
                    )

        st.markdown(t("ui.anomaly_title"))
        st.caption(t("ui.anomaly_caption"))

        with st.expander(t("ui.anomaly_rules"), expanded=False):
            multiplier_value = st.number_input(
                t("ui.high_amount_multiplier"),
                min_value=1.0,
                value=3.0,
                step=0.5,
                format="%.2f",
                key=f"anomaly_multiplier::{budget_scope_key}",
            )
            rare_ratio_value = st.number_input(
                t("ui.rare_merchant_ratio"),
                min_value=0.0,
                max_value=1.0,
                value=0.05,
                step=0.01,
                format="%.2f",
                key=f"anomaly_rare_ratio::{budget_scope_key}",
            )
            rare_count_value = st.number_input(
                t("ui.rare_merchant_count"),
                min_value=0,
                value=1,
                step=1,
                key=f"anomaly_rare_count::{budget_scope_key}",
            )
            country_gap_value = st.number_input(
                t("ui.country_gap_hours"),
                min_value=1,
                value=48,
                step=1,
                key=f"anomaly_country_gap::{budget_scope_key}",
            )

        anomaly_thresholds = AnomalyThresholds(
            high_amount_multiplier=Decimal(str(multiplier_value)),
            rare_merchant_max_ratio=Decimal(str(rare_ratio_value)),
            rare_merchant_max_tx_count=int(rare_count_value),
            country_switch_max_gap_hours=int(country_gap_value),
        )
        anomaly_result = detect_anomalies(
            analytics_df,
            thresholds=anomaly_thresholds,
            amount_column=amount_column,
        )
        export_tables["anomaly_metadata"] = pd.DataFrame([anomaly_result.metadata])

        flagged = anomaly_result.dataframe[anomaly_result.dataframe["is_anomaly"]].copy()
        if flagged.empty:
            st.info(t("ui.no_anomalies"))
            export_tables["anomaly_flagged"] = pd.DataFrame()
        else:
            flagged["anomaly_reasons"] = flagged["anomaly_reasons"].apply(_translate_anomaly_reasons)

            flagged_display = flagged[
                ["transaction_id", "date", "merchant_display", amount_column, "currency", "country", "anomaly_reasons"]
            ].copy()

            flagged_display[amount_col_name] = _minor_series_to_major(flagged_display[amount_column])
            flagged_display = flagged_display.drop(columns=[amount_column])
            st.dataframe(flagged_display, use_container_width=True)
            export_tables["anomaly_flagged"] = flagged_display.copy()

            feedback_entries = load_anomaly_feedback(anomaly_feedback_file)
            scoped_ids = set(flagged["transaction_id"].astype(str).tolist())
            feedback_summary = summarize_feedback(feedback_entries, transaction_ids=scoped_ids)
            export_tables["anomaly_feedback_summary"] = pd.DataFrame([feedback_summary])

            feedback_col_1, feedback_col_2, feedback_col_3 = st.columns(3)
            feedback_col_1.metric(t("ui.feedback_total"), str(feedback_summary["total_feedback"]))
            feedback_col_2.metric(t("ui.feedback_fraud"), str(feedback_summary["fraud_count"]))
            feedback_col_3.metric(t("ui.feedback_ok"), str(feedback_summary["ok_count"]))

            st.markdown(t("ui.manual_feedback_title"))
            selectable_ids = list(dict.fromkeys(flagged["transaction_id"].astype(str).tolist()))
            selected_tx_id = st.selectbox(
                t("ui.select_anomaly"),
                options=selectable_ids,
                key=f"anomaly_select::{budget_scope_key}",
            )

            selected_tx = flagged[flagged["transaction_id"].astype(str) == selected_tx_id].iloc[0]
            selected_amount = int(selected_tx[amount_column]) if pd.notna(selected_tx[amount_column]) else 0

            col11, col22 = st.columns(2)
            with col11:
                st.markdown("---")
                st.markdown(f"**{t('ui.transaction_id')}:** {str(selected_tx['transaction_id'])}")
                st.markdown(f"**{t('ui.merchant')}:** {str(selected_tx.get('merchant_display', ''))}")
                st.markdown(
                    f"**{t('ui.amount')}:** {round(selected_amount / 100, 2)} {str(selected_tx.get('currency', ''))}"
                )
                st.markdown("---")
            with col22:
                st.markdown("---")
                st.markdown(str(selected_tx.get("anomaly_reasons", "")))
                st.markdown(str(selected_tx.get("country", "")) or "—")
                st.markdown(f"**{t('ui.amount_minor')}:** {selected_amount}")
                st.markdown("---")

            selected_verdict = st.radio(
                t("ui.verdict"),
                options=["ok", "fraud"],
                horizontal=True,
                key=f"anomaly_verdict::{budget_scope_key}",
            )
            feedback_comment = st.text_input(
                t("ui.comment_optional"),
                value="",
                key=f"anomaly_comment::{budget_scope_key}",
            )

            if st.button(t("ui.save_feedback"), type="primary", key=f"anomaly_save::{budget_scope_key}"):
                reasons = [
                    reason.strip() for reason in str(selected_tx.get("anomaly_reasons", "")).split(";") if reason.strip()
                ]
                context = {
                    "scope": budget_scope_key,
                    "amount_column": amount_column,
                    "amount_minor": selected_amount,
                    "currency": str(selected_tx.get("currency", "")),
                    "country": str(selected_tx.get("country", "")),
                    "merchant": str(selected_tx.get("merchant_display", "")),
                }
                is_saved = save_anomaly_feedback(
                    transaction_id=str(selected_tx_id),
                    verdict=selected_verdict,
                    feedback_path=anomaly_feedback_file,
                    reasons=reasons,
                    comment=feedback_comment,
                    context=context,
                )

                if is_saved:
                    st.success(t("ui.feedback_saved"))
                    st.rerun()
                else:
                    st.error(t("ui.feedback_save_failed"))

    render_export_section(
        report_name=f"pfm_{budget_scope_key}_{display_currency}",
        export_tables=export_tables,
        scope_key=budget_scope_key,
    )

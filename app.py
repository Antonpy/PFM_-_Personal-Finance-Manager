from __future__ import annotations

import base64
from decimal import Decimal
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from analytics import (
    ALL_FILTER_VALUE,
    aggregate_expenses_by_category,
    aggregate_monthly_expenses,
    aggregate_top_merchants,
    calculate_budget_usage,
    compare_expenses_with_previous_period,
    convert_transactions_to_base_currency,
    detect_recurring_expenses,
    filter_transactions,
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
    get_user_by_id,
    login_user,
    register_user,
    update_user_consent,
)
from categorizer import categorize_transactions, save_user_rule
from export_utils import export_report_tables
from i18n import normalize_language, tr
from insights import generate_financial_insights
from io_utils import import_transactions
from secure_store import decrypt_dataframe, delete_user_secure_data, encrypt_dataframe, is_aes_available


USER_DATA_DIR = Path("models") / "user_data"

if "ui_language" not in st.session_state:
    st.session_state["ui_language"] = "ru"

CURRENT_LANGUAGE = normalize_language(st.session_state.get("ui_language", "ru"))


def _t(key: str, **kwargs) -> str:
    return tr(key, CURRENT_LANGUAGE, **kwargs)


st.set_page_config(page_title=_t("ui.page_title"), layout="wide")
st.title(_t("ui.main_title"))
st.caption(_t("ui.main_caption"))

if "manual_category_overrides" not in st.session_state:
    st.session_state["manual_category_overrides"] = {}
if "category_budgets_major_by_scope" not in st.session_state:
    st.session_state["category_budgets_major_by_scope"] = {}
if "fx_rates_major_to_base" not in st.session_state:
    st.session_state["fx_rates_major_to_base"] = {}
if "auth_user" not in st.session_state:
    st.session_state["auth_user"] = None
if "auth_encryption_key_b64" not in st.session_state:
    st.session_state["auth_encryption_key_b64"] = ""
if "working_transactions_df" not in st.session_state:
    st.session_state["working_transactions_df"] = None


def _user_rules_path(user_id: str) -> Path:
    return USER_DATA_DIR / f"{str(user_id).strip()}.user_rules.json"


def _anomaly_feedback_path(user_id: str) -> Path:
    return USER_DATA_DIR / f"{str(user_id).strip()}.anomaly_feedback.json"


def _set_authenticated_session(user: dict, encryption_key: bytes) -> None:
    st.session_state["auth_user"] = user
    st.session_state["auth_encryption_key_b64"] = base64.urlsafe_b64encode(encryption_key).decode("utf-8")
    st.session_state["manual_category_overrides"] = {}
    st.session_state["working_transactions_df"] = None


def _clear_authenticated_session() -> None:
    st.session_state["auth_user"] = None
    st.session_state["auth_encryption_key_b64"] = ""
    st.session_state["manual_category_overrides"] = {}
    st.session_state["working_transactions_df"] = None


def _get_session_encryption_key() -> bytes | None:
    key_b64 = str(st.session_state.get("auth_encryption_key_b64", "") or "").strip()
    if not key_b64:
        return None

    try:
        key = base64.urlsafe_b64decode(key_b64.encode("utf-8"))
    except Exception:  # noqa: BLE001
        return None

    return key if len(key) == 32 else None


def _render_language_switcher() -> None:
    with st.sidebar:
        st.markdown(f"## {_t('ui.language_section')}")
        selected_label = st.selectbox(
            _t("ui.language_label"),
            options=[_t("ui.language_ru"), _t("ui.language_en")],
            index=0 if CURRENT_LANGUAGE == "ru" else 1,
            key="language_selector",
        )

        selected_code = "ru" if selected_label == _t("ui.language_ru") else "en"
        if selected_code != CURRENT_LANGUAGE:
            st.session_state["ui_language"] = selected_code
            st.rerun()


def _render_auth_panel() -> dict | None:
    with st.sidebar:
        st.markdown(f"## {_t('ui.account')}")

        current_user = st.session_state.get("auth_user")
        if current_user is None:
            login_tab, register_tab = st.tabs([_t("ui.tab_login"), _t("ui.tab_register")])

            with login_tab:
                with st.form("login_form", clear_on_submit=False):
                    login_email = st.text_input(_t("ui.email"), key="login_email_input")
                    login_password = st.text_input(_t("ui.password"), type="password", key="login_password_input")
                    login_submit = st.form_submit_button(_t("ui.login"), type="primary")

                if login_submit:
                    login_result = login_user(
                        login_email,
                        login_password,
                        users_path=DEFAULT_USERS_PATH,
                        language=CURRENT_LANGUAGE,
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
                            st.error(_t("ui.encryption_key_prepare_failed"))
                        else:
                            _set_authenticated_session(login_result.user, encryption_key)
                            st.success(_t("ui.login_success"))
                            st.rerun()

            with register_tab:
                with st.form("register_form", clear_on_submit=False):
                    register_email = st.text_input(_t("ui.email"), key="register_email_input")
                    register_password = st.text_input(
                        _t("ui.password"),
                        type="password",
                        key="register_password_input",
                    )
                    register_submit = st.form_submit_button(_t("ui.register"), type="primary")

                if register_submit:
                    register_result = register_user(
                        register_email,
                        register_password,
                        users_path=DEFAULT_USERS_PATH,
                        language=CURRENT_LANGUAGE,
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
                            st.error(_t("ui.encryption_key_prepare_partial"))
                        else:
                            _set_authenticated_session(register_result.user, encryption_key)
                            st.success(_t("ui.register_success_logged_in"))
                            st.rerun()

            st.info(_t("ui.auth_required_info"))
            return None

        refreshed_user = get_user_by_id(str(current_user.get("user_id", "")), users_path=DEFAULT_USERS_PATH)
        if refreshed_user is None:
            st.warning(_t("ui.account_not_found"))
            _clear_authenticated_session()
            st.rerun()
            return None

        st.success(_t("ui.logged_in_as", email=refreshed_user.get("email", "")))
        st.caption(_t("ui.user_id", user_id=refreshed_user.get("user_id", "")))

        consent_value = st.checkbox(
            _t("ui.consent_checkbox"),
            value=bool(refreshed_user.get("consent_pii_storage", False)),
            key=f"consent_checkbox::{refreshed_user.get('user_id', '')}",
        )
        if st.button(_t("ui.save_consent"), key=f"consent_save::{refreshed_user.get('user_id', '')}"):
            is_updated = update_user_consent(
                user_id=str(refreshed_user.get("user_id", "")),
                consent_pii_storage=consent_value,
                users_path=DEFAULT_USERS_PATH,
            )
            if is_updated:
                st.success(_t("ui.consent_saved"))
                st.rerun()
            else:
                st.error(_t("ui.consent_save_failed"))

        if st.button(_t("ui.logout"), key=f"logout::{refreshed_user.get('user_id', '')}"):
            _clear_authenticated_session()
            st.rerun()

        with st.expander(_t("ui.delete_account_expander"), expanded=False):
            st.warning(_t("ui.delete_account_warning"))
            with st.form("delete_account_form", clear_on_submit=True):
                confirm_text = st.text_input(_t("ui.delete_account_confirm"))
                confirm_submit = st.form_submit_button(_t("ui.delete_account_button"), type="primary")

            if confirm_submit:
                if confirm_text.strip() != "DELETE":
                    st.error(_t("ui.delete_account_confirm_failed"))
                else:
                    user_id = str(refreshed_user.get("user_id", "")).strip()
                    delete_user_secure_data(user_id=user_id, base_dir=USER_DATA_DIR)

                    user_rules = _user_rules_path(user_id)
                    anomaly_feedback = _anomaly_feedback_path(user_id)
                    if user_rules.exists():
                        user_rules.unlink(missing_ok=True)
                    if anomaly_feedback.exists():
                        anomaly_feedback.unlink(missing_ok=True)

                    is_deleted = delete_user_account(user_id=user_id, users_path=DEFAULT_USERS_PATH)
                    if is_deleted:
                        _clear_authenticated_session()
                        st.success(_t("ui.delete_account_success"))
                        st.rerun()
                    else:
                        st.error(_t("ui.delete_account_failed"))

        return refreshed_user


def _insights_to_dataframe(insights_result, currency: str) -> pd.DataFrame:
    rows = []
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


def _minor_series_to_major(series: pd.Series) -> pd.Series:
    """Convert minor units to major units for UI display only."""
    numeric_series = pd.to_numeric(series, errors="coerce")
    return (numeric_series / 100).round(2)


def _render_export_section(
    report_name: str,
    export_tables: dict[str, pd.DataFrame],
    scope_key: str,
) -> None:
    st.markdown(_t("ui.export_title"))

    selected_formats = st.multiselect(
        _t("ui.export_formats"),
        options=["csv", "xlsx", "pdf"],
        default=["csv", "xlsx", "pdf"],
        key=f"export_formats::{scope_key}",
    )

    if not selected_formats:
        st.info(_t("ui.export_select_one"))
        return

    export_result = export_report_tables(
        report_name=report_name,
        tables=export_tables,
        formats=tuple(selected_formats),
        language=CURRENT_LANGUAGE,
    )

    if export_result.warnings:
        for warning_text in export_result.warnings:
            st.warning(warning_text)

    if export_result.errors:
        for error_text in export_result.errors:
            st.error(error_text)
        return

    #st.json(export_result.metadata)

    if not export_result.artifacts:
        st.info(_t("ui.export_no_artifacts"))
        return

    for artifact in export_result.artifacts:
        st.download_button(
            label=_t("ui.download", file_name=artifact.file_name),
            data=artifact.content,
            file_name=artifact.file_name,
            mime=artifact.mime_type,
            key=f"download::{scope_key}::{artifact.file_name}",
            use_container_width=True,
        )


def _render_dashboard_blocks(
    analytics_df: pd.DataFrame,
    amount_column: str,
    display_currency: str,
    budget_scope_key: str,
    anomaly_feedback_path: Path,
) -> None:
    if analytics_df.empty:
        st.warning(_t("ui.no_data_after_filters"))
        return

    export_tables: dict[str, pd.DataFrame] = {}

    expense_col_name = f"{_t('ui.col_expense')} ({display_currency})"
    share_col_name = _t("ui.col_share")
    amount_col_name = f"{_t('ui.col_amount')} ({display_currency})"
    budget_col_name = f"{_t('ui.col_budget')} ({display_currency})"
    remaining_col_name = f"{_t('ui.col_remaining')} ({display_currency})"

    st.markdown(_t("ui.expenses_by_category"))
    category_expenses = aggregate_expenses_by_category(analytics_df, amount_column=amount_column)

    if category_expenses.empty:
        st.info(_t("ui.no_expenses_for_category"))
        export_tables["expenses_by_category"] = pd.DataFrame(
            columns=["category", "expense_minor", "expense_major", "share_percent"]
        )
    else:
        category_display = category_expenses[["category", "expense_major", "share_percent"]].rename(
            columns={"expense_major": expense_col_name, "share_percent": share_col_name}
        )
        export_tables["expenses_by_category"] = category_expenses.copy()
        st.dataframe(category_display, use_container_width=True)

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

    st.markdown(_t("ui.monthly_trend"))
    st.caption(_t("ui.monthly_trend_caption"))
    monthly_expenses = aggregate_monthly_expenses(analytics_df, amount_column=amount_column)

    months_for_comparison = st.selectbox(
        _t("ui.months_comparison", currency=display_currency),
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
    #kpi_1, kpi_2, kpi_3 = st.columns(3)
    kpi_1.metric(_t("ui.current_period"), f"{comparison.current_total_minor / 100:.2f} {display_currency}")
    kpi_2.metric(_t("ui.previous_period"), f"{comparison.previous_total_minor / 100:.2f} {display_currency}")

    delta_text = _t("ui.not_available") if comparison.delta_percent is None else f"{comparison.delta_percent}%"
    kpi_3.metric(_t("ui.delta"), f"{comparison.delta_minor / 100:.2f} {display_currency}", delta=delta_text)

    last_date = pd.to_datetime(analytics_df['date']).max()
    period_start = last_date - pd.DateOffset(months=months_for_comparison)

    # Доходы за период
    period_income = analytics_df[
                        (analytics_df[amount_column] > 0) &
                        (pd.to_datetime(analytics_df['date']) >= period_start) &
                        (pd.to_datetime(analytics_df['date']) <= last_date)
                        ][amount_column].sum() / 100

    kpi_4.metric(_t("ui.income_period"), f"{period_income:.2f} {display_currency}")

    if monthly_expenses.empty:
        st.info(_t("ui.no_monthly_data"))
    else:
        trend_chart = (
            alt.Chart(monthly_expenses)
            .mark_line(point=True)
            .encode(
                x=alt.X("month_label:N", title=_t("ui.month_axis")),
                y=alt.Y("expense_major:Q", title=_t("ui.expenses_axis", currency=display_currency)),
                tooltip=["month_label", "expense_major"],
            )
            .properties(height=320)
        )
        st.altair_chart(trend_chart, use_container_width=True)

    st.markdown(_t("ui.top_merchants"))
    top_merchants = aggregate_top_merchants(analytics_df, limit=10, amount_column=amount_column)
    export_tables["top_merchants"] = top_merchants.copy()

    if top_merchants.empty:
        st.info(_t("ui.no_top_merchants"))
    else:
        st.dataframe(
            top_merchants[["merchant", "transactions", "expense_major"]].rename(
                columns={"expense_major": expense_col_name}
            ),
            use_container_width=True,
        )

    recurring_df = detect_recurring_expenses(analytics_df, amount_column=amount_column)
    export_tables["recurring_expenses"] = recurring_df.copy()
    st.caption(_t("ui.recurring_caption"))
    if recurring_df.empty:
        st.info(_t("ui.no_recurring"))
    else:
        recurring_display = recurring_df[
            ["merchant", "amount_major", "occurrences", "avg_interval_days", "last_date", "next_expected_date"]
        ].rename(columns={"amount_major": amount_col_name})
        st.dataframe(recurring_display, use_container_width=True)

    st.markdown(_t("ui.budget_usage"))
    category_list = category_expenses["category"].tolist() if not category_expenses.empty else []

    budgets_store: dict[str, dict[str, float]] = st.session_state["category_budgets_major_by_scope"]
    scope_budgets = budgets_store.get(budget_scope_key, {})

    with st.expander(_t("ui.budget_limits"), expanded=False):
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
        st.info(_t("ui.no_budget_data"))
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
            st.success(_t("ui.no_budget_overruns"))
        else:
            st.error(
                _t(
                    "ui.budget_overrun",
                    categories=", ".join(exceeded["category"].astype(str).tolist()),
                )
            )

    st.markdown(_t("ui.insights_title"))
    insights_result = generate_financial_insights(
        analytics_df,
        amount_column=amount_column,
        currency=display_currency,
        language=CURRENT_LANGUAGE,
    )
    export_tables["insights"] = _insights_to_dataframe(insights_result, currency=display_currency)

    insight_metrics_col1, insight_metrics_col2 = st.columns(2)
    insight_metrics_col1.metric(_t("ui.insights_metric"), str(insights_result.metadata.get("total_insights", 0)))
    insight_metrics_col2.metric(
        _t("ui.savings_metric"),
        f"{insights_result.total_potential_save_major:.2f} {display_currency}",
    )

    if not insights_result.insights:
        st.info(_t("ui.no_insights"))
    else:
        for insight in insights_result.insights:
            with st.container(border=True):
                st.markdown(f"**{insight.title}**")
                st.write(insight.message)
                st.caption(
                    _t(
                        "ui.insight_action_caption",
                        action=insight.action,
                        amount=insight.potential_save_major,
                        currency=display_currency,
                    )
                )

    st.markdown(_t("ui.anomaly_title"))
    st.caption(_t("ui.anomaly_caption"))

    with st.expander(_t("ui.anomaly_rules"), expanded=False):
        multiplier_value = st.number_input(
            _t("ui.high_amount_multiplier"),
            min_value=1.0,
            value=3.0,
            step=0.5,
            format="%.2f",
            key=f"anomaly_multiplier::{budget_scope_key}",
        )
        rare_ratio_value = st.number_input(
            _t("ui.rare_merchant_ratio"),
            min_value=0.0,
            max_value=1.0,
            value=0.05,
            step=0.01,
            format="%.2f",
            key=f"anomaly_rare_ratio::{budget_scope_key}",
        )
        rare_count_value = st.number_input(
            _t("ui.rare_merchant_count"),
            min_value=0,
            value=1,
            step=1,
            key=f"anomaly_rare_count::{budget_scope_key}",
        )
        country_gap_value = st.number_input(
            _t("ui.country_gap_hours"),
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

    #st.json(anomaly_result.metadata)
    export_tables["anomaly_metadata"] = pd.DataFrame([anomaly_result.metadata])

    flagged = anomaly_result.dataframe[anomaly_result.dataframe["is_anomaly"]].copy()
    if flagged.empty:
        st.info(_t("ui.no_anomalies"))
        export_tables["anomaly_flagged"] = pd.DataFrame()
    else:
        # Переводим причины используя i18n
        flagged = flagged.copy()
        flagged['anomaly_reasons'] = flagged['anomaly_reasons'].apply(
            lambda x: ', '.join([
                _t(f"anomaly.reason.{r.split('>')[0].split('<')[0].strip()}")  # берём только код до > или <
                for r in str(x).split(';') if r.strip()
            ])
        )

        flagged_display = flagged[
            [
                "transaction_id",
                "date",
                "merchant_display",
                amount_column,
                "currency",
                "country",
                "anomaly_reasons",  # показываем переведённые причины
            ]
        ].copy()

        flagged_display[amount_col_name] = _minor_series_to_major(flagged_display[amount_column])
        flagged_display = flagged_display.drop(columns=[amount_column])
        st.dataframe(flagged_display, use_container_width=True)
        export_tables["anomaly_flagged"] = flagged_display.copy()

        feedback_entries = load_anomaly_feedback(anomaly_feedback_path)
        scoped_ids = set(flagged["transaction_id"].astype(str).tolist())
        feedback_summary = summarize_feedback(feedback_entries, transaction_ids=scoped_ids)

        export_tables["anomaly_feedback_summary"] = pd.DataFrame([feedback_summary])

        feedback_col_1, feedback_col_2, feedback_col_3 = st.columns(3)
        feedback_col_1.metric(_t("ui.feedback_total"), str(feedback_summary["total_feedback"]))
        feedback_col_2.metric(_t("ui.feedback_fraud"), str(feedback_summary["fraud_count"]))
        feedback_col_3.metric(_t("ui.feedback_ok"), str(feedback_summary["ok_count"]))

        st.markdown(_t("ui.manual_feedback_title"))
        selectable_ids = list(dict.fromkeys(flagged["transaction_id"].astype(str).tolist()))
        selected_tx_id = st.selectbox(
            _t("ui.select_anomaly"),
            options=selectable_ids,
            key=f"anomaly_select::{budget_scope_key}",
        )

        selected_tx = flagged[flagged["transaction_id"].astype(str) == selected_tx_id].iloc[0]
        selected_amount = int(selected_tx[amount_column]) if pd.notna(selected_tx[amount_column]) else 0
# ---------------------------------------
        #st.write(
        #    {
        #        "transaction_id": str(selected_tx["transaction_id"]),
        #        "merchant": str(selected_tx.get("merchant_display", "")),
        #        _t("ui.amount_minor"): selected_amount,
        #        _t("ui.amount_major"): round(selected_amount / 100, 2),
        #        "currency": str(selected_tx.get("currency", "")),
        #        "country": str(selected_tx.get("country", "")),
        #        "reasons": str(selected_tx.get("anomaly_reasons", "")),
        #    }
        #)
#---------------------------------------

        col11, col22 = st.columns(2)
        with col11:
            st.markdown("---")
            st.markdown(f"**ID:** {str(selected_tx['transaction_id'])}")
            st.markdown(f"**Merchant:** {str(selected_tx.get('merchant_display', ''))}")
            st.markdown(f"**Amount:** {round(selected_amount / 100, 2)} {str(selected_tx.get('currency', ''))}")
            st.markdown("---")
        with col22:
            st.markdown("---")
            st.markdown(f"**Reasons:** {str(selected_tx.get('anomaly_reasons', ''))}")
            st.markdown(f"**Country:** {str(selected_tx.get('country', '')) or '—'}")
            st.markdown(f"**Minor:** {selected_amount}")
            st.markdown("---")

# ---------------------------------------
        selected_verdict = st.radio(
            _t("ui.verdict"),
            options=["ok", "fraud"],
            horizontal=True,
            key=f"anomaly_verdict::{budget_scope_key}",
        )
        feedback_comment = st.text_input(
            _t("ui.comment_optional"),
            value="",
            key=f"anomaly_comment::{budget_scope_key}",
        )

        if st.button(_t("ui.save_feedback"), type="primary", key=f"anomaly_save::{budget_scope_key}"):
            reasons = [reason.strip() for reason in str(selected_tx.get("anomaly_reasons", "")).split(";") if reason.strip()]
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
                feedback_path=anomaly_feedback_path,
                reasons=reasons,
                comment=feedback_comment,
                context=context,
            )

            if is_saved:
                st.success(_t("ui.feedback_saved"))
                st.rerun()
            else:
                st.error(_t("ui.feedback_save_failed"))

    _render_export_section(
        report_name=f"pfm_{budget_scope_key}_{display_currency}",
        export_tables=export_tables,
        scope_key=budget_scope_key,
    )


_render_language_switcher()
current_user = _render_auth_panel()
if current_user is None:
    st.info(_t("ui.auth_right_panel_info"))
    st.stop()

if not is_aes_available():
    st.error(_t("ui.crypto_unavailable"))

st.warning(_t("ui.pii_warning"))
st.caption(_t("ui.pii_caption"))

user_id = str(current_user.get("user_id", "")).strip()
user_rules_path = _user_rules_path(user_id)
anomaly_feedback_path = _anomaly_feedback_path(user_id)
encryption_key = _get_session_encryption_key()

if encryption_key is None:
    st.error(_t("ui.session_key_unavailable"))
    st.stop()

consent_enabled = bool(current_user.get("consent_pii_storage", False))
if not consent_enabled:
    st.info(_t("ui.consent_disabled_info"))

st.subheader(_t("ui.data_source"))
source_col_1, source_col_2 = st.columns(2)

with source_col_1:
    if st.button(_t("ui.load_encrypted_data"), use_container_width=True):
        decrypt_result = decrypt_dataframe(
            user_id=user_id,
            encryption_key=encryption_key,
            base_dir=USER_DATA_DIR,
            language=CURRENT_LANGUAGE,
        )
        if not decrypt_result.success:
            st.error(decrypt_result.message)
        else:
            loaded_df = decrypt_result.dataframe if decrypt_result.dataframe is not None else pd.DataFrame()
            st.session_state["working_transactions_df"] = loaded_df
            st.success(decrypt_result.message)
            st.rerun()

with source_col_2:
    if st.button(_t("ui.clear_session_data"), use_container_width=True):
        st.session_state["working_transactions_df"] = None
        st.session_state["manual_category_overrides"] = {}
        st.success(_t("ui.session_cleared"))
        st.rerun()

amount_mode_label = st.selectbox(
    _t("ui.amount_mode_select"),
    options=[_t("ui.amount_mode_auto"), _t("ui.amount_mode_major"), _t("ui.amount_mode_minor")],
    index=1,
)
amount_mode_map = {
    _t("ui.amount_mode_auto"): "auto",
    _t("ui.amount_mode_major"): "major",
    _t("ui.amount_mode_minor"): "minor",
}
selected_amount_mode = amount_mode_map[amount_mode_label]

uploaded_file = st.file_uploader(
    _t("ui.upload_file"),
    type=["csv", "xlsx", "xls", "xlsm"],
)

if uploaded_file:
    result = import_transactions(uploaded_file, language=CURRENT_LANGUAGE, amount_mode=selected_amount_mode)

    if result.errors:
        for error_text in result.errors:
            st.error(error_text)
        st.stop()

    if result.warnings:
        st.subheader(_t("ui.import_warnings"))
        for warning_text in result.warnings:
            st.warning(warning_text)

    #if result.metadata:
    #    st.subheader(_t("ui.import_metadata"))
    #    st.json(result.metadata)

    normalized_df = result.dataframe
    if normalized_df is None or normalized_df.empty:
        st.info(_t("ui.empty_after_import"))
        st.stop()

    st.session_state["working_transactions_df"] = normalized_df
    st.session_state["manual_category_overrides"] = {}

    if consent_enabled:
        if st.button(_t("ui.save_encrypted_import"), type="primary"):
            save_result = encrypt_dataframe(
                dataframe=normalized_df,
                user_id=user_id,
                encryption_key=encryption_key,
                base_dir=USER_DATA_DIR,
                language=CURRENT_LANGUAGE,
            )
            if save_result.success:
                st.success(save_result.message)
            else:
                st.error(save_result.message)

working_df = st.session_state.get("working_transactions_df")
if working_df is None or not isinstance(working_df, pd.DataFrame) or working_df.empty:
    st.info(_t("ui.need_data_to_continue"))
    st.stop()

categorized_df, category_meta = categorize_transactions(working_df, rules_path=user_rules_path)

overrides: dict[str, str] = st.session_state["manual_category_overrides"]
if overrides:
    override_mask = categorized_df["transaction_id"].astype(str).isin(overrides)
    categorized_df.loc[override_mask, "category"] = categorized_df.loc[override_mask, "transaction_id"].map(overrides)
    categorized_df.loc[override_mask, "category_source"] = "manual"

st.subheader(_t("ui.categorization_metrics"))
col1, col2, col3 = st.columns(3)
col1.metric(_t("ui.metric_coverage"), f"{category_meta['coverage_percent']}%")
col2.metric(_t("ui.metric_categorized"), str(category_meta["categorized_rows"]))
col3.metric(_t("ui.metric_total"), str(category_meta["total_rows"]))

st.caption(
    _t(
        "ui.rules_priority_caption",
        rules_total=category_meta["rules_total"],
        rules_user=category_meta["rules_user"],
        rules_builtin=category_meta["rules_builtin"],
    )
)

st.subheader(_t("ui.categorized_preview"))
preview_df = categorized_df.head(50).copy()

# Оставляем только нужные колонки
cols_to_show = ['transaction_id', 'date', 'merchant', 'description', 'category']
preview_df = preview_df[[col for col in cols_to_show if col in preview_df.columns]]

if "amount" in categorized_df.columns:
    preview_df[_t("ui.preview_amount_major")] = _minor_series_to_major(categorized_df.head(50)["amount"])

st.dataframe(preview_df, use_container_width=True)

#st.subheader(_t("ui.categorized_preview"))
#preview_df = categorized_df.head(50).copy()
#if "amount" in preview_df.columns:
#    preview_df[_t("ui.preview_amount_major")] = _minor_series_to_major(preview_df["amount"])
#    preview_df = preview_df.drop(columns=["amount"])
#st.dataframe(preview_df, use_container_width=True)

#st.subheader(_t("ui.schema_check"))
#schema_df = pd.DataFrame(
#    {
#        "column": categorized_df.columns,
#        "dtype": [str(dtype) for dtype in categorized_df.dtypes],
#    }
#)
#st.dataframe(schema_df, use_container_width=True)

st.subheader(_t("ui.manual_category_correction"))

row_options = categorized_df.index.tolist()
selected_row_index = st.selectbox(_t("ui.select_transaction_for_edit"), options=row_options, index=0)
selected_row = categorized_df.loc[selected_row_index]

selected_amount_minor = int(selected_row["amount"]) if pd.notna(selected_row["amount"]) else None
selected_amount_major = (selected_amount_minor / 100) if selected_amount_minor is not None else None

col_preview_1, col_preview_2 = st.columns(2)

with col_preview_1:
    st.markdown("---")
    st.markdown(f"<b>{_t('ui.transaction_id')}:</b> {selected_row['transaction_id']}", unsafe_allow_html=True)
    st.markdown(f"<b>{_t('ui.merchant')}:</b> {selected_row['merchant']}", unsafe_allow_html=True)
    st.markdown(f"<b>{_t('ui.description')}:</b> {selected_row['description']}", unsafe_allow_html=True)
    st.markdown("---")

with col_preview_2:
    st.markdown("---")
    st.markdown(f"<b>{_t('ui.amount')}:</b> {selected_amount_major} {selected_row.get('currency', 'RUB')}", unsafe_allow_html=True)
    st.markdown(f"<b>{_t('ui.current_category')}:</b> {selected_row['category']}", unsafe_allow_html=True)
    st.markdown(f"<b>{_t('ui.amount_minor')}:</b> {selected_amount_minor}", unsafe_allow_html=True)
    st.markdown("---")

#st.write(
#    {
#        "transaction_id": selected_row["transaction_id"],
#        "merchant": selected_row["merchant"],
#        "description": selected_row["description"],
#        _t("ui.amount_minor"): selected_amount_minor,
#        _t("ui.amount_major"): selected_amount_major,
#        "current_category": selected_row["category"],
#    }
#)

suggested_pattern = selected_row["merchant"] or selected_row["description"]
corrected_category = st.text_input(
    _t("ui.new_category"),
    value=str(selected_row["category"]),
    help=_t("ui.new_category_help"),
).strip()

pattern_text = st.text_input(
    _t("ui.rule_pattern"),
    value=str(suggested_pattern),
    help=_t("ui.rule_pattern_help"),
).strip()

rule_field = st.selectbox(_t("ui.rule_field"), options=["merchant", "description", "both"], index=0)
rule_match_type = st.selectbox(_t("ui.rule_match_type"), options=["contains", "exact"], index=0)

default_direction = "any"
if pd.notna(selected_row["amount"]):
    default_direction = "income" if int(selected_row["amount"]) > 0 else "expense"
rule_direction = st.selectbox(
    _t("ui.rule_direction"),
    options=["any", "income", "expense"],
    index=["any", "income", "expense"].index(default_direction),
)

col_apply, col_save = st.columns(2)

with col_apply:
    if st.button(_t("ui.apply_local_fix"), use_container_width=True):
        if not corrected_category:
            st.warning(_t("ui.empty_category_warning"))
        else:
            tx_id = str(selected_row["transaction_id"])
            st.session_state["manual_category_overrides"][tx_id] = corrected_category
            st.success(_t("ui.local_fix_applied"))
            st.rerun()

with col_save:
    if st.button(_t("ui.save_rule"), type="primary", use_container_width=True):
        if not corrected_category:
            st.warning(_t("ui.empty_category_before_save"))
        elif not pattern_text:
            st.warning(_t("ui.empty_pattern_warning"))
        else:
            is_added = save_user_rule(
                pattern=pattern_text,
                category=corrected_category,
                field=rule_field,
                match_type=rule_match_type,
                direction=rule_direction,
                rules_path=user_rules_path,
            )
            if is_added:
                st.success(_t("ui.rule_saved"))
            else:
                st.info(_t("ui.rule_exists_or_invalid"))
            st.rerun()

st.subheader(_t("ui.dashboard"))

has_account_column = "account" in categorized_df.columns
selected_account = ALL_FILTER_VALUE
if has_account_column:
    available_accounts = sorted(value for value in categorized_df["account"].dropna().astype(str).unique().tolist() if value)
    account_options = [ALL_FILTER_VALUE, *available_accounts]
    selected_account = st.selectbox(
        _t("ui.account_filter"),
        options=account_options,
        format_func=lambda value: _t("ui.all_accounts") if value == ALL_FILTER_VALUE else value,
    )

base_filtered_df = filter_transactions(
    categorized_df,
    currency=ALL_FILTER_VALUE,
    account=selected_account,
)

if base_filtered_df.empty:
    st.warning(_t("ui.empty_after_account_filter"))
    st.stop()

available_currencies = sorted(
    value for value in base_filtered_df["currency"].dropna().astype(str).str.upper().unique().tolist() if value
)
if not available_currencies:
    st.warning(_t("ui.currency_missing"))
    st.stop()

base_currency_options = sorted(set(["RUB", "USD", "EUR", *available_currencies]))
selected_base_currency = st.selectbox(
    _t("ui.base_currency"),
    options=base_currency_options,
    index=base_currency_options.index("RUB") if "RUB" in base_currency_options else 0,
)

st.markdown(f"#### {_t('ui.manual_rates')}")
st.caption(_t("ui.manual_rates_caption"))

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
            _t("ui.rate_input", from_currency=currency_code, to_currency=selected_base_currency),
            min_value=0.0,
            value=default_rate,
            step=0.01,
            format="%.6f",
            key=f"fx_input::{rate_key}",
        )

    rates_store[rate_key] = float(entered_rate)
    if entered_rate > 0:
        rates_major_to_base[currency_code] = float(entered_rate)

conversion_result = convert_transactions_to_base_currency(
    base_filtered_df,
    base_currency=selected_base_currency,
    rates_major_to_base=rates_major_to_base,
    language=CURRENT_LANGUAGE,
)

for warning_text in conversion_result.warnings:
    st.warning(warning_text)

#st.subheader(_t("ui.fx_metadata"))
#st.json(conversion_result.metadata)

converted_df = conversion_result.dataframe

st.markdown(f"#### {_t('ui.analytics_views')}")
tab_titles = [*available_currencies, _t("ui.consolidated_tab", currency=selected_base_currency)]
tabs = st.tabs(tab_titles)

for currency_code, tab in zip(available_currencies, tabs[:-1]):
    with tab:
        currency_df = filter_transactions(
            base_filtered_df,
            currency=currency_code,
            account=ALL_FILTER_VALUE,
        )
        st.caption(_t("ui.source_currency_analytics", currency=currency_code))
        _render_dashboard_blocks(
            analytics_df=currency_df,
            amount_column="amount",
            display_currency=currency_code,
            budget_scope_key=f"source::{selected_account}::{currency_code}",
            anomaly_feedback_path=anomaly_feedback_path,
        )

with tabs[-1]:
    consolidated_df = converted_df[converted_df["amount_base"].notna()].copy()
    st.caption(_t("ui.consolidated_caption"))

    if consolidated_df.empty:
        st.info(_t("ui.consolidated_empty"))
    else:
        consolidated_display = consolidated_df[
            [
                "transaction_id",
                "date",
                "currency",
                "amount",
                "amount_base",
                "base_currency",
                "merchant",
                "category",
            ]
        ].copy()
        consolidated_display[_t("ui.col_amount_source_major")] = _minor_series_to_major(consolidated_display["amount"])
        consolidated_display[_t("ui.col_amount_base_major", currency=selected_base_currency)] = _minor_series_to_major(
            consolidated_display["amount_base"]
        )
        consolidated_display = consolidated_display.drop(columns=["amount", "amount_base"])

        st.dataframe(
            consolidated_display.head(100),
            use_container_width=True,
        )
        _render_dashboard_blocks(
            analytics_df=consolidated_df,
            amount_column="amount_base",
            display_currency=selected_base_currency,
            budget_scope_key=f"base::{selected_account}::{selected_base_currency}",
            anomaly_feedback_path=anomaly_feedback_path,
        )

st.success(_t("ui.completed"))

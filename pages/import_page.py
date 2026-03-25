from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from handlers import (
    apply_local_category_override,
    clear_session_working_data,
    get_categorized_transactions_df,
    get_working_transactions_df,
    load_encrypted_user_data,
    minor_series_to_major,
    run_import,
    save_category_rule,
    save_encrypted_user_data,
)
from state_manager import t


AMOUNT_MODE_OPTIONS: tuple[str, ...] = ("auto", "major", "minor")


def _amount_mode_label(mode: str) -> str:
    labels = {
        "auto": t("ui.amount_mode_auto"),
        "major": t("ui.amount_mode_major"),
        "minor": t("ui.amount_mode_minor"),
    }
    return labels.get(mode, labels["auto"])


def render_import_page(user_id: str, encryption_key: bytes, consent_enabled: bool, user_rules_file: Path) -> None:
    st.subheader(t("ui.data_source"))
    source_col_1, source_col_2 = st.columns(2)

    with source_col_1:
        if st.button(t("ui.load_encrypted_data"), use_container_width=True):
            decrypt_result = load_encrypted_user_data(
                user_id=user_id,
                encryption_key=encryption_key,
                language=st.session_state.get("ui_language", "ru"),
            )
            if not decrypt_result.success:
                st.error(decrypt_result.message)
            else:
                loaded_df = decrypt_result.dataframe if decrypt_result.dataframe is not None else pd.DataFrame()
                st.session_state["working_transactions_df"] = loaded_df
                st.success(decrypt_result.message)
                st.rerun()

    with source_col_2:
        if st.button(t("ui.clear_session_data"), use_container_width=True):
            clear_session_working_data()
            st.success(t("ui.session_cleared"))
            st.rerun()

    selected_amount_mode = st.selectbox(
        t("ui.amount_mode_select"),
        options=list(AMOUNT_MODE_OPTIONS),
        format_func=_amount_mode_label,
        key="import_amount_mode",
    )

    uploaded_file = st.file_uploader(
        t("ui.upload_file"),
        type=["csv", "xlsx", "xls", "xlsm", "pdf"],
        key="import_page_uploader",
    )

    if uploaded_file:
        result = run_import(
            uploaded_file=uploaded_file,
            language=st.session_state.get("ui_language", "ru"),
            amount_mode=selected_amount_mode,
        )

        if result.errors:
            for error_text in result.errors:
                st.error(error_text)
            return

        if result.warnings:
            st.subheader(t("ui.import_warnings"))
            for warning_text in result.warnings:
                st.warning(warning_text)

        normalized_df = result.dataframe
        if normalized_df is None or normalized_df.empty:
            st.info(t("ui.empty_after_import"))
            return

        if consent_enabled and st.button(t("ui.save_encrypted_import"), type="primary"):
            save_result = save_encrypted_user_data(
                dataframe=normalized_df,
                user_id=user_id,
                encryption_key=encryption_key,
                language=st.session_state.get("ui_language", "ru"),
            )
            if save_result.success:
                st.success(save_result.message)
            else:
                st.error(save_result.message)

    working_df = get_working_transactions_df()
    if working_df is None:
        st.info(t("ui.need_data_to_continue"))
        return

    categorized_df, category_meta = get_categorized_transactions_df(rules_path=user_rules_file)
    if categorized_df is None or categorized_df.empty:
        st.info(t("ui.need_data_to_continue"))
        return

    st.subheader(t("ui.categorization_metrics"))
    col1, col2, col3 = st.columns(3)
    col1.metric(t("ui.metric_coverage"), f"{category_meta['coverage_percent']}%")
    col2.metric(t("ui.metric_categorized"), str(category_meta["categorized_rows"]))
    col3.metric(t("ui.metric_total"), str(category_meta["total_rows"]))

    st.caption(
        t(
            "ui.rules_priority_caption",
            rules_total=category_meta["rules_total"],
            rules_user=category_meta["rules_user"],
            rules_builtin=category_meta["rules_builtin"],
        )
    )

    st.subheader(t("ui.categorized_preview"))
    if "show_all_transactions" not in st.session_state:
        st.session_state["show_all_transactions"] = False

    toggle_label = (
        t("ui.show_all_transactions")
        if not st.session_state["show_all_transactions"]
        else t("ui.show_first_50")
    )
    if st.button(toggle_label, key="toggle_transactions_view"):
        st.session_state["show_all_transactions"] = not st.session_state["show_all_transactions"]
        st.rerun()

    preview_df = categorized_df.copy() if st.session_state["show_all_transactions"] else categorized_df.head(50).copy()
    cols_to_show = ["transaction_id", "date", "merchant", "description", "category", "amount"]
    preview_df = preview_df[[col for col in cols_to_show if col in preview_df.columns]]

    if "amount" in preview_df.columns:
        preview_df[t("ui.preview_amount_major")] = minor_series_to_major(preview_df["amount"])
        preview_df = preview_df.drop(columns=["amount"])

    st.dataframe(preview_df, use_container_width=True)

    st.subheader(t("ui.manual_category_correction"))
    row_options = categorized_df.index.tolist()
    selected_row_index = st.selectbox(t("ui.select_transaction_for_edit"), options=row_options, index=0)
    selected_row = categorized_df.loc[selected_row_index]

    selected_amount_minor = int(selected_row["amount"]) if pd.notna(selected_row["amount"]) else None
    selected_amount_major = (selected_amount_minor / 100) if selected_amount_minor is not None else None

    col_preview_1, col_preview_2 = st.columns(2)
    with col_preview_1:
        st.markdown("---")
        st.markdown(f"<b>{t('ui.transaction_id')}:</b> {selected_row['transaction_id']}", unsafe_allow_html=True)
        st.markdown(f"<b>{t('ui.merchant')}:</b> {selected_row['merchant']}", unsafe_allow_html=True)
        st.markdown(f"<b>{t('ui.description')}:</b> {selected_row['description']}", unsafe_allow_html=True)
        st.markdown("---")

    with col_preview_2:
        st.markdown("---")
        st.markdown(
            f"<b>{t('ui.amount')}:</b> {selected_amount_major} {selected_row.get('currency', 'RUB')}",
            unsafe_allow_html=True,
        )
        st.markdown(f"<b>{t('ui.current_category')}:</b> {selected_row['category']}", unsafe_allow_html=True)
        st.markdown(f"<b>{t('ui.amount_minor')}:</b> {selected_amount_minor}", unsafe_allow_html=True)
        st.markdown("---")

    suggested_pattern = selected_row.get("merchant") or selected_row.get("description")
    corrected_category = st.text_input(
        t("ui.new_category"),
        value=str(selected_row["category"]),
        help=t("ui.new_category_help"),
    ).strip()

    pattern_text = st.text_input(
        t("ui.rule_pattern"),
        value=str(suggested_pattern),
        help=t("ui.rule_pattern_help"),
    ).strip()

    rule_field = st.selectbox(t("ui.rule_field"), options=["merchant", "description", "both"], index=0)
    rule_match_type = st.selectbox(t("ui.rule_match_type"), options=["contains", "exact"], index=0)

    default_direction = "any"
    if pd.notna(selected_row["amount"]):
        default_direction = "income" if int(selected_row["amount"]) > 0 else "expense"
    rule_direction = st.selectbox(
        t("ui.rule_direction"),
        options=["any", "income", "expense"],
        index=["any", "income", "expense"].index(default_direction),
    )

    col_apply, col_save = st.columns(2)
    with col_apply:
        if st.button(t("ui.apply_local_fix"), use_container_width=True):
            if not corrected_category:
                st.warning(t("ui.empty_category_warning"))
            else:
                apply_local_category_override(str(selected_row["transaction_id"]), corrected_category)
                st.success(t("ui.local_fix_applied"))
                st.rerun()

    with col_save:
        if st.button(t("ui.save_rule"), type="primary", use_container_width=True):
            if not corrected_category:
                st.warning(t("ui.empty_category_before_save"))
            elif not pattern_text:
                st.warning(t("ui.empty_pattern_warning"))
            else:
                is_added = save_category_rule(
                    pattern=pattern_text,
                    category=corrected_category,
                    field=rule_field,
                    match_type=rule_match_type,
                    direction=rule_direction,
                    rules_path=user_rules_file,
                )
                if is_added:
                    st.success(t("ui.rule_saved"))
                else:
                    st.info(t("ui.rule_exists_or_invalid"))
                st.rerun()

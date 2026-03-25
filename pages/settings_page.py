from __future__ import annotations

import streamlit as st

from auth import DEFAULT_USERS_PATH, change_user_password, derive_user_encryption_key
from handlers import clear_session_working_data, get_working_transactions_df, update_session_encryption_key
from secure_store import is_aes_available
from state_manager import get_current_language, t


def render_settings_page(user: dict, consent_enabled: bool) -> None:
    st.subheader(t("ui.account"))

    st.markdown(f"**{t('ui.email')}:** {user.get('email', '')}")
    st.markdown(f"**{t('ui.user_id', user_id=user.get('user_id', ''))}**")
    st.markdown(f"**{t('ui.consent_checkbox')}:** {'✅' if consent_enabled else '❌'}")
    st.markdown(f"**AES:** {'✅' if is_aes_available() else '❌'}")

    working_df = get_working_transactions_df()
    row_count = int(working_df.shape[0]) if working_df is not None else 0
    st.caption(f"{t('ui.metric_total')}: {row_count}")

    with st.expander(t("ui.change_password_expander"), expanded=False):
        with st.form("change_password_form", clear_on_submit=True):
            old_password = st.text_input(t("ui.old_password"), type="password")
            new_password = st.text_input(t("ui.new_password"), type="password")
            new_password_confirm = st.text_input(t("ui.confirm_new_password"), type="password")
            change_password_submit = st.form_submit_button(t("ui.change_password_button"), type="primary")

        if change_password_submit:
            if new_password != new_password_confirm:
                st.error(t("ui.new_password_mismatch"))
            else:
                user_id = str(user.get("user_id", "")).strip()
                change_result = change_user_password(
                    user_id=user_id,
                    old_password=old_password,
                    new_password=new_password,
                    users_path=DEFAULT_USERS_PATH,
                    language=get_current_language(),
                )
                if not change_result.success:
                    st.error(change_result.message)
                else:
                    new_encryption_key = derive_user_encryption_key(
                        user_id=user_id,
                        password=new_password,
                        users_path=DEFAULT_USERS_PATH,
                    )
                    if new_encryption_key is None:
                        st.error(t("ui.encryption_key_prepare_failed"))
                    else:
                        update_session_encryption_key(new_encryption_key)
                        st.session_state["auth_user"] = change_result.user or user
                        st.success(change_result.message)
                        st.rerun()

    if st.button(t("ui.clear_session_data"), use_container_width=True):
        clear_session_working_data()
        st.success(t("ui.session_cleared"))
        st.rerun()

    st.info(t("ui.pii_caption"))

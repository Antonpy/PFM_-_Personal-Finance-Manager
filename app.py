from __future__ import annotations

import streamlit as st

from handlers import (
    clear_authenticated_session,
    get_session_encryption_key,
    refresh_authenticated_user,
    user_rules_path,
)
from pages.analytics_page import render_analytics_page
from pages.budgets_page import render_budgets_page
from pages.import_page import render_import_page
from pages.settings_page import render_settings_page
from secure_store import is_aes_available
from state_manager import init_session_state, t
from ui_components import render_auth_panel, render_language_switcher


def _build_navigation(user_id: str, encryption_key: bytes, consent_enabled: bool):
    rules_path = user_rules_path(user_id)

    def _import_page() -> None:
        render_import_page(
            user_id=user_id,
            encryption_key=encryption_key,
            consent_enabled=consent_enabled,
            user_rules_file=rules_path,
        )

    def _analytics_page() -> None:
        render_analytics_page(user_id=user_id, user_rules_file=rules_path)

    def _budgets_page() -> None:
        render_budgets_page(user_id=user_id, user_rules_file=rules_path)

    def _settings_page() -> None:
        current_user = st.session_state.get("auth_user") or {}
        render_settings_page(user=current_user, consent_enabled=consent_enabled)

    return st.navigation(
        [
            st.Page(_import_page, title=t("ui.data_source"), icon="📥"),
            st.Page(_analytics_page, title=t("ui.dashboard"), icon="📊"),
            st.Page(_budgets_page, title=t("ui.budget_usage"), icon="💸"),
            st.Page(_settings_page, title=t("ui.account"), icon="⚙️"),
        ],
        position="sidebar",
    )


def main() -> None:
    init_session_state()

    st.set_page_config(page_title=t("ui.page_title"), layout="wide")
    st.title(t("ui.main_title"))
    st.caption(t("ui.main_caption"))

    render_language_switcher()
    current_user = render_auth_panel()
    if current_user is None:
        st.info(t("ui.auth_right_panel_info"))
        st.stop()

    refreshed_user = refresh_authenticated_user()
    if refreshed_user is None:
        st.warning(t("ui.account_not_found"))
        clear_authenticated_session()
        st.rerun()

    st.session_state["auth_user"] = refreshed_user

    if not is_aes_available():
        st.error(t("ui.crypto_unavailable"))

    st.warning(t("ui.pii_warning"))
    st.caption(t("ui.pii_caption"))

    encryption_key = get_session_encryption_key()
    if encryption_key is None:
        st.error(t("ui.session_key_unavailable"))
        st.stop()

    user_id = str(refreshed_user.get("user_id", "")).strip()
    consent_enabled = bool(refreshed_user.get("consent_pii_storage", False))
    if not consent_enabled:
        st.info(t("ui.consent_disabled_info"))

    navigation = _build_navigation(
        user_id=user_id,
        encryption_key=encryption_key,
        consent_enabled=consent_enabled,
    )
    navigation.run()


if __name__ == "__main__":
    main()

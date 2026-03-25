from __future__ import annotations

from typing import Any

import streamlit as st

from i18n import normalize_language, tr


SESSION_DEFAULTS: dict[str, Any] = {
    "ui_language": "ru",
    "manual_category_overrides": {},
    "category_budgets_major_by_scope": {},
    "fx_rates_major_to_base": {},
    "auth_user": None,
    "auth_encryption_key_b64": "",
    "working_transactions_df": None,
    "show_all_transactions": False,
    "selected_account_filter": None,
    "selected_base_currency": "RUB",
}


def init_session_state() -> None:
    """Initialize required Streamlit session keys with deterministic defaults."""
    for key, value in SESSION_DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = value


def get_current_language() -> str:
    return normalize_language(st.session_state.get("ui_language", "ru"))


def t(key: str, **kwargs: Any) -> str:
    return tr(key, get_current_language(), **kwargs)


def clear_working_data() -> None:
    st.session_state["working_transactions_df"] = None
    st.session_state["manual_category_overrides"] = {}
    st.session_state["show_all_transactions"] = False

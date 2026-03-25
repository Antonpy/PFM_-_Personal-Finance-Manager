from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from auth import DEFAULT_USERS_PATH, get_user_by_id
from categorizer import categorize_transactions, save_user_rule
from io_utils import ImportResult, import_transactions
from secure_store import SecureStoreResult, decrypt_dataframe, encrypt_dataframe


USER_DATA_DIR = Path("models") / "user_data"


def user_rules_path(user_id: str) -> Path:
    return USER_DATA_DIR / f"{str(user_id).strip()}.user_rules.json"


def anomaly_feedback_path(user_id: str) -> Path:
    return USER_DATA_DIR / f"{str(user_id).strip()}.anomaly_feedback.json"


def set_authenticated_session(user: dict[str, Any], encryption_key: bytes) -> None:
    st.session_state["auth_user"] = user
    st.session_state["auth_encryption_key_b64"] = base64.urlsafe_b64encode(encryption_key).decode("utf-8")
    st.session_state["manual_category_overrides"] = {}
    st.session_state["working_transactions_df"] = None


def update_session_encryption_key(encryption_key: bytes) -> None:
    """Обновляет ключ шифрования в сессии без сброса рабочих данных."""
    st.session_state["auth_encryption_key_b64"] = base64.urlsafe_b64encode(encryption_key).decode("utf-8")


def clear_authenticated_session() -> None:
    st.session_state["auth_user"] = None
    st.session_state["auth_encryption_key_b64"] = ""
    st.session_state["manual_category_overrides"] = {}
    st.session_state["working_transactions_df"] = None


def get_session_encryption_key() -> bytes | None:
    key_b64 = str(st.session_state.get("auth_encryption_key_b64", "") or "").strip()
    if not key_b64:
        return None

    try:
        key = base64.urlsafe_b64decode(key_b64.encode("utf-8"))
    except Exception:  # noqa: BLE001
        return None

    return key if len(key) == 32 else None


def refresh_authenticated_user() -> dict[str, Any] | None:
    current_user = st.session_state.get("auth_user")
    if current_user is None:
        return None

    return get_user_by_id(str(current_user.get("user_id", "")), users_path=DEFAULT_USERS_PATH)


def load_encrypted_user_data(user_id: str, encryption_key: bytes, language: str) -> SecureStoreResult:
    return decrypt_dataframe(
        user_id=user_id,
        encryption_key=encryption_key,
        base_dir=USER_DATA_DIR,
        language=language,
    )


def save_encrypted_user_data(
    dataframe: pd.DataFrame,
    user_id: str,
    encryption_key: bytes,
    language: str,
) -> SecureStoreResult:
    return encrypt_dataframe(
        dataframe=dataframe,
        user_id=user_id,
        encryption_key=encryption_key,
        base_dir=USER_DATA_DIR,
        language=language,
    )


def run_import(uploaded_file: Any, language: str, amount_mode: str) -> ImportResult:
    result = import_transactions(uploaded_file, language=language, amount_mode=amount_mode)
    normalized_df = result.dataframe

    if normalized_df is not None and not normalized_df.empty and not result.errors:
        st.session_state["working_transactions_df"] = normalized_df
        st.session_state["manual_category_overrides"] = {}

    return result


def get_working_transactions_df() -> pd.DataFrame | None:
    working_df = st.session_state.get("working_transactions_df")
    if working_df is None or not isinstance(working_df, pd.DataFrame) or working_df.empty:
        return None
    return working_df


def get_categorized_transactions_df(rules_path: Path) -> tuple[pd.DataFrame | None, dict[str, Any]]:
    working_df = get_working_transactions_df()
    if working_df is None:
        return None, {}

    categorized_df, category_meta = categorize_transactions(working_df, rules_path=rules_path)

    overrides: dict[str, str] = st.session_state.get("manual_category_overrides", {})
    if overrides:
        override_mask = categorized_df["transaction_id"].astype(str).isin(overrides)
        categorized_df.loc[override_mask, "category"] = categorized_df.loc[override_mask, "transaction_id"].map(overrides)
        categorized_df.loc[override_mask, "category_source"] = "manual"

    return categorized_df, category_meta


def apply_local_category_override(transaction_id: str, category: str) -> None:
    overrides = st.session_state.get("manual_category_overrides", {})
    overrides[str(transaction_id)] = str(category)
    st.session_state["manual_category_overrides"] = overrides


def save_category_rule(
    pattern: str,
    category: str,
    field: str,
    match_type: str,
    direction: str,
    rules_path: Path,
) -> bool:
    return save_user_rule(
        pattern=pattern,
        category=category,
        field=field,
        match_type=match_type,
        direction=direction,
        rules_path=rules_path,
    )


def minor_series_to_major(series: pd.Series) -> pd.Series:
    numeric_series = pd.to_numeric(series, errors="coerce")
    return (numeric_series / 100).round(2)


def clear_session_working_data() -> None:
    st.session_state["working_transactions_df"] = None
    st.session_state["manual_category_overrides"] = {}
    st.session_state["show_all_transactions"] = False

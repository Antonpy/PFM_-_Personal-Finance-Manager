from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from i18n import tr

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:  # pragma: no cover - зависит от окружения
    AESGCM = None


DEFAULT_USER_DATA_DIR = Path("models") / "user_data"
AES_GCM_NONCE_SIZE = 12


@dataclass(frozen=True)
class SecureStoreResult:
    """Результат операций безопасного хранилища."""

    success: bool
    message: str
    dataframe: pd.DataFrame | None = None
    metadata: dict[str, Any] | None = None


def is_aes_available() -> bool:
    """Показывает, доступна ли AES-реализация через cryptography."""
    return AESGCM is not None


def _user_payload_path(user_id: str, base_dir: str | Path = DEFAULT_USER_DATA_DIR) -> Path:
    normalized_id = str(user_id or "").strip()
    root = Path(base_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{normalized_id}.transactions.enc.json"


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("utf-8")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(str(value).encode("utf-8"))


def _serialize_dataframe(dataframe: pd.DataFrame) -> str:
    prepared = dataframe.copy()

    if "date" in prepared.columns:
        prepared["date"] = pd.to_datetime(prepared["date"], errors="coerce", utc=True)
        prepared["date"] = prepared["date"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    return prepared.to_json(orient="records", force_ascii=False)


def _deserialize_dataframe(payload_json: str) -> pd.DataFrame:
    records = json.loads(payload_json)
    if not isinstance(records, list):
        return pd.DataFrame()

    dataframe = pd.DataFrame(records)
    if "date" in dataframe.columns:
        dataframe["date"] = pd.to_datetime(dataframe["date"], errors="coerce", utc=True)

    if "amount" in dataframe.columns:
        dataframe["amount"] = pd.to_numeric(dataframe["amount"], errors="coerce").astype("Int64")

    if "amount_base" in dataframe.columns:
        dataframe["amount_base"] = pd.to_numeric(dataframe["amount_base"], errors="coerce").astype("Int64")

    return dataframe


def encrypt_dataframe(
    dataframe: pd.DataFrame,
    user_id: str,
    encryption_key: bytes,
    base_dir: str | Path = DEFAULT_USER_DATA_DIR,
    language: str = "ru",
) -> SecureStoreResult:
    """Шифрует DataFrame алгоритмом AES-GCM и сохраняет payload на диск."""
    normalized_id = str(user_id or "").strip()
    if not normalized_id:
        return SecureStoreResult(success=False, message=tr("secure.invalid_user_id", language))

    if not encryption_key or len(encryption_key) != 32:
        return SecureStoreResult(success=False, message=tr("secure.invalid_key", language))

    if not is_aes_available():
        return SecureStoreResult(success=False, message=tr("secure.aes_unavailable", language))

    payload_path = _user_payload_path(normalized_id, base_dir=base_dir)
    aesgcm = AESGCM(encryption_key)
    nonce = os.urandom(AES_GCM_NONCE_SIZE)

    serialized = _serialize_dataframe(dataframe)
    ciphertext = aesgcm.encrypt(nonce, serialized.encode("utf-8"), normalized_id.encode("utf-8"))

    payload = {
        "version": 1,
        "algorithm": "AES-256-GCM",
        "user_id": normalized_id,
        "updated_at": datetime.now(UTC).isoformat(),
        "nonce_b64": _encode(nonce),
        "ciphertext_b64": _encode(ciphertext),
    }

    payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return SecureStoreResult(
        success=True,
        message=tr("secure.saved", language),
        metadata={"path": str(payload_path), "rows": int(dataframe.shape[0])},
    )


def decrypt_dataframe(
    user_id: str,
    encryption_key: bytes,
    base_dir: str | Path = DEFAULT_USER_DATA_DIR,
    language: str = "ru",
) -> SecureStoreResult:
    """Загружает и расшифровывает ранее сохранённый DataFrame пользователя."""
    normalized_id = str(user_id or "").strip()
    if not normalized_id:
        return SecureStoreResult(success=False, message=tr("secure.invalid_user_id", language))

    if not encryption_key or len(encryption_key) != 32:
        return SecureStoreResult(success=False, message=tr("secure.invalid_key", language))

    if not is_aes_available():
        return SecureStoreResult(success=False, message=tr("secure.aes_unavailable", language))

    payload_path = _user_payload_path(normalized_id, base_dir=base_dir)
    if not payload_path.exists():
        return SecureStoreResult(success=True, message=tr("secure.not_found", language), dataframe=pd.DataFrame())

    try:
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return SecureStoreResult(success=False, message=tr("secure.corrupted_file", language))

    nonce_b64 = str(payload.get("nonce_b64", "")).strip()
    ciphertext_b64 = str(payload.get("ciphertext_b64", "")).strip()
    if not nonce_b64 or not ciphertext_b64:
        return SecureStoreResult(success=False, message=tr("secure.invalid_encrypted_format", language))

    try:
        nonce = _decode(nonce_b64)
        ciphertext = _decode(ciphertext_b64)
    except Exception:  # noqa: BLE001
        return SecureStoreResult(success=False, message=tr("secure.invalid_base64", language))

    if len(nonce) != AES_GCM_NONCE_SIZE:
        return SecureStoreResult(success=False, message=tr("secure.invalid_nonce", language))

    aesgcm = AESGCM(encryption_key)
    try:
        decrypted = aesgcm.decrypt(nonce, ciphertext, normalized_id.encode("utf-8"))
    except Exception:  # noqa: BLE001
        return SecureStoreResult(success=False, message=tr("secure.decrypt_failed", language))

    try:
        dataframe = _deserialize_dataframe(decrypted.decode("utf-8"))
    except Exception:  # noqa: BLE001
        return SecureStoreResult(success=False, message=tr("secure.deserialize_failed", language))

    return SecureStoreResult(
        success=True,
        message=tr("secure.loaded", language),
        dataframe=dataframe,
        metadata={"path": str(payload_path), "rows": int(dataframe.shape[0])},
    )


def delete_user_secure_data(user_id: str, base_dir: str | Path = DEFAULT_USER_DATA_DIR) -> bool:
    """Удаляет зашифрованные транзакции пользователя."""
    normalized_id = str(user_id or "").strip()
    if not normalized_id:
        return False

    payload_path = _user_payload_path(normalized_id, base_dir=base_dir)
    if not payload_path.exists():
        return True

    payload_path.unlink(missing_ok=True)
    return True

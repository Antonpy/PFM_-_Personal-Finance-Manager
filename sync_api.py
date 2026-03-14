from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from auth import DEFAULT_USERS_PATH, derive_user_encryption_key, login_user
from i18n import tr
from secure_store import is_aes_available

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:  # pragma: no cover - зависит от окружения
    AESGCM = None


DEFAULT_SYNC_STATE_PATH = Path("models") / "sync_state.json"
SYNC_SCHEMA_VERSION = 1
AES_GCM_NONCE_SIZE = 12
MAX_DEVICE_ID_LENGTH = 128
MAX_USER_ID_LENGTH = 128


@dataclass(frozen=True)
class SyncApiResult:
    """Результат обработки sync API запроса."""

    success: bool
    status_code: int
    body: dict[str, Any] = field(default_factory=dict)


def _state_path(sync_state_path: str | Path = DEFAULT_SYNC_STATE_PATH) -> Path:
    path = Path(sync_state_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _load_state(sync_state_path: str | Path = DEFAULT_SYNC_STATE_PATH) -> list[dict[str, Any]]:
    path = _state_path(sync_state_path)
    if not path.exists():
        return []

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []

    if not isinstance(payload, list):
        return []

    return [item for item in payload if isinstance(item, dict)]


def _save_state(records: list[dict[str, Any]], sync_state_path: str | Path = DEFAULT_SYNC_STATE_PATH) -> None:
    path = _state_path(sync_state_path)
    path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


def _normalize_text(value: Any, max_length: int) -> str:
    normalized = str(value or "").strip()
    return normalized[:max_length]


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _validate_push_request(request: dict[str, Any], language: str) -> list[str]:
    errors: list[str] = []

    schema_version = request.get("schema_version")
    if schema_version != SYNC_SCHEMA_VERSION:
        errors.append(tr("sync.schema_version_error", language, version=SYNC_SCHEMA_VERSION))

    user_id = _normalize_text(request.get("user_id"), MAX_USER_ID_LENGTH)
    if not user_id:
        errors.append(tr("sync.user_id_required", language))

    device_id = _normalize_text(request.get("device_id"), MAX_DEVICE_ID_LENGTH)
    if not device_id:
        errors.append(tr("sync.device_id_required", language))

    try:
        client_revision = int(request.get("client_revision"))
    except (TypeError, ValueError):
        client_revision = -1

    if client_revision < 0:
        errors.append(tr("sync.client_revision_error", language))

    payload = request.get("payload")
    if payload is None:
        errors.append(tr("sync.payload_required", language))

    return errors


def _validate_pull_request(request: dict[str, Any], language: str) -> list[str]:
    errors: list[str] = []

    schema_version = request.get("schema_version")
    if schema_version != SYNC_SCHEMA_VERSION:
        errors.append(tr("sync.schema_version_error", language, version=SYNC_SCHEMA_VERSION))

    user_id = _normalize_text(request.get("user_id"), MAX_USER_ID_LENGTH)
    if not user_id:
        errors.append(tr("sync.user_id_required", language))

    since_revision = request.get("since_revision", -1)
    try:
        since_revision_value = int(since_revision)
    except (TypeError, ValueError):
        since_revision_value = -2

    if since_revision_value < -1:
        errors.append(tr("sync.since_revision_error", language))

    return errors


def _authenticate(email: str, password: str, user_id: str, users_path: str | Path, language: str) -> tuple[bool, str]:
    auth_result = login_user(email=email, password=password, users_path=users_path, language=language)
    if not auth_result.success or auth_result.user is None:
        return False, tr("sync.auth_failed", language)

    auth_user_id = str(auth_result.user.get("user_id", "")).strip()
    if auth_user_id != str(user_id).strip():
        return False, tr("sync.auth_user_mismatch", language)

    return True, ""


def _derive_storage_key(user_id: str, password: str, users_path: str | Path) -> bytes | None:
    return derive_user_encryption_key(user_id=user_id, password=password, users_path=users_path)


def _encrypt_payload(payload_json: str, key: bytes, aad: bytes) -> tuple[str, str]:
    aesgcm = AESGCM(key)
    nonce = os.urandom(AES_GCM_NONCE_SIZE)
    ciphertext = aesgcm.encrypt(nonce, payload_json.encode("utf-8"), aad)
    return base64.urlsafe_b64encode(nonce).decode("utf-8"), base64.urlsafe_b64encode(ciphertext).decode("utf-8")


def _decrypt_payload(nonce_b64: str, ciphertext_b64: str, key: bytes, aad: bytes) -> dict[str, Any] | None:
    try:
        nonce = base64.urlsafe_b64decode(nonce_b64.encode("utf-8"))
        ciphertext = base64.urlsafe_b64decode(ciphertext_b64.encode("utf-8"))
    except Exception:  # noqa: BLE001
        return None

    if len(nonce) != AES_GCM_NONCE_SIZE:
        return None

    aesgcm = AESGCM(key)
    try:
        decrypted = aesgcm.decrypt(nonce, ciphertext, aad)
    except Exception:  # noqa: BLE001
        return None

    try:
        parsed = json.loads(decrypted.decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None

    return parsed if isinstance(parsed, dict) else None


def push_sync_payload(
    request: dict[str, Any],
    email: str,
    password: str,
    users_path: str | Path = DEFAULT_USERS_PATH,
    sync_state_path: str | Path = DEFAULT_SYNC_STATE_PATH,
    language: str = "en",
) -> SyncApiResult:
    """
    Versioned push endpoint для синхронизации между устройствами.

    Идемпотентность: upsert по ключу (user_id, device_id, client_revision).
    """
    validation_errors = _validate_push_request(request, language=language)
    if validation_errors:
        return SyncApiResult(
            success=False,
            status_code=400,
            body={"errors": validation_errors, "schema_version": SYNC_SCHEMA_VERSION},
        )

    if not is_aes_available() or AESGCM is None:
        return SyncApiResult(
            success=False,
            status_code=503,
            body={"errors": [tr("sync.aes_unavailable", language)]},
        )

    user_id = _normalize_text(request.get("user_id"), MAX_USER_ID_LENGTH)
    device_id = _normalize_text(request.get("device_id"), MAX_DEVICE_ID_LENGTH)
    client_revision = int(request.get("client_revision"))
    payload = request.get("payload")
    payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    is_authenticated, auth_error = _authenticate(
        email=email,
        password=password,
        user_id=user_id,
        users_path=users_path,
        language=language,
    )
    if not is_authenticated:
        return SyncApiResult(success=False, status_code=401, body={"errors": [auth_error]})

    storage_key = _derive_storage_key(user_id=user_id, password=password, users_path=users_path)
    if storage_key is None:
        return SyncApiResult(
            success=False,
            status_code=500,
            body={"errors": [tr("sync.key_derive_failed", language)]},
        )

    aad = f"{user_id}:{device_id}:{client_revision}".encode("utf-8")
    nonce_b64, ciphertext_b64 = _encrypt_payload(payload_json=payload_json, key=storage_key, aad=aad)
    payload_hash = _sha256_hex(payload_json.encode("utf-8"))

    records = _load_state(sync_state_path)
    now_iso = datetime.now(UTC).isoformat()

    updated_index: int | None = None
    for index, item in enumerate(records):
        if (
            str(item.get("user_id", "")).strip() == user_id
            and str(item.get("device_id", "")).strip() == device_id
            and int(item.get("client_revision", -1)) == client_revision
        ):
            updated_index = index
            break

    status = "created"
    if updated_index is not None:
        previous_hash = str(records[updated_index].get("payload_hash", "")).strip()
        status = "noop" if previous_hash == payload_hash else "updated"
        records[updated_index] = {
            "schema_version": SYNC_SCHEMA_VERSION,
            "user_id": user_id,
            "device_id": device_id,
            "client_revision": client_revision,
            "payload_hash": payload_hash,
            "nonce_b64": nonce_b64,
            "ciphertext_b64": ciphertext_b64,
            "updated_at": now_iso,
        }
    else:
        records.append(
            {
                "schema_version": SYNC_SCHEMA_VERSION,
                "user_id": user_id,
                "device_id": device_id,
                "client_revision": client_revision,
                "payload_hash": payload_hash,
                "nonce_b64": nonce_b64,
                "ciphertext_b64": ciphertext_b64,
                "updated_at": now_iso,
            }
        )

    _save_state(records, sync_state_path)

    return SyncApiResult(
        success=True,
        status_code=200,
        body={
            "status": status,
            "schema_version": SYNC_SCHEMA_VERSION,
            "user_id": user_id,
            "device_id": device_id,
            "client_revision": client_revision,
            "payload_hash": payload_hash,
            "updated_at": now_iso,
        },
    )


def pull_sync_payload(
    request: dict[str, Any],
    email: str,
    password: str,
    users_path: str | Path = DEFAULT_USERS_PATH,
    sync_state_path: str | Path = DEFAULT_SYNC_STATE_PATH,
    language: str = "en",
) -> SyncApiResult:
    """
    Versioned pull endpoint для получения синхронизированных payload между устройствами.

    Возвращает все записи пользователя, где client_revision > since_revision.
    """
    validation_errors = _validate_pull_request(request, language=language)
    if validation_errors:
        return SyncApiResult(
            success=False,
            status_code=400,
            body={"errors": validation_errors, "schema_version": SYNC_SCHEMA_VERSION},
        )

    if not is_aes_available() or AESGCM is None:
        return SyncApiResult(
            success=False,
            status_code=503,
            body={"errors": [tr("sync.aes_unavailable", language)]},
        )

    user_id = _normalize_text(request.get("user_id"), MAX_USER_ID_LENGTH)
    since_revision = int(request.get("since_revision", -1))

    is_authenticated, auth_error = _authenticate(
        email=email,
        password=password,
        user_id=user_id,
        users_path=users_path,
        language=language,
    )
    if not is_authenticated:
        return SyncApiResult(success=False, status_code=401, body={"errors": [auth_error]})

    storage_key = _derive_storage_key(user_id=user_id, password=password, users_path=users_path)
    if storage_key is None:
        return SyncApiResult(
            success=False,
            status_code=500,
            body={"errors": [tr("sync.key_derive_failed", language)]},
        )

    records = _load_state(sync_state_path)

    scoped_records = [
        item
        for item in records
        if str(item.get("user_id", "")).strip() == user_id and int(item.get("client_revision", -1)) > since_revision
    ]
    scoped_records.sort(key=lambda item: int(item.get("client_revision", -1)))

    payloads: list[dict[str, Any]] = []
    skipped_records = 0

    for item in scoped_records:
        device_id = str(item.get("device_id", "")).strip()
        client_revision = int(item.get("client_revision", -1))
        aad = f"{user_id}:{device_id}:{client_revision}".encode("utf-8")

        decrypted_payload = _decrypt_payload(
            nonce_b64=str(item.get("nonce_b64", "")),
            ciphertext_b64=str(item.get("ciphertext_b64", "")),
            key=storage_key,
            aad=aad,
        )
        if decrypted_payload is None:
            skipped_records += 1
            continue

        payloads.append(
            {
                "schema_version": SYNC_SCHEMA_VERSION,
                "user_id": user_id,
                "device_id": device_id,
                "client_revision": client_revision,
                "payload": decrypted_payload,
                "payload_hash": str(item.get("payload_hash", "")),
                "updated_at": str(item.get("updated_at", "")),
            }
        )

    return SyncApiResult(
        success=True,
        status_code=200,
        body={
            "schema_version": SYNC_SCHEMA_VERSION,
            "user_id": user_id,
            "since_revision": since_revision,
            "records": payloads,
            "records_count": len(payloads),
            "skipped_records": skipped_records,
        },
    )

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from i18n import tr


DEFAULT_USERS_PATH = Path("models") / "users.json"
PBKDF2_ITERATIONS = 310_000
ENCRYPTION_KEY_ITERATIONS = 210_000
PASSWORD_MIN_LENGTH = 10


@dataclass(frozen=True)
class AuthResult:
    """Результат попытки регистрации или входа пользователя."""

    success: bool
    message: str
    user: dict[str, Any] | None = None


def normalize_email(email: str) -> str:
    """Нормализует email для безопасного и стабильного сравнения."""
    return str(email or "").strip().lower()


def is_valid_email(email: str) -> bool:
    """Проверяет базовую корректность email формата."""
    normalized = normalize_email(email)
    if len(normalized) < 5 or len(normalized) > 254:
        return False

    return re.match(r"^[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}$", normalized) is not None


def validate_password_policy(password: str, language: str = "ru") -> tuple[bool, str]:
    """Проверяет пароль по минимальной политике безопасности."""
    value = str(password or "")
    if len(value) < PASSWORD_MIN_LENGTH:
        return False, tr("auth.password_min_length", language, min_len=PASSWORD_MIN_LENGTH)
    if not re.search(r"[A-ZА-Я]", value):
        return False, tr("auth.password_need_upper", language)
    if not re.search(r"[a-zа-я]", value):
        return False, tr("auth.password_need_lower", language)
    if not re.search(r"\d", value):
        return False, tr("auth.password_need_digit", language)
    return True, ""


def _hash_password(password: str, salt: bytes, iterations: int = PBKDF2_ITERATIONS) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256",
        str(password).encode("utf-8"),
        salt,
        int(iterations),
        dklen=32,
    )


def _users_payload_path(users_path: str | Path = DEFAULT_USERS_PATH) -> Path:
    path = Path(users_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_users(users_path: str | Path = DEFAULT_USERS_PATH) -> list[dict[str, Any]]:
    """Загружает список пользователей; при повреждении JSON возвращает пустой список."""
    path = _users_payload_path(users_path)
    if not path.exists():
        return []

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []

    if not isinstance(payload, list):
        return []

    return [entry for entry in payload if isinstance(entry, dict)]


def _save_users(users: list[dict[str, Any]], users_path: str | Path = DEFAULT_USERS_PATH) -> None:
    path = _users_payload_path(users_path)
    path.write_text(json.dumps(users, ensure_ascii=False, indent=2), encoding="utf-8")


def _public_user_record(record: dict[str, Any]) -> dict[str, Any]:
    """Возвращает безопасное представление пользователя без хэша пароля."""
    return {
        "user_id": str(record.get("user_id", "")),
        "email": normalize_email(str(record.get("email", ""))),
        "created_at": str(record.get("created_at", "")),
        "consent_pii_storage": bool(record.get("consent_pii_storage", False)),
        "consent_at": str(record.get("consent_at", "")),
    }


def _find_user_by_email(users: list[dict[str, Any]], email: str) -> dict[str, Any] | None:
    normalized = normalize_email(email)
    for user in users:
        if normalize_email(str(user.get("email", ""))) == normalized:
            return user
    return None


def _find_user_by_id(users: list[dict[str, Any]], user_id: str) -> dict[str, Any] | None:
    normalized_id = str(user_id or "").strip()
    for user in users:
        if str(user.get("user_id", "")).strip() == normalized_id:
            return user
    return None


def register_user(
    email: str,
    password: str,
    users_path: str | Path = DEFAULT_USERS_PATH,
    language: str = "ru",
) -> AuthResult:
    """Регистрирует нового пользователя с PBKDF2-хэшированием пароля."""
    normalized_email = normalize_email(email)
    if not is_valid_email(normalized_email):
        return AuthResult(success=False, message=tr("auth.invalid_email_register", language))

    password_ok, password_message = validate_password_policy(password, language=language)
    if not password_ok:
        return AuthResult(success=False, message=password_message)

    users = load_users(users_path)
    existing = _find_user_by_email(users, normalized_email)
    if existing is not None:
        return AuthResult(success=False, message=tr("auth.user_exists", language))

    salt = secrets.token_bytes(16)
    encryption_salt = secrets.token_bytes(16)
    password_hash = _hash_password(password=password, salt=salt, iterations=PBKDF2_ITERATIONS)

    created_record = {
        "user_id": str(uuid.uuid4()),
        "email": normalized_email,
        "password_alg": "pbkdf2_sha256",
        "password_iterations": PBKDF2_ITERATIONS,
        "password_salt_hex": salt.hex(),
        "password_hash_hex": password_hash.hex(),
        "encryption_kdf": "pbkdf2_sha256",
        "encryption_iterations": ENCRYPTION_KEY_ITERATIONS,
        "encryption_salt_hex": encryption_salt.hex(),
        "created_at": datetime.now(UTC).isoformat(),
        "consent_pii_storage": False,
        "consent_at": "",
    }
    users.append(created_record)
    _save_users(users, users_path)

    return AuthResult(
        success=True,
        message=tr("auth.register_success", language),
        user=_public_user_record(created_record),
    )


def login_user(
    email: str,
    password: str,
    users_path: str | Path = DEFAULT_USERS_PATH,
    language: str = "ru",
) -> AuthResult:
    """Проверяет email+пароль и возвращает публичный профиль пользователя."""
    normalized_email = normalize_email(email)
    if not is_valid_email(normalized_email):
        return AuthResult(success=False, message=tr("auth.invalid_email_login", language))

    users = load_users(users_path)
    existing = _find_user_by_email(users, normalized_email)
    if existing is None:
        return AuthResult(success=False, message=tr("auth.user_not_found", language))

    if str(existing.get("password_alg", "")).strip().lower() != "pbkdf2_sha256":
        return AuthResult(success=False, message=tr("auth.unsupported_account_format", language))

    try:
        iterations = int(existing.get("password_iterations", PBKDF2_ITERATIONS))
        salt = bytes.fromhex(str(existing.get("password_salt_hex", "")))
        stored_hash = bytes.fromhex(str(existing.get("password_hash_hex", "")))
    except (TypeError, ValueError):
        return AuthResult(success=False, message=tr("auth.account_data_corrupted", language))

    computed_hash = _hash_password(password=password, salt=salt, iterations=iterations)
    if not hmac.compare_digest(stored_hash, computed_hash):
        return AuthResult(success=False, message=tr("auth.wrong_password", language))

    return AuthResult(
        success=True,
        message=tr("auth.login_success", language),
        user=_public_user_record(existing),
    )


def derive_user_encryption_key(
    user_id: str,
    password: str,
    users_path: str | Path = DEFAULT_USERS_PATH,
) -> bytes | None:
    """Производит AES-ключ из пользовательского пароля и индивидуальной соли."""
    normalized_id = str(user_id or "").strip()
    if not normalized_id or not password:
        return None

    users = load_users(users_path)
    user = _find_user_by_id(users, normalized_id)
    if user is None:
        return None

    try:
        encryption_salt = bytes.fromhex(str(user.get("encryption_salt_hex", "")))
        encryption_iterations = int(user.get("encryption_iterations", ENCRYPTION_KEY_ITERATIONS))
    except (TypeError, ValueError):
        return None

    return hashlib.pbkdf2_hmac(
        "sha256",
        str(password).encode("utf-8"),
        encryption_salt,
        encryption_iterations,
        dklen=32,
    )


def get_user_by_id(user_id: str, users_path: str | Path = DEFAULT_USERS_PATH) -> dict[str, Any] | None:
    """Ищет пользователя по идентификатору и возвращает публичный профиль."""
    normalized_id = str(user_id or "").strip()
    if not normalized_id:
        return None

    users = load_users(users_path)
    user = _find_user_by_id(users, normalized_id)
    if user is None:
        return None

    return _public_user_record(user)


def update_user_consent(
    user_id: str,
    consent_pii_storage: bool,
    users_path: str | Path = DEFAULT_USERS_PATH,
) -> bool:
    """Обновляет согласие пользователя на хранение банковских данных/PII."""
    normalized_id = str(user_id or "").strip()
    if not normalized_id:
        return False

    users = load_users(users_path)
    updated = False

    for index, user in enumerate(users):
        if str(user.get("user_id", "")).strip() != normalized_id:
            continue

        users[index]["consent_pii_storage"] = bool(consent_pii_storage)
        users[index]["consent_at"] = datetime.now(UTC).isoformat()
        updated = True
        break

    if not updated:
        return False

    _save_users(users, users_path)
    return True


def delete_user_account(user_id: str, users_path: str | Path = DEFAULT_USERS_PATH) -> bool:
    """Удаляет учётную запись пользователя из хранилища аккаунтов."""
    normalized_id = str(user_id or "").strip()
    if not normalized_id:
        return False

    users = load_users(users_path)
    filtered = [user for user in users if str(user.get("user_id", "")).strip() != normalized_id]

    if len(filtered) == len(users):
        return False

    _save_users(filtered, users_path)
    return True

import tempfile
import unittest
from pathlib import Path

from auth import (
    DEFAULT_USERS_PATH,
    delete_user_account,
    derive_user_encryption_key,
    get_user_by_id,
    login_user,
    register_user,
    update_user_consent,
)


class TestAuth(unittest.TestCase):
    def test_register_and_login_success(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            users_path = Path(tmp_dir) / "users.json"

            register_result = register_user(
                email="user@example.com",
                password="StrongPass123",
                users_path=users_path,
            )
            self.assertTrue(register_result.success)
            self.assertIsNotNone(register_result.user)

            login_result = login_user(
                email="user@example.com",
                password="StrongPass123",
                users_path=users_path,
            )
            self.assertTrue(login_result.success)
            self.assertIsNotNone(login_result.user)
            self.assertEqual(login_result.user.get("email"), "user@example.com")

    def test_register_rejects_weak_password(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            users_path = Path(tmp_dir) / "users.json"

            register_result = register_user(
                email="user@example.com",
                password="weak",
                users_path=users_path,
            )
            self.assertFalse(register_result.success)
            self.assertIn("Пароль", register_result.message)

    def test_login_rejects_wrong_password(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            users_path = Path(tmp_dir) / "users.json"

            register_result = register_user(
                email="user@example.com",
                password="StrongPass123",
                users_path=users_path,
            )
            self.assertTrue(register_result.success)

            login_result = login_user(
                email="user@example.com",
                password="WrongPass123",
                users_path=users_path,
            )
            self.assertFalse(login_result.success)
            self.assertIn("Неверный пароль", login_result.message)

    def test_consent_update_and_get_user(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            users_path = Path(tmp_dir) / "users.json"

            register_result = register_user(
                email="user@example.com",
                password="StrongPass123",
                users_path=users_path,
            )
            self.assertTrue(register_result.success)
            user = register_result.user or {}
            user_id = str(user.get("user_id", ""))

            is_updated = update_user_consent(
                user_id=user_id,
                consent_pii_storage=True,
                users_path=users_path,
            )
            self.assertTrue(is_updated)

            refreshed = get_user_by_id(user_id=user_id, users_path=users_path)
            self.assertIsNotNone(refreshed)
            self.assertTrue(bool(refreshed.get("consent_pii_storage")))

    def test_derive_encryption_key_is_deterministic_for_same_user_and_password(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            users_path = Path(tmp_dir) / "users.json"

            register_result = register_user(
                email="user@example.com",
                password="StrongPass123",
                users_path=users_path,
            )
            self.assertTrue(register_result.success)
            user = register_result.user or {}
            user_id = str(user.get("user_id", ""))

            key_1 = derive_user_encryption_key(
                user_id=user_id,
                password="StrongPass123",
                users_path=users_path,
            )
            key_2 = derive_user_encryption_key(
                user_id=user_id,
                password="StrongPass123",
                users_path=users_path,
            )
            key_3 = derive_user_encryption_key(
                user_id=user_id,
                password="OtherPass123",
                users_path=users_path,
            )

            self.assertIsNotNone(key_1)
            self.assertIsNotNone(key_2)
            self.assertEqual(key_1, key_2)
            self.assertNotEqual(key_1, key_3)
            self.assertEqual(len(key_1 or b""), 32)

    def test_delete_user_account(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            users_path = Path(tmp_dir) / "users.json"

            register_result = register_user(
                email="user@example.com",
                password="StrongPass123",
                users_path=users_path,
            )
            self.assertTrue(register_result.success)
            user = register_result.user or {}
            user_id = str(user.get("user_id", ""))

            deleted = delete_user_account(user_id=user_id, users_path=users_path)
            self.assertTrue(deleted)

            lookup = get_user_by_id(user_id=user_id, users_path=users_path)
            self.assertIsNone(lookup)


if __name__ == "__main__":
    unittest.main()

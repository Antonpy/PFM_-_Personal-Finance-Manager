import tempfile
import unittest
from pathlib import Path

import pandas as pd

from auth import (
    DEFAULT_USERS_PATH,
    change_user_password,
    delete_user_account,
    derive_user_encryption_key,
    get_user_by_id,
    login_user,
    register_user,
    update_user_consent,
)
from secure_store import decrypt_dataframe, encrypt_dataframe, is_aes_available


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

    def test_change_password_updates_login_and_encryption_key_without_payload(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            users_path = Path(tmp_dir) / "users.json"
            encrypted_dir = Path(tmp_dir) / "user_data"

            register_result = register_user(
                email="rotate@example.com",
                password="StrongPass123",
                users_path=users_path,
            )
            self.assertTrue(register_result.success)
            user = register_result.user or {}
            user_id = str(user.get("user_id", ""))

            old_key = derive_user_encryption_key(
                user_id=user_id,
                password="StrongPass123",
                users_path=users_path,
            )
            self.assertIsNotNone(old_key)

            change_result = change_user_password(
                user_id=user_id,
                old_password="StrongPass123",
                new_password="NewStrongPass456",
                users_path=users_path,
                encrypted_data_dir=encrypted_dir,
            )
            self.assertTrue(change_result.success)

            old_login = login_user(
                email="rotate@example.com",
                password="StrongPass123",
                users_path=users_path,
            )
            self.assertFalse(old_login.success)

            new_login = login_user(
                email="rotate@example.com",
                password="NewStrongPass456",
                users_path=users_path,
            )
            self.assertTrue(new_login.success)

            new_key = derive_user_encryption_key(
                user_id=user_id,
                password="NewStrongPass456",
                users_path=users_path,
            )
            self.assertIsNotNone(new_key)
            self.assertNotEqual(old_key, new_key)

    @unittest.skipUnless(is_aes_available(), "cryptography/AES недоступны в окружении")
    def test_change_password_reencrypts_existing_payload(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            users_path = Path(tmp_dir) / "users.json"
            encrypted_dir = Path(tmp_dir) / "user_data"

            register_result = register_user(
                email="secure@example.com",
                password="StrongPass123",
                users_path=users_path,
            )
            self.assertTrue(register_result.success)
            user = register_result.user or {}
            user_id = str(user.get("user_id", ""))

            old_key = derive_user_encryption_key(
                user_id=user_id,
                password="StrongPass123",
                users_path=users_path,
            )
            self.assertIsNotNone(old_key)

            source_df = pd.DataFrame(
                [
                    {
                        "transaction_id": "tx-1",
                        "date": "2026-01-10",
                        "amount": -1550,
                        "currency": "RUB",
                        "merchant": "Netflix",
                        "description": "Subscription",
                    }
                ]
            )
            encrypted = encrypt_dataframe(
                dataframe=source_df,
                user_id=user_id,
                encryption_key=old_key or b"",
                base_dir=encrypted_dir,
            )
            self.assertTrue(encrypted.success)

            change_result = change_user_password(
                user_id=user_id,
                old_password="StrongPass123",
                new_password="NewStrongPass456",
                users_path=users_path,
                encrypted_data_dir=encrypted_dir,
            )
            self.assertTrue(change_result.success)

            old_decrypt = decrypt_dataframe(
                user_id=user_id,
                encryption_key=old_key or b"",
                base_dir=encrypted_dir,
            )
            self.assertFalse(old_decrypt.success)

            new_key = derive_user_encryption_key(
                user_id=user_id,
                password="NewStrongPass456",
                users_path=users_path,
            )
            self.assertIsNotNone(new_key)

            new_decrypt = decrypt_dataframe(
                user_id=user_id,
                encryption_key=new_key or b"",
                base_dir=encrypted_dir,
            )
            self.assertTrue(new_decrypt.success)
            self.assertIsNotNone(new_decrypt.dataframe)
            self.assertEqual(int(new_decrypt.dataframe.iloc[0]["amount"]), -1550)

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

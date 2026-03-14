import tempfile
import unittest
from pathlib import Path

import pandas as pd

from secure_store import (
    decrypt_dataframe,
    delete_user_secure_data,
    encrypt_dataframe,
    is_aes_available,
)


@unittest.skipUnless(is_aes_available(), "cryptography/AES недоступны в окружении")
class TestSecureStore(unittest.TestCase):
    def _build_df(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "transaction_id": "1",
                    "date": "2026-01-01",
                    "amount": -12345,
                    "currency": "RUB",
                    "merchant": "Пятёрочка",
                    "description": "Продукты",
                },
                {
                    "transaction_id": "2",
                    "date": "2026-01-02",
                    "amount": 150000,
                    "currency": "RUB",
                    "merchant": "Employer",
                    "description": "Salary",
                },
            ]
        )

    def test_encrypt_then_decrypt_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir) / "user_data"
            key = b"k" * 32
            user_id = "user-1"

            source_df = self._build_df()
            encrypted = encrypt_dataframe(
                dataframe=source_df,
                user_id=user_id,
                encryption_key=key,
                base_dir=base_dir,
            )

            self.assertTrue(encrypted.success)

            decrypted = decrypt_dataframe(
                user_id=user_id,
                encryption_key=key,
                base_dir=base_dir,
            )
            self.assertTrue(decrypted.success)
            self.assertIsNotNone(decrypted.dataframe)

            restored = decrypted.dataframe
            self.assertEqual(restored.shape[0], source_df.shape[0])
            self.assertEqual(int(restored.loc[0, "amount"]), -12345)
            self.assertEqual(str(restored.loc[0, "currency"]), "RUB")

    def test_decrypt_with_wrong_key_fails(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir) / "user_data"
            key = b"k" * 32
            wrong_key = b"z" * 32
            user_id = "user-2"

            source_df = self._build_df()
            encrypted = encrypt_dataframe(
                dataframe=source_df,
                user_id=user_id,
                encryption_key=key,
                base_dir=base_dir,
            )
            self.assertTrue(encrypted.success)

            decrypted = decrypt_dataframe(
                user_id=user_id,
                encryption_key=wrong_key,
                base_dir=base_dir,
            )
            self.assertFalse(decrypted.success)

    def test_delete_user_secure_data(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir) / "user_data"
            key = b"k" * 32
            user_id = "user-3"

            source_df = self._build_df()
            encrypted = encrypt_dataframe(
                dataframe=source_df,
                user_id=user_id,
                encryption_key=key,
                base_dir=base_dir,
            )
            self.assertTrue(encrypted.success)

            deleted = delete_user_secure_data(user_id=user_id, base_dir=base_dir)
            self.assertTrue(deleted)

            decrypted = decrypt_dataframe(
                user_id=user_id,
                encryption_key=key,
                base_dir=base_dir,
            )
            self.assertTrue(decrypted.success)
            self.assertIsNotNone(decrypted.dataframe)
            self.assertTrue(decrypted.dataframe.empty)


if __name__ == "__main__":
    unittest.main()

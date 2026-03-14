import io
import tempfile
import unittest
from pathlib import Path

from auth import login_user, register_user
from i18n import DEFAULT_LANGUAGE, normalize_language, tr
from io_utils import import_transactions


class TestI18N(unittest.TestCase):
    def test_normalize_language_defaults_to_ru(self):
        self.assertEqual(normalize_language(None), DEFAULT_LANGUAGE)
        self.assertEqual(normalize_language(""), DEFAULT_LANGUAGE)
        self.assertEqual(normalize_language("de"), DEFAULT_LANGUAGE)
        self.assertEqual(normalize_language("EN"), "en")
        self.assertEqual(normalize_language("ru"), "ru")

    def test_translation_fallback_to_key_when_unknown(self):
        unknown_key = "unknown.translation.key"
        self.assertEqual(tr(unknown_key, "ru"), unknown_key)
        self.assertEqual(tr(unknown_key, "en"), unknown_key)

    def test_auth_messages_support_english(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            users_path = Path(tmp_dir) / "users.json"

            weak_password_result = register_user(
                email="user@example.com",
                password="weak",
                users_path=users_path,
                language="en",
            )
            self.assertFalse(weak_password_result.success)
            self.assertIn("Password", weak_password_result.message)

            register_ok = register_user(
                email="user@example.com",
                password="StrongPass123",
                users_path=users_path,
                language="en",
            )
            self.assertTrue(register_ok.success)

            login_fail = login_user(
                email="user@example.com",
                password="WrongPass123",
                users_path=users_path,
                language="en",
            )
            self.assertFalse(login_fail.success)
            self.assertIn("Wrong password", login_fail.message)

    def test_import_messages_support_english(self):
        csv_text = "merchant,description\nStore,Only text\n"
        uploaded = io.BytesIO(csv_text.encode("utf-8"))
        uploaded.name = "broken.csv"

        result = import_transactions(uploaded, language="en")

        self.assertIsNone(result.dataframe)
        self.assertTrue(any("Required columns are missing" in error for error in result.errors))


if __name__ == "__main__":
    unittest.main()

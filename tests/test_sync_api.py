import tempfile
import unittest
from pathlib import Path

from auth import register_user
from secure_store import is_aes_available
from sync_api import pull_sync_payload, push_sync_payload


@unittest.skipUnless(is_aes_available(), "cryptography/AES недоступны в окружении")
class TestSyncApi(unittest.TestCase):
    def _register_user(self, users_path: Path) -> dict:
        register_result = register_user(
            email="sync_user@example.com",
            password="StrongPass123",
            users_path=users_path,
        )
        self.assertTrue(register_result.success)
        self.assertIsNotNone(register_result.user)
        return register_result.user or {}

    def test_push_then_pull_success(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            users_path = Path(tmp_dir) / "users.json"
            sync_state_path = Path(tmp_dir) / "sync_state.json"

            user = self._register_user(users_path)
            user_id = str(user.get("user_id", ""))

            push_request = {
                "schema_version": 1,
                "user_id": user_id,
                "device_id": "device-a",
                "client_revision": 1,
                "payload": {
                    "transactions": [{"transaction_id": "t1", "amount": -1000}],
                    "metadata": {"source": "mobile"},
                },
            }
            push_result = push_sync_payload(
                request=push_request,
                email="sync_user@example.com",
                password="StrongPass123",
                users_path=users_path,
                sync_state_path=sync_state_path,
            )

            self.assertTrue(push_result.success)
            self.assertEqual(push_result.status_code, 200)
            self.assertEqual(push_result.body.get("status"), "created")

            pull_request = {
                "schema_version": 1,
                "user_id": user_id,
                "since_revision": -1,
            }
            pull_result = pull_sync_payload(
                request=pull_request,
                email="sync_user@example.com",
                password="StrongPass123",
                users_path=users_path,
                sync_state_path=sync_state_path,
            )

            self.assertTrue(pull_result.success)
            self.assertEqual(pull_result.status_code, 200)
            self.assertEqual(int(pull_result.body.get("records_count", 0)), 1)

            records = pull_result.body.get("records", [])
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].get("device_id"), "device-a")
            self.assertEqual(int(records[0].get("client_revision", -1)), 1)
            self.assertEqual(records[0].get("payload"), push_request["payload"])

    def test_push_idempotent_noop_for_same_revision_and_payload(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            users_path = Path(tmp_dir) / "users.json"
            sync_state_path = Path(tmp_dir) / "sync_state.json"

            user = self._register_user(users_path)
            user_id = str(user.get("user_id", ""))

            request = {
                "schema_version": 1,
                "user_id": user_id,
                "device_id": "device-a",
                "client_revision": 5,
                "payload": {"sample": "value"},
            }

            first_push = push_sync_payload(
                request=request,
                email="sync_user@example.com",
                password="StrongPass123",
                users_path=users_path,
                sync_state_path=sync_state_path,
            )
            second_push = push_sync_payload(
                request=request,
                email="sync_user@example.com",
                password="StrongPass123",
                users_path=users_path,
                sync_state_path=sync_state_path,
            )

            self.assertTrue(first_push.success)
            self.assertTrue(second_push.success)
            self.assertEqual(first_push.body.get("status"), "created")
            self.assertEqual(second_push.body.get("status"), "noop")

            pull_result = pull_sync_payload(
                request={
                    "schema_version": 1,
                    "user_id": user_id,
                    "since_revision": -1,
                },
                email="sync_user@example.com",
                password="StrongPass123",
                users_path=users_path,
                sync_state_path=sync_state_path,
            )

            self.assertTrue(pull_result.success)
            self.assertEqual(int(pull_result.body.get("records_count", 0)), 1)

    def test_push_validation_errors_are_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            users_path = Path(tmp_dir) / "users.json"
            sync_state_path = Path(tmp_dir) / "sync_state.json"

            _ = self._register_user(users_path)

            invalid_request = {
                "schema_version": 999,
                "user_id": "",
                "device_id": "",
                "client_revision": -2,
            }

            result = push_sync_payload(
                request=invalid_request,
                email="sync_user@example.com",
                password="StrongPass123",
                users_path=users_path,
                sync_state_path=sync_state_path,
            )

            self.assertFalse(result.success)
            self.assertEqual(result.status_code, 400)
            errors = result.body.get("errors", [])
            self.assertIn("schema_version must be 1.", errors)
            self.assertIn("user_id is required.", errors)
            self.assertIn("device_id is required.", errors)
            self.assertIn("client_revision must be a non-negative integer.", errors)
            self.assertIn("payload is required.", errors)

    def test_authentication_failure_returns_401(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            users_path = Path(tmp_dir) / "users.json"
            sync_state_path = Path(tmp_dir) / "sync_state.json"

            user = self._register_user(users_path)
            user_id = str(user.get("user_id", ""))

            request = {
                "schema_version": 1,
                "user_id": user_id,
                "device_id": "device-a",
                "client_revision": 1,
                "payload": {"sample": 1},
            }

            result = push_sync_payload(
                request=request,
                email="sync_user@example.com",
                password="WrongPass123",
                users_path=users_path,
                sync_state_path=sync_state_path,
            )

            self.assertFalse(result.success)
            self.assertEqual(result.status_code, 401)
            self.assertIn("Authentication failed.", result.body.get("errors", []))


if __name__ == "__main__":
    unittest.main()

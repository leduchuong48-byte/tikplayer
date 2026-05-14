import base64
import json
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

import main


class TokenRefreshPersistenceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)

        self.originals = {
            "DATA_DIR": main.DATA_DIR,
            "TOKEN_STORE_FILE": main.TOKEN_STORE_FILE,
            "TOKEN_KEY_FILE": main.TOKEN_KEY_FILE,
            "persisted_tokens": main.persisted_tokens,
            "token_cache": main.token_cache,
            "token_cipher": main.token_cipher,
        }
        self.addCleanup(self._restore_globals)

        main.DATA_DIR = self.tempdir.name
        main.TOKEN_STORE_FILE = os.path.join(self.tempdir.name, "tokens.json")
        main.TOKEN_KEY_FILE = os.path.join(self.tempdir.name, "token.key")
        main.persisted_tokens = {}
        main.token_cache = {}
        main.token_cipher = None
        main._load_or_create_token_cipher()

        self.base_url = "https://api.openai.com/v1"
        self.username = "demo"
        self.password = "secret"
        self.cache_key = main._token_cache_key(self.base_url, self.username, self.password)

    def _restore_globals(self):
        main.DATA_DIR = self.originals["DATA_DIR"]
        main.TOKEN_STORE_FILE = self.originals["TOKEN_STORE_FILE"]
        main.TOKEN_KEY_FILE = self.originals["TOKEN_KEY_FILE"]
        main.persisted_tokens = self.originals["persisted_tokens"]
        main.token_cache = self.originals["token_cache"]
        main.token_cipher = self.originals["token_cipher"]

    def _make_jwt(self, exp):
        def encode(payload):
            raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("utf-8")

        return f"{encode({'alg': 'none', 'typ': 'JWT'})}.{encode({'exp': int(exp)})}.sig"

    def _write_legacy_store(self, token_text):
        with open(main.TOKEN_STORE_FILE, "w", encoding="utf-8") as fh:
            json.dump({self.cache_key: token_text}, fh)

    async def test_load_persisted_tokens_migrates_legacy_string_record(self):
        now = 1_700_000_000
        jwt_token = self._make_jwt(now + 7200)
        self._write_legacy_store(main._encrypt_token(jwt_token))

        with patch("main.time.time", return_value=now):
            main._load_persisted_tokens()

        stored = main.persisted_tokens[self.cache_key]
        self.assertIsInstance(stored, dict)
        self.assertEqual(main._get_persisted_token(self.base_url, self.username, self.password), jwt_token)
        self.assertEqual(int(stored["expires_at"]), now + 7200)
        self.assertLess(float(stored["refresh_after"]), float(stored["expires_at"]))

    async def test_get_source_token_pre_refreshes_and_persists_new_token(self):
        now = 1_700_100_000
        main.persisted_tokens[self.cache_key] = {
            "token": main._encrypt_token("old-token"),
            "updated_at": now - 600,
            "expires_at": now + 1800,
            "refresh_after": now - 5,
            "last_error": "",
        }
        main._save_persisted_tokens()

        login_mock = AsyncMock(return_value=("new-token", None, {"expires_at": now + 7200}))

        with patch("main.time.time", return_value=now), patch.object(
            main.AlistHelper, "login_with_error", login_mock
        ), patch.object(main.AlistHelper, "validate_token", AsyncMock(return_value=True)):
            token, err = await main.get_source_token(object(), self.base_url, self.username, self.password)

        self.assertEqual(token, "new-token")
        self.assertIsNone(err)
        self.assertEqual(main._get_persisted_token(self.base_url, self.username, self.password), "new-token")
        stored = main.persisted_tokens[self.cache_key]
        self.assertGreater(float(stored["refresh_after"]), now)
        login_mock.assert_awaited_once()

    async def test_get_source_token_keeps_unexpired_token_when_pre_refresh_fails(self):
        now = 1_700_200_000
        main.persisted_tokens[self.cache_key] = {
            "token": main._encrypt_token("still-valid"),
            "updated_at": now - 600,
            "expires_at": now + 900,
            "refresh_after": now - 5,
            "last_error": "",
        }
        main._save_persisted_tokens()

        with patch("main.time.time", return_value=now), patch.object(
            main.AlistHelper,
            "login_with_error",
            AsyncMock(return_value=(None, "refresh failed", {"last_error": "refresh failed"})),
        ), patch.object(main.AlistHelper, "validate_token", AsyncMock(return_value=True)):
            token, err = await main.get_source_token(object(), self.base_url, self.username, self.password)

        self.assertEqual(token, "still-valid")
        self.assertIsNone(err)
        self.assertEqual(main.persisted_tokens[self.cache_key]["last_error"], "refresh failed")

    async def test_get_source_token_rejects_expired_token_when_refresh_fails(self):
        now = 1_700_300_000
        main.persisted_tokens[self.cache_key] = {
            "token": main._encrypt_token("expired-token"),
            "updated_at": now - 3600,
            "expires_at": now - 1,
            "refresh_after": now - 600,
            "last_error": "",
        }
        main._save_persisted_tokens()

        with patch("main.time.time", return_value=now), patch.object(
            main.AlistHelper,
            "login_with_error",
            AsyncMock(return_value=(None, "refresh failed", {"last_error": "refresh failed"})),
        ):
            token, err = await main.get_source_token(object(), self.base_url, self.username, self.password)

        self.assertIsNone(token)
        self.assertEqual(err, "refresh failed")
        self.assertNotIn(self.cache_key, main.persisted_tokens)

    async def test_refreshable_token_error_recognizes_expired_messages(self):
        self.assertTrue(main._is_refreshable_token_error("token is invalidated"))
        self.assertTrue(main._is_refreshable_token_error("token is expired"))
        self.assertFalse(main._is_refreshable_token_error("object not found"))


if __name__ == "__main__":
    unittest.main()

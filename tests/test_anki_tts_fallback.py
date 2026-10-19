"""Exercise the optional Anki add-on against isolated player/backend fixtures."""

import importlib.util
import itertools
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, call, patch


ADDON = Path(__file__).resolve().parents[1] / "anki_addons" / "lilt_windows_tts_fallback" / "__init__.py"
MODULE_IDS = itertools.count()
MISSING_VOICES = 'WindowsError { code: HRESULT(0x80070002), message: "The system cannot find the file specified." }'


class FakeBackendError(Exception):
    pass


def player_fixture(backend):
    """Mirror Anki's cached voices, validation and per-player ranking calls.

    Both players must be ranked even if SAPI already has a matching voice. That
    is why failure in the second player's enumeration formerly blocked SAPI.
    """
    sapi_voice = SimpleNamespace(name="Microsoft_David", lang="en_US")

    class TTSPlayer:
        default_rank = 0

        def __init__(self):
            self._available_voices = None

        def voices(self):
            if self._available_voices is None:
                self._available_voices = self.get_available_voices()
            return self._available_voices

        def rank_for_tag(self, tag):
            voices = self.voices()
            rank = self.default_rank
            for requested in tag.voices:
                for voice in voices:
                    if voice.name == requested and voice.lang == tag.lang:
                        return rank
                rank -= 1
            for voice in voices:
                if voice.lang == tag.lang:
                    return -100
            return None

    class WindowsTTSPlayer(TTSPlayer):
        default_rank = -1

        def get_available_voices(self):
            return [sapi_voice]

    class WindowsRTTTSFilePlayer(TTSPlayer):
        @staticmethod
        def _get_available_voices(validate):
            return backend(validate=validate)

        @classmethod
        def get_available_voices(cls):
            return cls._get_available_voices(validate=False)

        def validated_voices(self):
            self._available_voices = self._get_available_voices(validate=True)
            return self._available_voices

    tts = ModuleType("aqt.tts")
    tts.WindowsTTSPlayer = WindowsTTSPlayer
    tts.WindowsRTTTSFilePlayer = WindowsRTTTSFilePlayer
    return tts


def load_addon(tts, platform="win32"):
    anki, errors, aqt = ModuleType("anki"), ModuleType("anki.errors"), ModuleType("aqt")
    errors.BackendError = FakeBackendError
    anki.errors = errors
    aqt.tts = tts
    fake_modules = {"anki": anki, "anki.errors": errors, "aqt": aqt, "aqt.tts": tts}
    name = f"_lilt_tts_fallback_test_{next(MODULE_IDS)}"
    spec = importlib.util.spec_from_file_location(name, ADDON)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, fake_modules), patch.object(sys, "platform", platform):
        spec.loader.exec_module(module)
    return module, fake_modules


class AnkiTtsFallbackTests(unittest.TestCase):
    def test_healthy_enumeration_preserves_result_and_both_validation_modes(self):
        voices = [SimpleNamespace(name="Microsoft_Jenny", lang="en_US")]
        backend = Mock(return_value=voices)
        tts = player_fixture(backend)
        load_addon(tts)
        player = tts.WindowsRTTTSFilePlayer()
        self.assertIs(player.get_available_voices(), voices)
        self.assertIs(player.validated_voices(), voices)
        self.assertEqual(backend.call_args_list, [call(validate=False), call(validate=True)])

    def test_missing_windows_voice_files_return_empty_for_normal_and_validated_paths(self):
        backend = Mock(side_effect=FakeBackendError(MISSING_VOICES))
        tts = player_fixture(backend)
        addon, _ = load_addon(tts)
        player = tts.WindowsRTTTSFilePlayer()
        with self.assertLogs(addon.__name__, level="WARNING"):
            self.assertEqual(player.get_available_voices(), [])
            self.assertEqual(player.validated_voices(), [])
        self.assertEqual(backend.call_args_list, [call(validate=False), call(validate=True)])

    def test_sapi_player_is_selected_after_broken_winrt_player_is_also_ranked(self):
        backend = Mock(side_effect=FakeBackendError(MISSING_VOICES))
        tts = player_fixture(backend)
        tag = SimpleNamespace(lang="en_US", voices=[])
        # Before the add-on, choosing a winner fails despite healthy SAPI.
        with self.assertRaises(FakeBackendError):
            for player in [tts.WindowsTTSPlayer(), tts.WindowsRTTTSFilePlayer()]:
                player.rank_for_tag(tag)
        backend.reset_mock()
        addon, _ = load_addon(tts)
        sapi, winrt = tts.WindowsTTSPlayer(), tts.WindowsRTTTSFilePlayer()
        with self.assertLogs(addon.__name__, level="WARNING"):
            ranked = [(rank, player) for player in [sapi, winrt]
                      if (rank := player.rank_for_tag(tag)) is not None]
        self.assertIs(max(ranked, key=lambda pair: pair[0])[1], sapi)
        backend.assert_called_once_with(validate=False)

    def test_unrelated_backend_errors_are_propagated_unchanged(self):
        for message in (
            "WindowsError { code: HRESULT(0x80070005), message: Access denied }",
            "Database error while reading voice information",
            "File not found: 0x80070002",
            "WindowsError without the missing-file HRESULT",
        ):
            with self.subTest(message=message):
                error = FakeBackendError(message)
                backend = Mock(side_effect=error)
                tts = player_fixture(backend)
                load_addon(tts)
                with self.assertRaises(FakeBackendError) as caught:
                    tts.WindowsRTTTSFilePlayer.get_available_voices()
                self.assertIs(caught.exception, error)

    def test_non_backend_exceptions_are_not_hidden_even_with_matching_message(self):
        for error_type in (OSError, RuntimeError, TypeError):
            with self.subTest(error_type=error_type):
                error = error_type(MISSING_VOICES)
                tts = player_fixture(Mock(side_effect=error))
                load_addon(tts)
                with self.assertRaises(error_type) as caught:
                    tts.WindowsRTTTSFilePlayer.get_available_voices()
                self.assertIs(caught.exception, error)

    def test_install_and_module_reload_are_idempotent(self):
        voices = [SimpleNamespace(name="voice", lang="en_US")]
        backend = Mock(return_value=voices)
        tts = player_fixture(backend)
        addon, fake_modules = load_addon(tts)
        installed = tts.WindowsRTTTSFilePlayer._get_available_voices
        with patch.dict(sys.modules, fake_modules), patch.object(sys, "platform", "win32"):
            self.assertTrue(addon.install())
            self.assertTrue(addon.install())
        load_addon(tts)
        self.assertIs(tts.WindowsRTTTSFilePlayer._get_available_voices, installed)
        self.assertIs(tts.WindowsRTTTSFilePlayer.get_available_voices(), voices)
        backend.assert_called_once_with(validate=False)

    def test_missing_or_changed_player_api_is_a_noop(self):
        for player in (None, type("MissingMethod", (), {}), type("NotCallable", (), {"_get_available_voices": None})):
            with self.subTest(player=player):
                tts = ModuleType("aqt.tts")
                if player is not None:
                    tts.WindowsRTTTSFilePlayer = player
                addon, fake_modules = load_addon(tts)
                with patch.dict(sys.modules, fake_modules), patch.object(sys, "platform", "win32"):
                    self.assertFalse(addon.install())
                if player is not None:
                    self.assertFalse(callable(getattr(player, "_get_available_voices", None)))

    def test_non_windows_does_not_patch_player_or_enumerate_voices(self):
        for platform in ("linux", "darwin"):
            with self.subTest(platform=platform):
                backend = Mock()
                tts = player_fixture(backend)
                original = tts.WindowsRTTTSFilePlayer._get_available_voices
                addon, fake_modules = load_addon(tts, platform=platform)
                with patch.dict(sys.modules, fake_modules), patch.object(sys, "platform", platform):
                    self.assertFalse(addon.install())
                self.assertIs(tts.WindowsRTTTSFilePlayer._get_available_voices, original)
                backend.assert_not_called()

    def test_missing_voice_warning_is_logged_once_per_installed_wrapper(self):
        backend = Mock(side_effect=FakeBackendError(MISSING_VOICES))
        tts = player_fixture(backend)
        addon, _ = load_addon(tts)
        with self.assertLogs(addon.__name__, level="WARNING") as logs:
            tts.WindowsRTTTSFilePlayer.get_available_voices()
            tts.WindowsRTTTSFilePlayer().validated_voices()
            tts.WindowsRTTTSFilePlayer.get_available_voices()
        self.assertEqual(len(logs.records), 1)
        self.assertIn("SAPI", logs.records[0].getMessage())

    def test_voice_enumeration_can_recover_when_windows_is_repaired(self):
        backend = Mock(side_effect=FakeBackendError(MISSING_VOICES))
        tts = player_fixture(backend)
        addon, _ = load_addon(tts)
        player = tts.WindowsRTTTSFilePlayer()
        with self.assertLogs(addon.__name__, level="WARNING"):
            self.assertEqual(player.voices(), [])
        repaired_voices = [SimpleNamespace(name="Microsoft_Aria", lang="en_US")]
        backend.side_effect = None
        backend.return_value = repaired_voices
        # Anki's explicit validation refreshes the session's cached empty list.
        self.assertIs(player.validated_voices(), repaired_voices)
        self.assertIs(player.voices(), repaired_voices)
        self.assertEqual(backend.call_args_list, [call(validate=False), call(validate=True)])


if __name__ == "__main__":
    unittest.main()

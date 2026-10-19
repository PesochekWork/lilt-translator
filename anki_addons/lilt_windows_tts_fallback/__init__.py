"""Let Anki use its SAPI voices when Windows' WinRT voice list is missing."""

from functools import wraps
import logging
import sys


def install() -> bool:
    if sys.platform != "win32":
        return False

    from anki.errors import BackendError
    from aqt import tts

    player = getattr(tts, "WindowsRTTTSFilePlayer", None)
    original = getattr(player, "_get_available_voices", None)
    if not callable(original):
        return False
    if getattr(original, "_lilt_missing_winrt_fallback", False):
        return True

    warned = False

    @wraps(original)
    def available_voices(validate: bool):
        nonlocal warned
        try:
            return original(validate=validate)
        except BackendError as exc:
            details = str(exc).lower()
            if "windowserror" not in details or "0x80070002" not in details:
                raise
            if not warned:
                logging.getLogger(__name__).warning(
                    "Windows WinRT speech voices are missing. "
                    "Anki can use its installed legacy SAPI voices instead."
                )
                warned = True
            return []

    available_voices._lilt_missing_winrt_fallback = True
    player._get_available_voices = staticmethod(available_voices)
    return True


install()

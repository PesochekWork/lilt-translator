# Windows speech fallback for Anki

This optional, local Anki add-on handles one Windows speech failure:
`all_tts_voices` raises `WindowsError` with `HRESULT(0x80070002)` while
enumerating WinRT voices. It was verified with Anki **26.09.3** on Windows 11.

Anki already includes a legacy Windows **SAPI** speech player. A failure in its
newer **WinRT** player can interrupt review before Anki selects that working
legacy player. This add-on treats that specific failed WinRT voice list as
empty, allowing Anki to select another installed player. Healthy WinRT voices
and unrelated errors retain their existing behavior.

It changes no cards, templates, scheduling, deck options, Windows settings or
voice installations. It makes no network requests. The add-on stays on this
computer; it does not sync to your home PC. If neither speech system has a
suitable voice, it cannot supply one.

## Install or remove

1. Download **Lilt-Windows-speech-fallback.ankiaddon** from the repository's
   [release assets](https://github.com/PesochekWork/lilt-translator/releases).
2. In Anki, choose **Tools → Add-ons → Install from file** and select it.
3. Restart Anki, then review a vocabulary card. **R/F5** replays its English word.

To remove the workaround, select **Lilt: Windows speech fallback** in Anki's
Add-ons window, choose **Delete**, and restart Anki. No card migration or Lilt
update is needed.

For a source installation, copy the `lilt_windows_tts_fallback` directory into
Anki's `addons21` directory, then restart Anki. Do not copy this whole parent
directory. Tests use isolated module fixtures and never modify a personal
collection:

```powershell
python -m unittest discover -s tests -p test_anki_tts_fallback.py -v
python tools/package_anki_addon.py
```

The packaging command creates `dist/anki/Lilt-Windows-speech-fallback.ankiaddon`.

## Restore Windows speech

This workaround does not repair missing Windows components. To restore standard
voices, use **Windows Settings → Time & language → Speech → Manage voices → Add
voices → English (United States)**, then restart Anki. A managed work computer
may require its administrator to restore the English Text-to-speech language
feature. Do not copy voice registry entries from another computer.

References: [Anki's Windows speech players](https://github.com/ankitects/anki/blob/26.09.3/qt/aqt/tts.py),
[player selection](https://github.com/ankitects/anki/blob/26.09.3/qt/aqt/sound.py),
[Windows voice installation](https://support.microsoft.com/en-us/accessibility/windows/narrator/appendix-a-supported-languages-and-voices).

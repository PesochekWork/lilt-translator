# Lilt project handoff

## Continue on another Windows PC

The project is in the private repository **[PesochekWork/lilt-translator](https://github.com/PesochekWork/lilt-translator)**, branch **main**. The current application code has been pushed. Sign into a GitHub account with access, then:

```powershell
git clone https://github.com/PesochekWork/lilt-translator.git
cd lilt-translator
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m lilt
```

Use Python 3.12 or newer; development and tests used Python 3.14. Tell the next coding assistant to read this file and README.md first. There are no outstanding requested features at this handoff.

## Product and preferences

- A lightweight Windows desktop translator for **English ↔ Russian**, with local history and quick Anki card creation. The user wants minimal clutter and useful translation details.
- Preserve the requested appearance: **charcoal background, orange accents, sharp corners, old-school square checkboxes with black ticks, and no slogans**.
- Select text in another app, hold **Ctrl**, and tap **C twice within 0.6 seconds**. The popup translates the clipboard and appears near the mouse cursor. It flips beside screen edges and clamps to that monitor's work area, including monitors with negative coordinates. **Esc** hides it.
- **Ctrl+Enter** translates; **Ctrl+Shift+A** adds a card. **Ctrl+Alt+Space** translates the current clipboard as a fallback. Closing to the tray keeps capture available.

## Implementation and data

- Python + **PySide6**, launched with `python -m lilt`. Main UI: `lilt/ui.py`; translation: `engine.py`; capture: `hotkeys.py`; native single-instance/activation: `instance.py`.
- Default provider is **Google's unofficial online endpoint**, requiring no account. It can change or fail. Optional **DeepL official API** accepts the user's own key. Only EN/RU are supported, with a 5,000-character limit.
- The exact-query cache reuses the same text, source-language setting, and provider. It is **not an offline translation engine**. History can display saved translations without a network request.
- **AnkiConnect** connects locally at `127.0.0.1:8765` (add-on **2055492159**). The custom **Lilt** note type has **Front / Back / Context** fields. Cards save locally before sending; offline cards remain pending for explicit retry. TSV export is available.
- SQLite stores history, cache, cards, and preferences under **`%LOCALAPPDATA%\Lilt`**. Optional keys are stored separately using **Windows DPAPI**, bound to the Windows account/computer. Re-enter keys on the home PC. **Never put secrets or personal databases in the repository.**

## Validate and package

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Last reported validation: **54 automated tests passed**, plus the packaged `--self-test` check. Live Google translation was verified. **Live DeepL and a real Anki collection were not verified.** Earlier computer use was stopped with Escape; no UI automation is active. Use console tests or the package self-test unless the user requests interactive testing.

With the intended Python environment activated, run **`.\build.ps1`**. It installs build tools, runs tests, packages with **Lilt.spec**, and runs the noninteractive package self-check. Preserve the spec's ICU exclusion: PyInstaller previously picked an unrelated **icuuc.dll / icudt78.dll** from PATH whose versioned exports broke Qt imports. The app relies on Windows' system ICU.

The canonical executable is **`dist/Lilt/Lilt.exe`**; keep its entire folder together. Build outputs and the distribution ZIP are ignored and **are not on GitHub**. Clone and run/build locally, or separately transfer the full packaged folder/ZIP. **Quit an older running Lilt before replacing or rebuilding its package**, because Windows locks loaded files. Personal settings/history/cards do not travel with the Git clone.

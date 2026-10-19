# Lilt project notes

## Repository and development

The project is in the public repository **[PesochekWork/lilt-translator](https://github.com/PesochekWork/lilt-translator)**, branch **main**. The project includes the compact UI, dictionary-enriched vocabulary cards, and native Anki speech. Windows users can install **setup.exe** from GitHub Releases without Python; developers can clone and run from source:

```powershell
git clone https://github.com/PesochekWork/lilt-translator.git
cd lilt-translator
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m lilt
```

Use Python 3.12 or newer; development and tests use Python 3.14. Read this file and README.md before making changes. New vocabulary templates include native Anki speech for the English word.

## Product and preferences

- A lightweight Windows desktop translator for **English ↔ Russian**, with local history and quick Anki card creation. The user wants minimal clutter and useful translation details.
- Preserve the requested appearance: **charcoal background, orange accents, sharp corners, old-school square checkboxes with black ticks, and no slogans**.
- Main-window default is **960 × 600**, minimum **900 × 540**, with **64 px** minimum source/translation editors. Keep normal resizing, scrolling, **19 px** main text and **18 px** pronunciation/details. Details show the full available content. Repeated language/provider labels, sidebar shortcut help and persistent double-copy status were removed from the main UI and popup where applicable; source-language selection, Swap and Preferences controls remain.
- Select text in another app, hold **Ctrl**, and tap **C twice within 0.6 seconds**. The popup translates the clipboard and appears near the mouse cursor. It flips beside screen edges and clamps to that monitor's work area, including monitors with negative coordinates. **Esc** hides it.
- **Ctrl+Enter** translates; **Ctrl+Shift+A** adds a card. **Ctrl+Alt+Space** translates the current clipboard as a fallback. Closing to the tray keeps capture available.
- **Preferences → Start Lilt with Windows** registers this copy under the current user's Windows Run key only after Save; default is off. `lilt/startup.py` builds a quoted, absolute command with `--startup` (packaged executable or source `launch.pyw` with pythonw). Automatic launches stay in the tray, fall back to showing the window if no tray exists, and do not raise an already running instance. Normal launches still open/activate the window. Registry failures are shown in Preferences; test writes must use mocks, never a user's real startup entries.

## Implementation and data

- Python + **PySide6**, launched with `python -m lilt`. Main UI: `lilt/ui.py`; translation: `engine.py`; English dictionary: `dictionary.py`; card preparation: `cards.py`; capture: `hotkeys.py`; native single-instance/activation: `instance.py`.
- Default provider is **Google's unofficial online endpoint**, requiring no account. It can change or fail. Optional **DeepL official API** accepts the user's own key. Only EN/RU are supported, with a 5,000-character limit.
- The exact-query cache reuses the same text, source-language setting, and provider. It is **not an offline translation engine**. History can display saved translations without a network request.
- Optional **Free Dictionary API** lookup adds actual English definitions, phonetic text and source/license attribution, with no key. Only short English queries (up to 80 characters/four words) are requested. Dictionary failure leaves translation and card creation usable. Fresh translation results cache the enrichment; Preview/Add can retry missing information. Google's translated alternatives/romanization are distinct from these English definitions/IPA and must not populate those card fields.
- **AnkiConnect** connects locally at `127.0.0.1:8765` (add-on **2055492159**). New cards use **Lilt Vocabulary v2** with ordered fields **English / Russian / Definition / Pronunciation / Context / DictionarySource**. Both translation directions produce English-front cards. Preview and Cards display the rich snapshot; optional dictionary fields may be empty. Vocabulary templates center the English word, pronunciation, Russian translation, definitions and optional context. Dictionary source/license attribution remains in the note field and TSV export, without visible source links on the review face.
- Old local cards and the original **Lilt** model (**Front / Back / Context**) are preserved. The database adds versioned rich fields and keeps existing rows/content/note IDs. Card creation never rewrites existing Anki templates or user edits; a v2 field-name conflict is reported. The centered layout and speech template apply when Lilt creates **Lilt Vocabulary v2**; existing templates are left unchanged. Cards save locally before sending and remain pending for explicit retry when Anki is unavailable. Verification must use mocks/isolated fixtures for writes, not test notes in a personal collection.
- TSV export containing rich cards uses note-type/deck columns followed by the fields in each model's order. Mixed files include old rows as **Lilt** and new rows as **Lilt Vocabulary v2**; pure-old-card exports retain **Front / Back / Context / Deck**. Note types must exist before import: a normal Add creates v2, or manually create its six ordered fields. See README for mapping.
- Speech uses Anki's native **`{{tts en_US:English}}`** once on the front. The answer uses **FrontSide**; with Anki's `replayq=true`, **R/F5** replays only the English word on either side without duplicate speech. **Skip question when replaying answer** must stay off for answer-side keyboard replay. It relies on an installed Windows English voice; no new speech backend, service, API key, voice or recorded media is installed. Playback follows Anki's existing autoplay setting; do not change shared deck presets silently. Users can choose **Don't play audio automatically** in deck Audio options for replay-only behavior. Missing suitable voices do not prevent reading the card text.
- SQLite stores history, cache, cards, and preferences under **`%LOCALAPPDATA%\Lilt`**. Optional keys are stored separately using **Windows DPAPI**, bound to the Windows account/computer. Re-enter keys after changing computers or Windows accounts. **Never put secrets or personal databases in the repository.**

## Validate and package

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Run the automated suite and packaged `--self-test` after changes. Tests use controlled translation/dictionary responses and isolated card/Anki fixtures. Live Google translation was verified during initial setup; live DeepL was not. No test cards should be created in the user's real Anki collection. Console checks and the package self-test do not require an interactive personal collection.

With the intended Python environment activated, run **`.\build.ps1`**. It installs build tools, runs tests, packages with **Lilt.spec**, and runs the noninteractive package self-check. Preserve the spec's ICU exclusion: PyInstaller previously picked an unrelated **icuuc.dll / icudt78.dll** from PATH whose versioned exports broke Qt imports. The app relies on Windows' system ICU.

The default executable is **`dist/Lilt/Lilt.exe`**; keep its entire folder together. **`build-installer.ps1`** builds the application by default, then uses **Inno Setup 6** to create **`dist/installer/setup.exe`**. Its **`-PackageDir`** option accepts an already verified package; **`-OutputDir`** and **`-CompilerPath`** override the output and compiler paths. The installer targets **Windows 10/11 x64**, installs per user under **`%LOCALAPPDATA%\Programs\Lilt`**, creates a Start menu entry and a default desktop shortcut, and retains **`%LOCALAPPDATA%\Lilt`** on uninstall. It does not install Anki or voices, or enable Windows startup by itself. Uninstall removes only a startup command matching the current installation; portable/alternate paths are preserved. The installer is unsigned.

Version **0.1.0** is the first public release; **0.1.1** adds optional Windows startup. GitHub Releases distribute **setup.exe**, a **Lilt-<version>-windows-x64.zip** folder package, and **SHA256SUMS.txt**. Generated packages stay ignored in Git; only source and packaging instructions are tracked. Keep the README's latest-release installer link stable by naming each release's primary asset **setup.exe**. The manually dispatched **Windows build** workflow tests and packages on GitHub's Windows runner using its existing Inno compiler; its **Lilt-Windows** artifact contains these three release files.

Windows locks loaded application files: preserve an active instance and its text, build to a sibling output when necessary, and point an existing desktop **Lilt** shortcut to the verified package if requested. Opening another copy activates the existing instance, so choose tray **Quit Lilt**, then reopen when ready to see a new build. Personal settings/history/cards do not travel with the Git clone or distribution ZIP.

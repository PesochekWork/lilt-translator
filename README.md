# Lilt

A small Windows desktop translator for **English ↔ Russian**, with a quick selection popup, local history, and English vocabulary cards for Anki. No Lilt account is needed.

**[Download setup.exe for Windows](https://github.com/PesochekWork/lilt-translator/releases/latest/download/setup.exe)** · [All releases](https://github.com/PesochekWork/lilt-translator/releases)

## Install

Requires **Windows 10 or 11, 64-bit (x64)**. Python is not needed.

1. Download **setup.exe** from the latest release and run it.
2. Follow the setup wizard. Lilt installs for your Windows account without administrator privileges. A Start menu entry and a desktop shortcut are included by default.
3. Open **Lilt** and enter a word, or use the selection shortcut below.

The installer is not code-signed, so Windows may show a SmartScreen prompt. Download it from this repository's Releases page.

Before updating, save any text you need and choose **Quit Lilt** from its system-tray menu. Closing the window normally leaves the app running. Install the new release over the existing one to keep your history, cards, and preferences.

To uninstall, use **Windows Settings → Apps → Lilt**. Uninstalling removes the application and its shortcuts, but keeps your personal data in **`%LOCALAPPDATA%\Lilt`**. Anki, AnkiConnect, and speech voices are separate and are not installed or removed by Lilt setup.

For a folder-only package, download **Lilt-0.1.0-windows-x64.zip** from the [release page](https://github.com/PesochekWork/lilt-translator/releases), extract it, and run **Lilt.exe**. Keep the extracted folder together. Both packages use the same local data folder; the ZIP does not isolate your history or settings. Release assets also include **SHA256SUMS.txt** for download verification.

## What Lilt does

- Translate English and Russian words, phrases, and text up to 5,000 characters.
- Open a compact popup from a selection with **Ctrl+C, C**, without leaving what you are reading.
- Show English definitions and pronunciation when dictionary information is available.
- Save English-first Anki cards with Russian translations, definitions, pronunciation, and optional context.
- Read the English word aloud in Anki using its native text-to-speech support.
- Keep translation history and cards locally, including cards waiting for Anki.

The charcoal interface opens at **960 × 600**, with compact text panes and readable pronunciation/details. Resize the window for longer text; the content wraps and scrolls.

![Lilt translator](docs/translator.png)

## Translate while reading

1. Leave Lilt running and select a word or sentence in another application.
2. Hold **Ctrl** and tap **C** twice quickly, within about 0.6 seconds. The application must support copying the selection.
3. The quick popup opens beside your mouse cursor and translates the clipboard text. Near a screen edge it opens on the other side and stays within that monitor's work area. Press **Esc** to hide it and keep reading.

You can also copy once, then press **Ctrl+Alt+Space**, or choose **Translate clipboard** from Lilt's tray menu. The shortcut uses the current clipboard; it does not extract text from pictures or applications that prevent copying.

| Shortcut | Action |
| --- | --- |
| Ctrl+C, C | Open the quick popup and translate the copied text |
| Ctrl+Alt+Space | Translate the current clipboard |
| Ctrl+Enter | Translate the text in the active Lilt translator |
| Ctrl+Shift+A | Save the displayed source and translation as an Anki card |
| Esc | Hide the quick popup |

In the main window, paste or type text and click **Translate**. Language detection chooses between Russian and English locally; select the source language yourself for short or mixed-language passages. The other language becomes the target. You can edit the translated text before making a card.

For short English words or phrases, Lilt also requests English definitions and phonetic text from the [Free Dictionary API](https://dictionaryapi.dev/), without an API key. With Russian input it looks up the English translation. Lookups accept up to **80 characters and four words**; sentences and unsupported input are skipped. Missing entries or dictionary connection failures leave the translation usable. Fresh translations cache any dictionary details alongside the result; Preview or Add can retry missing details. Google's translated alternatives and romanization are separate from English definitions and dictionary IPA.

## Translation providers and connection drops

**Google web** is the default and needs no account or API key. It uses an unofficial Google endpoint that may change, reject requests, or become unavailable. Lilt shows connection and service errors so you can retry.

**DeepL API** is optional. Enter your own API key in **Preferences**, select DeepL, and click **Save preferences**. Lilt uses DeepL's official API, separate from its desktop application. Your DeepL account's plan and allowance apply; see [DeepL's API documentation](https://developers.deepl.com/docs) and [plan information](https://support.deepl.com/hc/en-us/articles/360021200939-DeepL-API-plans).

New translations need an internet connection. Previously saved results can be reused locally for the **same text, source-language setting, and provider**. This exact-query cache is not a general offline translation engine. **History** lets you read earlier results. **Clear history** removes both history and cached translations while keeping your cards.

## Make Anki cards

Lilt connects to Anki desktop on this computer through [AnkiConnect](https://git.sr.ht/~foosoft/anki-connect).

1. Install [Anki desktop](https://apps.ankiweb.net/) if needed. In Anki, open **Tools → Add-ons → Get Add-ons** and enter **`2055492159`** ([AnkiWeb listing](https://ankiweb.net/shared/info/2055492159)).
2. Restart Anki and leave it open with your collection loaded.
3. In Lilt's **Preferences**, click **Test connection**. If Anki asks to allow access, approve Lilt's connection. AnkiConnect listens at `127.0.0.1:8765`; no AnkiWeb account is needed for local card creation.
4. Translate something, optionally add a context sentence, and choose or type a deck name. A new deck is created when the card is sent.
5. Click **Preview**, then **Add to Anki**, or press **Ctrl+Shift+A**.

New cards use the note type **Lilt Vocabulary v2**, created automatically on the first **Add to Anki** if absent. Its fields are **English**, **Russian**, **Definition**, **Pronunciation**, **Context**, and **DictionarySource**, in that order. The English word is centered on the front; the back centers the word, Russian translation, available English definitions and phonetic text, and optional context. Dictionary source/license metadata stays in **DictionarySource** and exports, without visible source links on the review card. Russian → English input uses the same English-first card layout. **Preview** and **Cards** show these saved details. If dictionary information is unavailable, a translation card can still be saved with those optional fields empty.

Existing local cards and the original **Lilt** note type (**Front / Back / Context**) keep their original content and behavior. Lilt does not rewrite existing Anki templates, including user edits. If **Lilt Vocabulary v2** already exists, its current templates stay unchanged; the centered layout and speech template are installed when Lilt creates that note type. If its fields differ from those listed above, Lilt reports the conflict instead of changing it.

Cards are saved locally before sending. If Anki is closed or unreachable, open **Cards** later and click **Send to Anki** on a waiting card. Retry is explicit; leaving a card waiting does not automatically send it. A successful send is marked **In Anki**. Removing a local card from Lilt leaves any existing Anki note in place.

An AnkiConnect API key is only needed if you configured one in that add-on. Enter it in **Preferences** and save. The app does not require a key for the default AnkiConnect configuration.

### Export instead

In **Cards**, choose **Export for Anki** to save all local cards as a UTF-8 `.tsv` file, including cards already sent to Anki. In Anki, choose **File → Import**, select the file, and review the preview before importing. Exports containing new cards include note-type and deck columns:

| Export column | Import mapping |
| --- | --- |
| 1 — NoteType | Note type column |
| 2 — Deck | Deck column |
| 3 | English (old cards: Front) |
| 4 | Russian (old cards: Back) |
| 5 | Definition (old cards: Context) |
| 6 | Pronunciation (old cards: unused) |
| 7 | Context (old cards: unused) |
| 8 | DictionarySource (old cards: unused) |

The named note types must already exist in Anki; TSV import does not create them. Normal **Add to Anki** creates the new type, or create **Lilt Vocabulary v2** manually with the six fields listed above in that exact order and an English-front template. Mixed exports also require the original **Lilt** type. Anki maps fields by their order within each note type, so review the import preview carefully.

An export containing only old cards keeps the original four columns: **Front / Back / Context / Deck**. Use the original **Lilt** type for that file. Export headers specify tab separation, plain text, the `lilt` tag, and deck/note-type columns as applicable. Review duplicate handling when importing cards already sent. See the [official text import guide](https://docs.ankiweb.net/manual/importing/text-files).

### Speech playback

The vocabulary template uses Anki's native **`{{tts en_US:English}}`** on the front, so speech reads only the English word. The answer reuses the front's word and replay button. In Anki's reviewer, press **R** or **F5** to replay it, or use the replay button. Answer-side keyboard replay uses the existing **Skip question when replaying answer** option: leave that option off to replay the word on either side. A single speech tag avoids saying the word twice. Playback uses an English voice already installed in Windows; no external speech service, API key, additional voice, or audio download is required.

Automatic playback follows your existing Anki deck setting. Lilt does not change that setting. To use replay only, enable **Don't play audio automatically** in the deck's **Audio** options. If no suitable English voice is installed, Windows voice setup is needed for speech; the card's text still works. See Anki's [text-to-speech documentation](https://docs.ankiweb.net/manual/templates/fields#text-to-speech-for-individual-fields) and [audio options](https://docs.ankiweb.net/manual/deck-options#audio).

## Preferences, tray, and local data

**Preferences** controls the provider, optional keys, double-copy capture, and closing to the tray. Click **Save preferences** to apply changes. By default, closing the main window leaves Lilt in the Windows system tray so the shortcuts continue working. Double-click its tray icon to reopen it; choose **Quit Lilt** from the tray menu to exit fully. Lilt does not add itself to Windows startup.

Lilt stores its database and preferences in **`%LOCALAPPDATA%\Lilt`**, normally `C:\Users\<you>\AppData\Local\Lilt`. The `lilt.sqlite3` database contains translation history, cached text, and local cards in readable form. Quit Lilt before backing up the whole folder.

Optional API keys are saved separately as `credentials.dpapi`, protected for your Windows account using [Windows DPAPI](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata). They generally cannot be moved to another account or computer by copying that file; enter them again there.

Text is sent to the selected translation provider only when you click **Translate**, use its shortcut, or invoke clipboard translation. Typing alone does not send a request. A matching cached translation uses no network request. Fresh translations and card preparation can send the short English word or phrase to Free Dictionary API for optional definitions and pronunciation. Context and card contents are sent to local Anki when you add or retry a card. The global keyboard listener recognizes the capture shortcuts; it does not save a keystroke history.

## Limits and troubleshooting

- This version targets Windows and supports only Russian and English. Each translation accepts up to **5,000 characters**.
- If a selection does not copy, try copying once and using **Ctrl+Alt+Space**, or paste into the main window. Another application's reserved shortcut, elevated window, or clipboard behavior can affect global capture. The tray's **Translate clipboard** action is another fallback.
- If the detected language is wrong, select **English** or **Русский** before translating.
- If Anki cannot be reached, check that Anki is open, the add-on is installed, and Anki was restarted. Use **Test connection** and check any configured API key. Your card stays in Lilt for retry.
- Google's alternatives and transliteration are provider-dependent. Real English definitions and phonetic text come from the separate optional dictionary lookup, including when using DeepL.
- There is no bundled offline translation model, recorded pronunciation audio, OCR, or automatic context extraction in this version. Anki speech uses the system voice as described above.

## Run from source

Use **Python 3.12 or newer** on Windows (development and tests use Python 3.14):

```powershell
git clone https://github.com/PesochekWork/lilt-translator.git
cd lilt-translator
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m lilt
```

Opening Lilt again brings its existing window forward, including when another copy is running from an installation or a build folder. Quit the tray instance before switching between versions.

## Test and build

From the project folder, with the source environment installed:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Activate the environment and build the Windows folder package with:

```powershell
.\.venv\Scripts\Activate.ps1
.\build.ps1
```

The build installs its build dependencies, runs the test suite, packages with PyInstaller, and checks the resulting executable. It produces **`dist/Lilt/Lilt.exe`**. Keep the entire **`dist/Lilt`** folder together; the executable needs its adjacent files. This package also runs without Python.

Build the Windows installer with:

```powershell
.\build-installer.ps1
```

The installer build requires [Inno Setup 6](https://jrsoftware.org/isinfo.php) and produces **`dist/installer/setup.exe`** after building and checking the application. To package an already verified folder build, use **`-PackageDir`**; **`-OutputDir`** and **`-CompilerPath`** override the output directory and Inno Setup compiler location. Build outputs are ignored by Git and distributed through GitHub Releases.

After a build, check translation, popup capture, tray behavior, and your Anki connection. Automated tests use controlled translation/dictionary responses and isolated Anki fixtures; they do not create cards in your collection. Live services can vary by network and time. DeepL requires your own key for live verification.

For a noninteractive package check that uses no network, keyboard hook, or personal Anki collection:

```powershell
Start-Process -FilePath .\dist\Lilt\Lilt.exe -ArgumentList '--self-test', "$PWD\package-check.json" -Wait
Get-Content .\package-check.json
```

Runtime license notices are included next to the executable in `THIRD_PARTY_NOTICES.md` and `licenses/`.

## Integration references

- [AnkiConnect current source and documentation](https://git.sr.ht/~foosoft/anki-connect), [original repository's move notice](https://github.com/FooSoft/anki-connect), and [version 6 API documentation snapshot](https://github.com/FooSoft/anki-connect/blob/b896b6673695ded4affd157034cf8ac52120e494/README.md).
- [DeepL official API documentation](https://developers.deepl.com/docs) and [official Python SDK](https://github.com/DeepLcom/deepl-python).
- [Google Cloud Translation's supported API](https://cloud.google.com/translate/docs) is a separate product. Lilt's default Google web integration is unofficial and does not use a Cloud account or its API key.

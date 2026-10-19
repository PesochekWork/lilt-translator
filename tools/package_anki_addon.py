"""Package only the standalone speech compatibility add-on's runtime files."""

import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def main():
    root = Path(__file__).resolve().parent.parent
    source = root / "anki_addons" / "lilt_windows_tts_fallback"
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    if manifest["package"] != "lilt_windows_tts_fallback":
        raise ValueError("Unexpected add-on package name.")
    target = root / "dist" / "anki" / "Lilt-Windows-speech-fallback.ankiaddon"
    target.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(target, "w", compression=ZIP_DEFLATED) as package:
        for name in ("__init__.py", "manifest.json"):
            package.write(source / name, arcname=name)
    print(target)


if __name__ == "__main__":
    main()

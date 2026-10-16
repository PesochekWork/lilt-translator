"""Copy bundled runtime license notices into the portable folder."""
from pathlib import Path
import shutil
import sys

root = Path(__file__).resolve().parents[1]
destination = root / "dist" / "Lilt"
licenses = destination / "licenses"
licenses.mkdir(parents=True, exist_ok=True)
for item in (root / "licenses").glob("*.txt"):
    shutil.copy2(item, licenses / item.name)
shutil.copy2(Path(sys.base_prefix) / "LICENSE.txt", licenses / "PYTHON-LICENSE.txt")
shutil.copy2(root / "THIRD_PARTY_NOTICES.md", destination / "THIRD_PARTY_NOTICES.md")

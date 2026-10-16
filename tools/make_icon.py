from pathlib import Path
import sys
from PIL import Image
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lilt.ui import icon

app = QApplication([])
destination = Path(__file__).resolve().parent
icon().pixmap(256, 256).save(str(destination / "lilt.png"))
with Image.open(destination / "lilt.png") as image:
    image.save(destination / "lilt.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

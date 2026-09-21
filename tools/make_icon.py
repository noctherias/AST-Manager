from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from PIL import Image

root = Path(__file__).resolve().parents[1]
app = QApplication([])
icon = QIcon(str(root / 'assets' / 'ast.svg'))
png = root / 'assets' / 'ast.png'
icon.pixmap(256, 256).save(str(png))
with Image.open(png) as image:
    image.save(root / 'assets' / 'ast.ico', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])

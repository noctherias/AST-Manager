"""Copy bundled dependency notices into the distribution without changing packages."""
from importlib.metadata import distribution
from pathlib import Path
import shutil
import sys

target = Path(sys.argv[1])
target.mkdir(parents=True, exist_ok=True)
for name in ["PySide6", "PySide6_Essentials", "PySide6_Addons", "shiboken6", "pypdf", "reportlab", "Pillow",
             "openpyxl", "et-xmlfile", "pyinstaller", "charset-normalizer"]:
    dist = distribution(name)
    folder = target / name
    folder.mkdir(exist_ok=True)
    for f in dist.files or []:
        if any(word in str(f).lower() for word in ("license", "copying")) and dist.locate_file(f).is_file():
            shutil.copy2(dist.locate_file(f), folder / Path(f).name)
    (folder / "METADATA.txt").write_text(dist.read_text("METADATA") or "", encoding="utf-8")
python_license = Path(sys.base_prefix) / "LICENSE.txt"
if python_license.exists(): shutil.copy2(python_license, target / "Python-LICENSE.txt")
source = Path(__file__).resolve().parents[1] / "licenses"
if source.exists(): shutil.copytree(source, target, dirs_exist_ok=True)

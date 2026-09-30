# PyInstaller onedir build: Qt libraries stay replaceable and visible.
from pathlib import Path
import os

root = Path(SPECPATH)
a = Analysis([str(root / 'main.py')], pathex=[str(root)],
             binaries=[], datas=[(str(root / 'templates' / 'Vorlage_Lohnausweis.pdf'), 'templates'),
                                  (str(root / 'templates' / 'Zeiterfassung_Vorlage.xlsm'), 'templates'),
                                  (str(root / 'assets'), 'assets'),
                                  (str(root / 'THIRD_PARTY_NOTICES.md'), '.'),
                                  (str(root / 'release_config.json'), '.')],
             hiddenimports=[], hookspath=[], hooksconfig={}, runtime_hooks=[],
             excludes=['tkinter','matplotlib','pandas','numpy','PySide6.QtWebEngineCore',
                       'PySide6.QtWebEngineWidgets','PySide6.QtQml','PySide6.QtQuick'], noarchive=False)
# Qt 6.11 uses the Windows system ICU API (unversioned symbols). Do not bundle
# unrelated ICU DLLs picked up from tools such as Poppler on the build PATH.
if os.name == 'nt':
    a.binaries = [entry for entry in a.binaries
                  if Path(entry[0]).name.lower() not in {'icuuc.dll', 'icudt78.dll'}]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='AST-Verwaltung',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=bool(os.environ.get('AST_BUILD_CONSOLE')), icon=str(root / 'assets' / 'ast.ico'))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='AST-Verwaltung')

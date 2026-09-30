# Bibliotheken

AST verwendet Python, PySide6 / Qt for Python (LGPLv3/GPLv3 oder kommerzielle Lizenz), pypdf (BSD-3-Clause), ReportLab (BSD), Pillow (HPND), openpyxl (MIT) und et-xmlfile (MIT).

Der Windows-Build nutzt dynamisch geladene Qt-Bibliotheken in einem separaten `_internal`-Ordner. Dieser Ordner gehört zum Programm. Die Bibliotheken können durch kompatible eigene Builds ersetzt werden. Die Lizenztexte werden mit dem Build unter `_internal/licenses` mitgeliefert. Anwendungscode und Build-Anleitung liegen vollständig bei. Es wird keine Einschränkung für Reverse Engineering zur Fehlersuche an Änderungen der LGPL-Bibliotheken hinzugefügt.

Upstream-Quellen und Informationen:

- Qt/PySide: https://code.qt.io/pyside/pyside-setup.git/ und https://code.qt.io/qt/qtbase.git/
- Qt PDF / PDFium: https://code.qt.io/qt/qtwebengine.git/
- Lizenzhinweise: https://doc.qt.io/qtforpython-6/licenses.html
- pypdf: https://github.com/py-pdf/pypdf
- ReportLab: https://hg.reportlab.com/hg-public/reportlab/
- Pillow: https://github.com/python-pillow/Pillow
- openpyxl: https://foss.heptapod.net/openpyxl/openpyxl
- et-xmlfile: https://foss.heptapod.net/openpyxl/et_xmlfile
- Python: https://www.python.org/psf/license/
- PyInstaller: https://github.com/pyinstaller/pyinstaller (GPL mit Bootloader-Ausnahme)

Die Excel-Vorlagen wurden vom Auftraggeber bereitgestellt. Die Lohnausweis-Vorlage stammt von der Eidgenössischen Steuerverwaltung.

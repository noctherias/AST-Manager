from PySide6.QtGui import QColor, QPalette


def apply_theme(app):
    """Force a readable light palette even when Windows uses dark mode."""
    palette = QPalette()
    for role, color in (
        (QPalette.ColorRole.Window, "#f4f7f9"),
        (QPalette.ColorRole.WindowText, "#183342"),
        (QPalette.ColorRole.Base, "#ffffff"),
        (QPalette.ColorRole.AlternateBase, "#f3f6f8"),
        (QPalette.ColorRole.ToolTipBase, "#163845"),
        (QPalette.ColorRole.ToolTipText, "#ffffff"),
        (QPalette.ColorRole.Text, "#183342"),
        (QPalette.ColorRole.Button, "#ffffff"),
        (QPalette.ColorRole.ButtonText, "#183342"),
        (QPalette.ColorRole.Highlight, "#d9eee8"),
        (QPalette.ColorRole.HighlightedText, "#123b32"),
        (QPalette.ColorRole.PlaceholderText, "#7b8d97"),
    ):
        palette.setColor(role, QColor(color))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor("#8999a2"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor("#8999a2"))
    app.setPalette(palette)
    app.setStyleSheet(STYLE)


STYLE = """
* { font-family: 'Segoe UI'; font-size: 10pt; color: #183342; }
QMainWindow, QDialog, QWidget#appRoot, QWidget#pageRoot, QStackedWidget { background: #f4f7f9; }
QLabel, QCheckBox, QRadioButton { background: transparent; }
QScrollArea#formScroll, QWidget#formContent { background: #ffffff; }
QWidget#sidebar { background: #0d3441; }
QWidget#sidebar QLabel { color: #acc4cd; background: transparent; }
QWidget#sidebar QLabel#brand { color: white; font-size: 26pt; font-weight: 700; }
QWidget#sidebar QLabel#brandCaption { color: #85c7b9; font-size: 10pt; }
QWidget#sidebar QLabel#navSection { color: #7fa2ad; font-size: 8pt; font-weight: 700; letter-spacing: 1px; }
QWidget#sidebar QPushButton#navButton { text-align: left; color: #d9e6e9; background: transparent; border: none; border-radius: 9px; padding: 13px 16px; font-weight: 600; }
QWidget#sidebar QPushButton#navButton:hover { background: #174653; color: white; }
QWidget#sidebar QPushButton#navButton:checked { background: #e4f3ee; color: #075f50; border-left: 4px solid #30b99c; padding-left: 12px; }
QWidget#sidebar QPushButton#navSubButton { text-align: left; color: #b9ced5; background: transparent; border: none; border-radius: 8px; padding: 8px 16px 8px 34px; font-size: 9pt; }
QWidget#sidebar QPushButton#navSubButton:hover { background: #174653; color: white; }
QWidget#sidebar QPushButton#navSubButton:checked { background: #d8eee6; color: #075f50; border-left: 4px solid #30b99c; padding-left: 30px; font-weight: 600; }
QLabel#pageTitle { font-size: 25pt; font-weight: 650; color: #162f3e; }
QLabel#dialogTitle { font-size: 19pt; font-weight: 650; }
QLabel#sectionTitle { font-size: 13pt; font-weight: 650; }
QLabel#muted, QLabel#metricTitle { color: #536b79; }
QLabel#metricTitle { font-size: 10pt; }
QLabel#metricValue { font-size: 22pt; font-weight: 650; color: #183847; }
QLabel#metricHint { color: #718492; font-size: 9pt; }
QFrame#card { background: white; border: 1px solid #dce5ea; border-radius: 12px; }
QFrame#accentCard { background: #e3f3ed; border: 1px solid #bcdccc; border-radius: 12px; }
QFrame#accentCard QLabel#metricValue { color: #0b715b; }
QPushButton { background: white; border: 1px solid #ced9e0; border-radius: 7px; padding: 8px 14px; font-weight: 600; }
QPushButton:hover { background: #eaf0f3; border-color: #94afb9; }
QPushButton:pressed { background: #d7e8e2; }
QPushButton#primary { background: #087e67; border-color: #087e67; color: white; }
QPushButton#primary:hover { background: #066953; }
QPushButton:disabled { color: #9aabb4; background: #edf1f4; border-color: #e1e6eb; }
QPushButton#primary:disabled { color: #9aabb4; background: #edf1f4; border-color: #e1e6eb; }
QLineEdit, QComboBox, QDateEdit, QTimeEdit, QSpinBox, QDoubleSpinBox { background: white; color: #173443; border: 1px solid #bdcbd3; border-radius: 7px; padding: 7px 10px; selection-background-color: #c5e9df; selection-color: #173a34; min-height: 22px; }
QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QTimeEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus { border: 2px solid #138a73; padding: 6px 9px; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox QAbstractItemView { background: white; selection-background-color: #dcefe9; selection-color: #203444; border: 1px solid #d5dfe6; }
QTableWidget { background: white; border: 1px solid #e0e7ec; border-radius: 9px; selection-background-color: #e2f2ed; selection-color: #163c32; outline: none; }
QTableWidget::item { padding: 8px 12px; border-bottom: 1px solid #edf1f4; }
QHeaderView::section { background: #edf2f5; color: #586f7f; border: none; border-bottom: 1px solid #dce5eb; padding: 13px 10px; font-size: 9pt; font-weight: 600; }
QScrollArea { background: #f4f7f9; border: none; }
QScrollBar:vertical { background: #edf1f4; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #bccbd3; border-radius: 5px; min-height: 28px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QTabWidget::pane { border: 1px solid #d5e0e6; border-radius: 9px; background: #ffffff; }
QTabBar::tab { background: #e8edf1; border: none; padding: 11px 18px; margin-right: 4px; }
QTabBar::tab:selected { background: #d8eee6; color: #096751; font-weight: 600; }
QCheckBox { spacing: 8px; padding: 5px 0; }
QStatusBar { background: #edf2f5; color: #607686; font-size: 9pt; }
QToolTip { background: #143744; color: white; border: none; padding: 7px; }
"""

STYLE += """
QPushButton#segment:checked { background: #d8eee6; color: #075e4d; border-color: #8cc4b2; }
QPushButton#disclosure { text-align: left; background: transparent; color: #456575; border: none; padding: 5px 2px; }
QPushButton#disclosure:checked { color: #087e67; }
QFrame#selectionBar { background: #edf2f5; border-radius: 9px; }
QPlainTextEdit { background: white; border: 1px solid #d5dfe6; border-radius: 7px; padding: 10px; }
QMenu { background: white; border: 1px solid #d5dfe6; padding: 6px; }
QMenu::item { padding: 9px 22px; }
QMenu::item:selected { background: #d8eee6; }
QProgressBar { border: 1px solid #d5dfe6; border-radius: 6px; text-align: center; min-height: 24px; }
QProgressBar::chunk { background: #85c7b9; }
"""

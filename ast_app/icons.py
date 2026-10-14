"""Small, dependency-free SVG icon set used throughout the AST interface.

The paths are deliberately kept in the project so every packaged build has the
same visual language and does not depend on an operating-system icon theme.
"""
from pathlib import Path

from PySide6.QtGui import QIcon

from .documents import resource_path


def icon(name: str) -> QIcon:
    return QIcon(str(resource_path(f"assets/icons/{name}.svg")))


def icon_path(name: str) -> Path:
    return resource_path(f"assets/icons/{name}.svg")

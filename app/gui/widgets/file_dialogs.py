"""File pickers that look and behave the same on Windows, Linux and macOS.

QFileDialog's static helpers open the OS's native dialog (Finder-style on
macOS, Explorer-style on Windows, GTK/KDE on Linux), which ignores the
app's theme and differs per platform. These wrappers always use Qt's own
dialog, styled by app/gui/theme.py, and give it the same sidebar
everywhere: home folders plus every mounted drive/volume, so removable
media is one click away on every OS.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QDir, QFileInfo, QStandardPaths, QUrl
from PySide6.QtGui import QAbstractFileIconProvider
from PySide6.QtWidgets import QFileDialog, QHeaderView, QSplitter, QTreeView, QWidget

from app.gui.theme import COLORS
from app.gui.widgets import icons


class ThemedIconProvider(QAbstractFileIconProvider):
    """The app's own line icons for files, folders and drives, instead of the
    OS icon theme (which differs on every platform)."""

    def icon(self, arg):  # noqa: D102 - Qt override; arg is an IconType or a QFileInfo
        if isinstance(arg, QFileInfo):
            path = arg.absoluteFilePath()
            if arg.isRoot() or path in _volume_paths() or path == QDir.homePath():
                name = "home" if path == QDir.homePath() else "hard-drive"
            else:
                name = "folder" if arg.isDir() else "file"
        else:
            name = {
                QAbstractFileIconProvider.IconType.Computer: "hard-drive",
                QAbstractFileIconProvider.IconType.Drive: "hard-drive",
                QAbstractFileIconProvider.IconType.Folder: "folder",
            }.get(arg, "file")
        color = COLORS["text_muted"] if name != "file" else COLORS["text_muted"]
        return icons.icon(name, color)


_ICON_PROVIDER: ThemedIconProvider | None = None


def _volume_paths() -> set[str]:
    if sys.platform == "win32":
        return {drive.absoluteFilePath() for drive in QDir.drives()}
    if sys.platform == "darwin":
        return {str(p) for p in Path("/Volumes").glob("*")}
    return set()


def _sidebar_urls() -> list[QUrl]:
    places: list[str] = []
    for location in (
        QStandardPaths.HomeLocation,
        QStandardPaths.DesktopLocation,
        QStandardPaths.DocumentsLocation,
        QStandardPaths.DownloadLocation,
    ):
        path = QStandardPaths.writableLocation(location)
        if path and os.path.isdir(path) and path not in places:
            places.append(path)

    if sys.platform == "win32":
        volumes = [drive.absoluteFilePath() for drive in QDir.drives()]
    elif sys.platform == "darwin":
        volumes = [str(p) for p in sorted(Path("/Volumes").glob("*")) if p.is_dir()]
    else:
        user = os.environ.get("USER", "")
        roots = [Path("/media") / user, Path("/run/media") / user, Path("/mnt")]
        volumes = [str(p) for root in roots if root.is_dir() for p in sorted(root.glob("*")) if p.is_dir()]
    for volume in volumes:
        if volume not in places:
            places.append(volume)
    return [QUrl.fromLocalFile(p) for p in places]


def _dialog(parent: QWidget | None, title: str, mode: QFileDialog.FileMode, name_filter: str = "") -> QFileDialog:
    dialog = QFileDialog(parent, title)
    dialog.setOption(QFileDialog.DontUseNativeDialog, True)
    dialog.setFileMode(mode)
    dialog.setViewMode(QFileDialog.Detail)
    dialog.setSidebarUrls(_sidebar_urls())
    global _ICON_PROVIDER
    if _ICON_PROVIDER is None:
        _ICON_PROVIDER = ThemedIconProvider()
    dialog.setIconProvider(_ICON_PROVIDER)
    dialog.resize(900, 560)
    splitter = dialog.findChild(QSplitter)
    if splitter is not None:
        splitter.setSizes([210, 690])
    tree = dialog.findChild(QTreeView)
    if tree is not None:
        header = tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for column in range(1, header.count()):
            header.setSectionResizeMode(column, QHeaderView.ResizeToContents)
    if name_filter:
        dialog.setNameFilter(name_filter)
    return dialog


def open_file(parent: QWidget | None, title: str, name_filter: str = "") -> str:
    dialog = _dialog(parent, title, QFileDialog.ExistingFile, name_filter)
    return dialog.selectedFiles()[0] if dialog.exec() and dialog.selectedFiles() else ""


def open_files(parent: QWidget | None, title: str, name_filter: str = "") -> list[str]:
    dialog = _dialog(parent, title, QFileDialog.ExistingFiles, name_filter)
    return dialog.selectedFiles() if dialog.exec() else []


def existing_directory(parent: QWidget | None, title: str) -> str:
    dialog = _dialog(parent, title, QFileDialog.Directory)
    dialog.setOption(QFileDialog.ShowDirsOnly, True)
    return dialog.selectedFiles()[0] if dialog.exec() and dialog.selectedFiles() else ""


def save_file(parent: QWidget | None, title: str, default_name: str = "", name_filter: str = "") -> str:
    dialog = _dialog(parent, title, QFileDialog.AnyFile, name_filter)
    dialog.setAcceptMode(QFileDialog.AcceptSave)
    if default_name:
        dialog.selectFile(default_name)
    return dialog.selectedFiles()[0] if dialog.exec() and dialog.selectedFiles() else ""

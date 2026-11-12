"""Visual theme: design tokens, bundled fonts, and the application stylesheet.

Everything visual lives here so views only set semantic hooks
(`objectName` / dynamic properties such as `variant="danger"`) instead of
hardcoding colours. Dark-only, tuned for a forensics/security tool:
graphite surfaces, off-white primary actions, one sage accent for
selection and the intact hash chain, amber for attention, and red
reserved strictly for destructive actions and failures.

Fonts (Fira Sans / Fira Code, SIL OFL — see assets/fonts/OFL.txt) are
loaded from the bundled assets; if they're missing the app falls back to
the platform UI and monospace fonts rather than failing.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

from app.utils.logging_setup import get_logger

logger = get_logger(__name__)

_ASSETS_DIR = Path(__file__).parent / "assets"
_FONTS_DIR = _ASSETS_DIR / "fonts"
_ICONS_DIR = _ASSETS_DIR / "icons"

# --- Tokens -----------------------------------------------------------------

COLORS = {
    # Graphite ramp: an evidence room at night. Surfaces stay grey so the
    # content (device verdicts, the hash chain, the wipe log) carries meaning.
    "bg": "#141415",
    "sidebar": "#0F0F10",
    "surface": "#19191B",
    "surface_alt": "#1E1E20",
    "surface_raised": "#232325",
    "border": "#29292C",
    "border_strong": "#36363A",
    "text": "#EDEDED",
    "text_muted": "#A1A1A6",
    "text_subtle": "#85858B",
    # Primary actions are off-white with dark text, not a coloured button.
    "primary": "#E8E8E6",
    "primary_hover": "#FFFFFF",
    "primary_pressed": "#CFCFCC",
    "primary_soft": "#26282A",
    "on_primary": "#141415",
    # One accent, sage like an instrument readout: selection, focus, progress, "intact".
    "seal": "#8FC1A9",
    "seal_soft": "#1B2622",
    "accent": "#E0A640",
    "accent_soft": "#2A2316",
    "danger": "#C9363C",
    "danger_hover": "#B12E34",
    "danger_pressed": "#97272C",
    "danger_soft": "#2A1A1B",
    "success": "#4CC38A",
    "success_soft": "#16261E",
    "danger_text": "#E5686D",
    "primary_text": "#8FC1A9",
    "info": "#A1A1A6",
    "info_soft": "#232325",
    "selection": "#2B302E",
}

TONE_COLORS = {
    "neutral": (COLORS["text_muted"], COLORS["surface_raised"]),
    "info": (COLORS["info"], COLORS["info_soft"]),
    "success": (COLORS["success"], COLORS["success_soft"]),
    "warning": (COLORS["accent"], COLORS["accent_soft"]),
    "danger": (COLORS["danger_text"], COLORS["danger_soft"]),
    "primary": (COLORS["primary_text"], COLORS["primary_soft"]),
}

RADIUS = {"sm": 6, "md": 8, "lg": 12}

UI_FONT_FALLBACKS = ["Fira Sans", ".AppleSystemUIFont", "Segoe UI", "Helvetica Neue", "Arial"]
MONO_FONT_FALLBACKS = ["Fira Code", "SF Mono", "Menlo", "Consolas", "DejaVu Sans Mono", "monospace"]


def _css_family(families: list[str]) -> str:
    return ", ".join(f'"{f}"' for f in families)


def load_fonts() -> None:
    if not _FONTS_DIR.is_dir():
        logger.info("bundled fonts not found at %s; using system fonts", _FONTS_DIR)
        return
    for font_file in sorted(_FONTS_DIR.glob("*.ttf")):
        if QFontDatabase.addApplicationFont(str(font_file)) < 0:
            logger.warning("could not load font %s", font_file.name)


def mono_font(pixel_size: int = 12) -> QFont:
    font = QFont()
    font.setFamilies(MONO_FONT_FALLBACKS)
    font.setStyleHint(QFont.Monospace)
    font.setPixelSize(pixel_size)
    return font


def build_stylesheet() -> str:
    c = COLORS
    ui = _css_family(UI_FONT_FALLBACKS)
    mono = _css_family(MONO_FONT_FALLBACKS)
    check_icon = (_ICONS_DIR / "check.svg").as_posix()
    return f"""
* {{
    font-family: {ui};
    font-size: 13px;
    color: {c['text']};
    outline: none;
}}
QMainWindow, QWidget#AppRoot, QStackedWidget#Pages, QWidget#Page, QScrollArea#PageScroll {{
    background: {c['bg']};
}}
QToolTip {{
    background: {c['surface_raised']};
    color: {c['text']};
    border: 1px solid {c['border_strong']};
    padding: 6px 8px;
    border-radius: {RADIUS['sm']}px;
}}

/* ---------- Sidebar ---------- */
QFrame#Sidebar {{
    background: {c['sidebar']};
    border-right: 1px solid {c['border']};
}}
QLabel#BrandTitle {{
    font-size: 15px;
    font-weight: 600;
}}
QLabel#BrandSubtitle, QLabel#SidebarSection, QLabel#SidebarFooter {{
    color: {c['text_subtle']};
    font-size: 11px;
}}
QLabel#SidebarSection {{
    font-weight: 500;
    padding: 0 12px;
}}
QLabel#BrandMark {{
    background: transparent;
    border: 1px solid {c['border_strong']};
    border-radius: 8px;
    color: {c['text']};
    font-family: {mono};
    font-size: 11px;
}}
QPushButton[nav="true"] {{
    text-align: left;
    padding: 8px 12px;
    border: none;
    border-radius: {RADIUS['md']}px;
    background: transparent;
    color: {c['text_muted']};
    font-size: 13px;
    font-weight: 500;
}}
QPushButton[nav="true"]:hover {{
    background: {c['surface_alt']};
    color: {c['text']};
}}
QPushButton[nav="true"]:checked {{
    background: {c['surface_raised']};
    color: {c['text']};
    border-top: 1px solid #303033;
}}
QPushButton[nav="true"]:focus {{
    border: 1px solid {c['seal']};
}}

/* ---------- Page header ---------- */
QLabel#PageTitle {{
    font-size: 24px;
    font-weight: 500;
}}
QLabel#PageSubtitle {{
    color: {c['text_muted']};
    font-size: 13px;
}}

/* ---------- Cards ---------- */
QFrame#Card {{
    background: {c['surface']};
    border: 1px solid {c['border']};
    border-radius: {RADIUS['lg']}px;
}}
QLabel#CardTitle {{
    font-size: 14px;
    font-weight: 600;
}}
QLabel#CardSubtitle, QLabel#Hint {{
    color: {c['text_muted']};
    font-size: 12px;
}}
QLabel#FieldLabel {{
    color: {c['text_muted']};
    font-size: 12px;
    font-weight: 500;
}}
QFrame#StatTile {{
    background: {c['surface']};
    border: 1px solid {c['border']};
    border-radius: {RADIUS['lg']}px;
}}
QLabel#StatLabel {{
    color: {c['text_muted']};
    font-size: 12px;
    font-weight: 500;
}}
QLabel#StatValue {{
    font-family: {mono};
    font-size: 26px;
    font-weight: 400;
}}
QLabel#StatCaption {{
    color: {c['text_subtle']};
    font-size: 11px;
}}
QFrame#Callout {{
    background: {c['accent_soft']};
    border: 1px solid #4A3B1E;
    border-radius: {RADIUS['md']}px;
}}
QFrame#Callout QLabel {{
    color: #EBCB8F;
    font-size: 12px;
}}
QFrame#DangerCallout {{
    background: {c['danger_soft']};
    border: 1px solid #4A2629;
    border-radius: {RADIUS['md']}px;
}}
QFrame#DangerCallout QLabel {{
    color: #EFA3A6;
}}

/* ---------- Buttons ---------- */
QPushButton {{
    background: {c['surface_raised']};
    border: 1px solid {c['border_strong']};
    border-radius: {RADIUS['md']}px;
    padding: 8px 14px;
    min-height: 20px;
    font-weight: 500;
}}
QPushButton:hover {{
    background: #2A2A2D;
    border-color: #444449;
}}
QPushButton:pressed {{
    background: #1E1E20;
}}
QPushButton:focus {{
    border: 1px solid {c['seal']};
}}
QPushButton:disabled {{
    color: {c['text_subtle']};
    background: {c['surface_alt']};
    border-color: {c['border']};
}}
QPushButton[variant="primary"] {{
    background: {c['primary']};
    border: 1px solid {c['primary']};
    color: {c['on_primary']};
    font-weight: 500;
}}
QPushButton[variant="primary"]:hover {{
    background: {c['primary_hover']};
    border-color: {c['primary_hover']};
}}
QPushButton[variant="primary"]:pressed {{
    background: {c['primary_pressed']};
}}
QPushButton[variant="danger"] {{
    background: {c['danger']};
    border: 1px solid {c['danger']};
    color: #FFFFFF;
    font-weight: 500;
}}
QPushButton[variant="danger"]:hover {{
    background: {c['danger_hover']};
    border-color: {c['danger_hover']};
}}
QPushButton[variant="danger"]:pressed {{
    background: {c['danger_pressed']};
}}
QPushButton[variant="danger"]:disabled, QPushButton[variant="primary"]:disabled {{
    background: {c['surface_alt']};
    border-color: {c['border']};
    color: {c['text_subtle']};
}}
QPushButton[variant="ghost"] {{
    background: transparent;
    border: 1px solid transparent;
    color: {c['text_muted']};
}}
QPushButton[variant="ghost"]:hover {{
    background: {c['surface_alt']};
    color: {c['text']};
}}
QPushButton[size="lg"] {{
    padding: 11px 18px;
    font-size: 14px;
}}

/* ---------- Inputs ---------- */
QLineEdit, QComboBox, QSpinBox {{
    background: {c['surface_alt']};
    border: 1px solid {c['border_strong']};
    border-radius: {RADIUS['md']}px;
    padding: 7px 10px;
    min-height: 20px;
    selection-background-color: {c['selection']};
}}
QLineEdit:hover, QComboBox:hover {{
    border-color: #444449;
}}
QLineEdit:focus, QComboBox:focus {{
    border: 1px solid {c['seal']};
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox QAbstractItemView {{
    background: {c['surface_raised']};
    border: 1px solid {c['border_strong']};
    selection-background-color: {c['selection']};
    padding: 4px;
}}
QCheckBox {{
    spacing: 8px;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid {c['border_strong']};
    background: {c['surface_alt']};
}}
QCheckBox::indicator:hover {{
    border-color: {c['seal']};
}}
QCheckBox::indicator:checked {{
    background: #3E6B58;
    border-color: {c['seal']};
    image: url({check_icon});
}}

/* ---------- Tables & lists ---------- */
QTableWidget, QTableView, QListWidget {{
    background: {c['surface']};
    alternate-background-color: {c['surface_alt']};
    border: 1px solid {c['border']};
    border-radius: {RADIUS['md']}px;
    gridline-color: transparent;
    selection-background-color: {c['selection']};
    selection-color: {c['text']};
}}
QTableWidget::item, QTableView::item {{
    padding: 0 8px;
    border: none;
}}
QTableWidget::item:selected, QTableView::item:selected {{
    background: {c['selection']};
}}
QListWidget {{
    padding: 4px;
}}
QListWidget::item {{
    padding: 8px 10px;
    border-radius: {RADIUS['sm']}px;
}}
QListWidget::item:hover {{
    background: {c['surface_alt']};
}}
QListWidget::item:selected {{
    background: {c['selection']};
    color: {c['text']};
}}
QHeaderView::section {{
    background: {c['surface_alt']};
    color: {c['text_muted']};
    border: none;
    border-bottom: 1px solid {c['border']};
    padding: 8px;
    font-size: 12px;
    font-weight: 500;
}}
QTableCornerButton::section {{
    background: {c['surface_alt']};
    border: none;
}}

/* ---------- Tabs ---------- */
QTabWidget::pane {{
    border: none;
    top: -1px;
}}
QTabBar {{
    qproperty-drawBase: 0;
}}
QTabBar::tab {{
    background: transparent;
    color: {c['text_muted']};
    padding: 8px 14px;
    margin-right: 4px;
    border: none;
    border-bottom: 2px solid transparent;
    font-weight: 500;
}}
QTabBar::tab:hover {{
    color: {c['text']};
}}
QTabBar::tab:selected {{
    color: {c['text']};
    border-bottom: 2px solid {c['seal']};
}}

/* ---------- Qt's own file dialog (used on every OS) ---------- */
QFileDialog QTreeView, QFileDialog QListView, QTreeView, QListView {{
    background: {c['surface']};
    alternate-background-color: {c['surface_alt']};
    border: 1px solid {c['border']};
    border-radius: {RADIUS['md']}px;
    selection-background-color: {c['selection']};
    selection-color: {c['text']};
}}
QTreeView::item, QListView::item {{
    padding: 4px 6px;
}}
QTreeView::item:hover, QListView::item:hover {{
    background: {c['surface_alt']};
}}
QTreeView::item:selected, QListView::item:selected {{
    background: {c['selection']};
    color: {c['text']};
}}
QFileDialog QListView#sidebar {{
    background: {c['sidebar']};
}}
QToolButton {{
    background: {c['surface_raised']};
    border: 1px solid {c['border_strong']};
    border-radius: {RADIUS['sm']}px;
    padding: 4px;
}}
QToolButton:hover {{
    background: #2A2A2D;
}}
QToolButton:disabled {{
    background: {c['surface_alt']};
    border-color: {c['border']};
}}
QMenu {{
    background: {c['surface_raised']};
    border: 1px solid {c['border_strong']};
    padding: 4px;
}}
QMenu::item {{
    padding: 6px 18px;
    border-radius: {RADIUS['sm']}px;
}}
QMenu::item:selected {{
    background: {c['selection']};
}}

/* ---------- Progress & log ---------- */
QProgressBar {{
    background: {c['surface_alt']};
    border: none;
    border-radius: 3px;
    max-height: 6px;
    min-height: 6px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    background: {c['seal']};
    border-radius: 3px;
}}
QPlainTextEdit#Log {{
    background: #0F0F10;
    border: 1px solid {c['border']};
    border-radius: {RADIUS['md']}px;
    padding: 8px;
    font-family: {mono};
    font-size: 12px;
    color: #C9C9C6;
    selection-background-color: {c['selection']};
}}
QLabel#StatusText {{
    font-weight: 500;
}}
QLabel#Mono {{
    font-family: {mono};
    font-size: 12px;
}}

/* ---------- Scrollbars ---------- */
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {c['border_strong']};
    border-radius: 3px;
    min-height: 28px;
}}
QScrollBar::handle:vertical:hover {{
    background: #4A4A4F;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {c['border_strong']};
    border-radius: 3px;
    min-width: 28px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    width: 0;
    height: 0;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}
QScrollArea {{
    background: transparent;
    border: none;
}}

/* ---------- Dialogs ---------- */
QDialog, QMessageBox, QInputDialog {{
    background: {c['surface']};
}}
QMessageBox QLabel {{
    color: {c['text']};
}}
QSplitter::handle {{
    background: transparent;
}}
"""


def _palette() -> QPalette:
    c = COLORS
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(c["bg"]))
    pal.setColor(QPalette.WindowText, QColor(c["text"]))
    pal.setColor(QPalette.Base, QColor(c["surface"]))
    pal.setColor(QPalette.AlternateBase, QColor(c["surface_alt"]))
    pal.setColor(QPalette.Text, QColor(c["text"]))
    pal.setColor(QPalette.PlaceholderText, QColor(c["text_subtle"]))
    pal.setColor(QPalette.Button, QColor(c["surface_raised"]))
    pal.setColor(QPalette.ButtonText, QColor(c["text"]))
    pal.setColor(QPalette.Highlight, QColor(c["selection"]))
    pal.setColor(QPalette.HighlightedText, QColor(c["text"]))
    pal.setColor(QPalette.ToolTipBase, QColor(c["surface_raised"]))
    pal.setColor(QPalette.ToolTipText, QColor(c["text"]))
    pal.setColor(QPalette.Link, QColor(c["seal"]))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, QColor(c["text_subtle"]))
    return pal


def apply_theme(app: QApplication) -> None:
    """Fusion style + dark palette + stylesheet. Fusion makes QSS render the
    same on macOS/Linux/Windows instead of mixing with native widget chrome."""
    load_fonts()
    # Qt-drawn dialogs everywhere (file pickers, message boxes, input dialogs),
    # so they follow this theme and look the same on Windows, Linux and macOS.
    QApplication.setAttribute(Qt.AA_DontUseNativeDialogs, True)
    app.setStyle("Fusion")
    app.setPalette(_palette())
    ui_font = QFont()
    ui_font.setFamilies(UI_FONT_FALLBACKS)
    ui_font.setPixelSize(13)
    app.setFont(ui_font)
    app.setStyleSheet(build_stylesheet())

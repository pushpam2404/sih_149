"""Small reusable building blocks so every page shares one visual language:
page headers, cards, stat tiles, status badges, callouts, styled buttons
and table defaults. Visual rules live in app/gui/theme.py; these only set
object names / properties that the stylesheet targets.
"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from app.gui.theme import COLORS, TONE_COLORS
from app.gui.widgets import icons

PAGE_MARGIN = 28
SECTION_GAP = 16


def button(text: str, variant: str = "secondary", icon_name: str | None = None, large: bool = False) -> QPushButton:
    # Leading space gives the icon breathing room; Qt has no icon-spacing QSS property.
    btn = QPushButton(f" {text}" if icon_name else text)
    if variant != "secondary":
        btn.setProperty("variant", variant)
    if large:
        btn.setProperty("size", "lg")
    if icon_name:
        on_solid = variant in ("primary", "danger")
        btn.setIcon(icons.icon(icon_name, (COLORS["on_primary"] if variant == "primary" else "#FFFFFF") if on_solid else COLORS["text_muted"]))
        btn.setIconSize(QSize(16, 16))
    btn.setCursor(Qt.PointingHandCursor)
    return btn


class Page(QScrollArea):
    """Page scaffold: title + subtitle header, optional header actions, and a
    vertical body layout (`self.body`) for cards.

    The page is a scroll area: when the window is shorter than the content
    (small laptop screens, or Windows display scaling at 125–150%), the page
    scrolls instead of squeezing cards on top of each other."""

    def __init__(self, title: str, subtitle: str, parent=None):
        super().__init__(parent)
        self.setObjectName("PageScroll")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        content = QWidget()
        content.setObjectName("Page")
        self.setWidget(content)
        outer = QVBoxLayout(content)
        outer.setContentsMargins(PAGE_MARGIN, 24, PAGE_MARGIN, PAGE_MARGIN)
        outer.setSpacing(SECTION_GAP + 4)

        header = QHBoxLayout()
        header.setSpacing(12)
        titles = QVBoxLayout()
        titles.setSpacing(4)
        title_label = QLabel(title)
        title_label.setObjectName("PageTitle")
        titles.addWidget(title_label)
        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("PageSubtitle")
        subtitle_label.setWordWrap(True)
        titles.addWidget(subtitle_label)
        header.addLayout(titles, 1)
        self.header_actions = QHBoxLayout()
        self.header_actions.setSpacing(8)
        header.addLayout(self.header_actions)
        header.setAlignment(self.header_actions, Qt.AlignTop)
        outer.addLayout(header)

        self.body = QVBoxLayout()
        self.body.setSpacing(SECTION_GAP)
        outer.addLayout(self.body, 1)


class Card(QFrame):
    """Rounded surface with an optional title row. Add content to `self.body`;
    put buttons for the title row in `self.actions`."""

    def __init__(self, title: str | None = None, subtitle: str | None = None, icon_name: str | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        self.actions = QHBoxLayout()
        self.actions.setSpacing(8)
        if title:
            head = QHBoxLayout()
            head.setSpacing(10)
            if icon_name:
                ic = QLabel()
                ic.setPixmap(icons.pixmap(icon_name, 18, COLORS["text_subtle"]))
                head.addWidget(ic, 0, Qt.AlignTop)
            texts = QVBoxLayout()
            texts.setSpacing(2)
            t = QLabel(title)
            t.setObjectName("CardTitle")
            texts.addWidget(t)
            if subtitle:
                s = QLabel(subtitle)
                s.setObjectName("CardSubtitle")
                s.setWordWrap(True)
                texts.addWidget(s)
            head.addLayout(texts, 1)
            head.addLayout(self.actions)
            layout.addLayout(head)

        self.body = QVBoxLayout()
        self.body.setSpacing(12)
        layout.addLayout(self.body, 1)


_BADGE_HEIGHT = 22
_BADGE_RADIUS = 10


class Badge(QLabel):
    """Pill-shaped status label. Always carries text, so meaning never
    depends on colour alone."""

    def __init__(self, text: str = "", tone: str = "neutral", parent=None):
        super().__init__(text, parent)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.setFixedHeight(_BADGE_HEIGHT)
        self.setAlignment(Qt.AlignCenter)
        self.set_tone(tone)

    def set_tone(self, tone: str) -> None:
        fg, bg = TONE_COLORS.get(tone, TONE_COLORS["neutral"])
        self.setStyleSheet(
            # Height is fixed in code (see __init__), and the radius stays below half of
            # it: Qt draws square corners when radius >= height / 2. Windows ignored a
            # stylesheet min-height and rendered the pill 18 px tall with square corners.
            f"background:{bg}; color:{fg}; border-radius:{_BADGE_RADIUS}px; padding:0 10px;"
            "font-size:11px; font-weight:600;"
        )

    def set(self, text: str, tone: str) -> None:
        self.setText(text)
        self.set_tone(tone)


class StatTile(QFrame):
    def __init__(self, label: str, icon_name: str, parent=None):
        super().__init__(parent)
        self.setObjectName("StatTile")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(8)
        self._icon = QLabel()
        name = QLabel(label)
        name.setObjectName("StatLabel")
        top.addWidget(name, 1)
        top.addWidget(self._icon, 0, Qt.AlignVCenter)
        layout.addLayout(top)

        self._value = QLabel("—")
        self._value.setObjectName("StatValue")
        layout.addWidget(self._value)
        self._caption = QLabel("")
        self._caption.setObjectName("StatCaption")
        self._caption.setWordWrap(True)
        layout.addWidget(self._caption)
        self._icon_name = icon_name
        self.set_tone("neutral")

    def set_tone(self, tone: str) -> None:
        # Stat tiles are numbers. A status dot appears only when the figure has a
        # state worth reading at a glance (the chain is intact, or broken).
        self._icon.setFixedSize(8, 8)
        if tone in ("neutral", "primary", "info"):
            self._icon.setVisible(False)
            return
        fg = COLORS["seal"] if tone == "success" else TONE_COLORS.get(tone, TONE_COLORS["neutral"])[0]
        self._icon.setStyleSheet(f"background:{fg}; border-radius:4px;")
        self._icon.setVisible(True)

    def set_value(self, value: str, caption: str = "", tone: str | None = None) -> None:
        self._value.setText(value)
        self._caption.setText(caption)
        if tone:
            self.set_tone(tone)


class Callout(QFrame):
    """Inline notice with an icon. tone='warning' (amber) or 'danger' (red)."""

    def __init__(self, text: str, tone: str = "warning", icon_name: str = "alert", parent=None):
        super().__init__(parent)
        self.setObjectName("DangerCallout" if tone == "danger" else "Callout")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)
        ic = QLabel()
        ic.setPixmap(icons.pixmap(icon_name, 16, COLORS["danger_text"] if tone == "danger" else COLORS["accent"]))
        layout.addWidget(ic, 0, Qt.AlignTop)
        self.label = QLabel(text)
        self.label.setWordWrap(True)
        self.label.setTextFormat(Qt.RichText)
        layout.addWidget(self.label, 1)


def field_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("FieldLabel")
    return label


def hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("Hint")
    label.setWordWrap(True)
    return label


def style_table(table: QTableWidget, row_height: int = 36) -> None:
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(row_height)
    table.setAlternatingRowColors(True)
    table.setShowGrid(False)
    table.setWordWrap(False)
    table.setFocusPolicy(Qt.StrongFocus)
    table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
    table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
    header = table.horizontalHeader()
    header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    header.setHighlightSections(False)
    header.setMinimumSectionSize(60)


class EmptyHint(QLabel):
    """Centered placeholder text shown over an empty table/list."""

    def __init__(self, text: str, parent: QWidget):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignCenter)
        self.setWordWrap(True)
        self.setStyleSheet(f"color:{COLORS['text_subtle']}; background:transparent; font-size:13px;")
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        parent.installEventFilter(self)
        self._reposition()

    def eventFilter(self, obj, event):  # noqa: N802 - Qt override
        if event.type() == event.Type.Resize:
            self._reposition()
        return False

    def _reposition(self) -> None:
        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(24, 40, max(parent.width() - 48, 10), max(parent.height() - 60, 10))

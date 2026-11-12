"""Type-to-confirm + acknowledgment dialog for destructive operations.

The OK button stays disabled until the user has typed the exact
confirmation token AND ticked the acknowledgment checkbox — this is the
GUI half of the safety story described in the plan (core-side enforcement
is app.core.devices.safety / the user_confirmed flag on run_drive_erase).
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QVBoxLayout,
)

from app.gui.theme import COLORS, mono_font
from app.gui.widgets import icons
from app.gui.widgets.ui import field_label


class ConfirmDestructiveDialog(QDialog):
    def __init__(self, warning_text: str, confirm_token: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Confirm destructive operation")
        self.setMinimumWidth(480)
        self._confirm_token = confirm_token

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)

        head = QHBoxLayout()
        head.setSpacing(12)
        ic = QLabel()
        ic.setPixmap(icons.pixmap("alert", 28, COLORS["danger_text"]))
        head.addWidget(ic, 0, Qt.AlignTop)
        title = QLabel("This action cannot be undone")
        title.setStyleSheet("font-size:17px; font-weight:600;")
        head.addWidget(title, 1)
        layout.addLayout(head)

        warning = QLabel(warning_text)
        warning.setWordWrap(True)
        warning.setTextInteractionFlags(Qt.TextSelectableByMouse)
        warning.setStyleSheet(
            f"background:{COLORS['danger_soft']}; border:1px solid #5C2530; border-radius:8px;"
            f"padding:12px; color:#FECACA;"
        )
        layout.addWidget(warning)

        layout.addWidget(field_label("Type the following to confirm:"))
        token = QLabel(confirm_token)
        token.setFont(mono_font(13))
        token.setTextInteractionFlags(Qt.TextSelectableByMouse)
        token.setStyleSheet(
            f"background:{COLORS['surface_raised']}; border:1px solid {COLORS['border_strong']};"
            "border-radius:6px; padding:6px 10px; font-weight:600;"
        )
        token.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        layout.addWidget(token, 0, Qt.AlignLeft)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Type the text shown above")
        self._input.setFont(mono_font(13))
        self._input.textChanged.connect(self._update_ok_state)
        layout.addWidget(self._input)

        self._ack = QCheckBox("I understand this action is irreversible and have selected the correct target.")
        self._ack.stateChanged.connect(self._update_ok_state)
        layout.addWidget(self._ack)

        self._buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        ok = self._buttons.button(QDialogButtonBox.Ok)
        ok.setText("Erase permanently")
        ok.setProperty("variant", "danger")
        ok.setCursor(Qt.PointingHandCursor)
        cancel = self._buttons.button(QDialogButtonBox.Cancel)
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.setDefault(True)
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        layout.addSpacing(4)
        layout.addWidget(self._buttons)

        self._update_ok_state()
        self._input.setFocus()

    def _update_ok_state(self) -> None:
        ok_enabled = self._input.text() == self._confirm_token and self._ack.isChecked()
        self._buttons.button(QDialogButtonBox.Ok).setEnabled(ok_enabled)

    @staticmethod
    def confirm(parent, warning_text: str, confirm_token: str) -> bool:
        dialog = ConfirmDestructiveDialog(warning_text, confirm_token, parent)
        return dialog.exec() == QDialog.Accepted

import html as html_escape
from datetime import datetime

from PySide6 import QtWidgets, QtGui

from .. import theme
from importlib import reload

reload(theme)


# ==========================================================
# LOG PANEL
# ==========================================================

class LogPanel(QtWidgets.QFrame):

    LEVELS = {
        "INFO":    {"label": "INFO",  "color": "#8ab4f8", "icon": "●"},
        "SUCCESS": {"label": "OK",    "color": "#5fd68a", "icon": "✔"},
        "WARNING": {"label": "WARN",  "color": "#e8b339", "icon": "⚠"},
        "ERROR":   {"label": "ERROR", "color": "#f0554c", "icon": "✖"},
    }

    def __init__(self, parent=None):
        """Initialize the log panel and build its interface."""
        super().__init__(parent)

        self.setObjectName("LogPanel")
        self.build_widgets()
        self.build_layout()

    # ------------------------------------------------------
    # UI
    # ------------------------------------------------------

    def build_widgets(self):
        """Create all widgets used by the log panel."""

        self.title = QtWidgets.QLabel("OUTPUT LOG")
        self.title.setStyleSheet(f"color: {theme.TEXT_MUTED}; letter-spacing: 1px; font-size: 11px;")

        self.clear_button = QtWidgets.QPushButton("Clear")
        self.clear_button.setFixedSize(60, 22)

        self.output = QtWidgets.QTextEdit()
        self.output.setReadOnly(True)
        self.output.setMinimumHeight(80)
        self.output.setStyleSheet(
            f"QTextEdit {{"
            f" background: {theme.SURFACE_ALT};"
            f" border: 1px solid {theme.BORDER};"
            f" border-radius: {theme.RADIUS_SM}px;"
            f" padding: 4px;"
            f"}}"
        )
        self.output.document().setDefaultFont(QtGui.QFont("Consolas", 9))

    def build_layout(self):
        """Build the log panel layout."""

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        header = QtWidgets.QHBoxLayout()
        header.addWidget(self.title)
        header.addStretch()
        header.addWidget(self.clear_button)

        layout.addLayout(header)
        layout.addWidget(self.output)

        self.clear_button.clicked.connect(self.clear)

    # ------------------------------------------------------
    # UI LOGIC
    # ------------------------------------------------------

    def write(self, message, level="INFO"):
        """Write a colored, timestamped message to the output log."""

        style = self.LEVELS.get(level, self.LEVELS["INFO"])
        timestamp = datetime.now().strftime("%H:%M:%S")
        safe_message = html_escape.escape(str(message)).replace("\n", "<br>")

        line = (
            '<div style="margin: 1px 0; white-space: pre-wrap;">'
            f'<span style="color:#6e6e6e;">{timestamp}</span>&nbsp;'
            f'<span style="color:{style["color"]}; font-weight:bold;">'
            f'{style["icon"]} {style["label"]:<5}</span>&nbsp;'
            f'<span style="color:#dcdcdc;">{safe_message}</span>'
            '</div>'
        )

        self.output.append(line)

        scrollbar = self.output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def clear(self):
        """Clear all messages from the output log."""
        self.output.clear()

from PySide6 import QtWidgets, QtCore


# ==========================================================
# SKIN TAB
# ==========================================================

class SkinTab(QtWidgets.QWidget):

    def __init__(self, parent=None):
        """Initialize the Skin tab."""
        super().__init__(parent)

        self.build_widgets()
        self.build_layout()

    # ------------------------------------------------------
    # UI
    # ------------------------------------------------------

    def build_widgets(self):
        """Create all widgets used by the Skin tab."""

        self.placeholder = QtWidgets.QLabel("Skin tools coming soon...")
        self.placeholder.setAlignment(QtCore.Qt.AlignCenter)
        self.placeholder.setStyleSheet("color: #888; font-size: 13px;")

    def build_layout(self):
        """Build the Skin tab layout."""

        layout = QtWidgets.QVBoxLayout(self)
        layout.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(self.placeholder)

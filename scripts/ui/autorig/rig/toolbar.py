from PySide6 import QtWidgets, QtCore

# ==========================================================
# TOOLBAR
# ==========================================================

class Toolbar(QtWidgets.QFrame):

    pageRequested = QtCore.Signal(str)

    def __init__(self,parent=None):
        super().__init__(parent)

        self.setObjectName("Toolbar")
        self.setFixedWidth(55)
        self.build_widgets()
        self.build_layout()

    # ------------------------------------------------------
    # UI
    # ------------------------------------------------------

    def build_widgets(self):

        pages = [
            ("⚙", "Settings"),
            ("🦴", "Modules"),
            ("💾", "Import/Export"),
            #("📦", "Assets"),
            #("💻", "Console")
        ]

        self.buttons = [(QtWidgets.QPushButton(icon), index) for icon, index in pages]

    def build_layout(self):

        layout = QtWidgets.QVBoxLayout(self)

        for button, index in self.buttons:

            def callback(checked=False, i=index):
                print("Bouton :", i)
                self.pageRequested.emit(i)

            button.clicked.connect(callback)

            layout.addWidget(button)

        layout.addStretch()
from PySide6 import QtWidgets, QtCore

from ...core.autorig.rigData import init_rigData
from . import theme
from importlib import reload

reload(init_rigData)
reload(theme)


# ==========================================================
# COLOR PICKER DIALOG
# ==========================================================

class ColorPickerDialog(QtWidgets.QDialog):

    def __init__(self, initial=(1.0, 1.0, 1.0), parent=None):
        """Initialize the color picker with an initial RGB value."""
        super().__init__(parent)

        self.setWindowTitle("Pick Color")
        self.setModal(True)

        self._rgb = tuple(initial)
        self._updating = False

        self.build_widgets()
        self.build_layout()
        self.create_connections()
        self.set_style()

        self.set_rgb(self._rgb)

    # ------------------------------------------------------
    # UI
    # ------------------------------------------------------

    def build_widgets(self):
        """Create all widgets used by the color picker."""

        self.preview = QtWidgets.QFrame()
        self.preview.setFixedHeight(60)
        self.preview.setFrameShape(QtWidgets.QFrame.StyledPanel)

        self.sliders = {}
        self.spinboxes = {}

        for channel in "RGB":
            slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
            slider.setRange(0, 255)

            spin = QtWidgets.QSpinBox()
            spin.setRange(0, 255)

            self.sliders[channel] = slider
            self.spinboxes[channel] = spin

        self.hex_edit = QtWidgets.QLineEdit()
        self.hex_edit.setMaxLength(7)
        self.hex_edit.setPlaceholderText("#RRGGBB")

        self.preset_buttons = []

        for side, colors in init_rigData.DEFAULT_COLORS.items():
            for name, rgb in colors.items():
                button = QtWidgets.QPushButton()
                button.setFixedSize(22, 22)
                button.setCursor(QtCore.Qt.PointingHandCursor)
                button.setToolTip(f"{side} - {name}")
                button.setProperty("rgb", tuple(rgb))

                self.style_swatch(button, rgb)

                self.preset_buttons.append(button)

        self.ok_button = QtWidgets.QPushButton("OK")
        self.cancel_button = QtWidgets.QPushButton("Cancel")

    def build_layout(self):
        """Build the color picker layout."""

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        main_layout.addWidget(self.preview)

        sliders_layout = QtWidgets.QFormLayout()
        sliders_layout.setSpacing(6)

        for channel in "RGB":
            row = QtWidgets.QHBoxLayout()
            row.addWidget(self.sliders[channel])
            row.addWidget(self.spinboxes[channel])

            sliders_layout.addRow(channel, row)

        main_layout.addLayout(sliders_layout)

        hex_layout = QtWidgets.QHBoxLayout()
        hex_layout.addWidget(QtWidgets.QLabel("Hex"))
        hex_layout.addWidget(self.hex_edit)

        main_layout.addLayout(hex_layout)

        main_layout.addWidget(QtWidgets.QLabel("Presets"))

        presets_frame = QtWidgets.QFrame()
        presets_grid = QtWidgets.QGridLayout(presets_frame)
        presets_grid.setSpacing(4)

        columns = 6

        for index, button in enumerate(self.preset_buttons):
            presets_grid.addWidget(button, index // columns, index % columns)

        main_layout.addWidget(presets_frame)

        buttons_layout = QtWidgets.QHBoxLayout()
        buttons_layout.addStretch()
        buttons_layout.addWidget(self.ok_button)
        buttons_layout.addWidget(self.cancel_button)

        main_layout.addLayout(buttons_layout)

    def create_connections(self):
        """Connect the color picker widgets to their actions."""

        for channel in "RGB":
            self.sliders[channel].valueChanged.connect(self.on_slider_changed)
            self.spinboxes[channel].valueChanged.connect(self.on_spinbox_changed)

        self.hex_edit.editingFinished.connect(self.on_hex_changed)

        for button in self.preset_buttons:
            button.clicked.connect(
                lambda checked=False, b=button: self.set_rgb(b.property("rgb"))
            )

        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)

    def set_style(self):
        """Apply the color picker stylesheet (dialog : own top-level window, doesn't inherit main_window.py's)."""

        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)

        self.setStyleSheet(
            theme.STYLESHEET
            + f"""
            QDialog {{
                background: {theme.BG};
            }}
            """
        )

    def style_swatch(self, button, rgb):
        """Paint a preset button with its RGB color."""

        r, g, b = [int(value * 255) for value in rgb]

        button.setStyleSheet(
            f"""
            QPushButton {{
                background-color: rgb({r},{g},{b});
                border: 1px solid #222;
                border-radius: 3px;
            }}
            """
        )

    # ------------------------------------------------------
    # UI LOGIC
    # ------------------------------------------------------

    def set_rgb(self, rgb):
        """Update every widget (sliders, spinboxes, hex, preview) from an RGB value."""

        self._rgb = tuple(rgb)
        self._updating = True

        for channel, value in zip("RGB", self._rgb):
            int_value = round(value * 255)

            self.sliders[channel].setValue(int_value)
            self.spinboxes[channel].setValue(int_value)

        self.hex_edit.setText(self.to_hex(self._rgb))
        self.update_preview()

        self._updating = False

    def on_slider_changed(self, _value):
        """Sync spinboxes/hex/preview when a slider moves."""

        if self._updating:
            return

        self.sync_from_channels(source="slider")

    def on_spinbox_changed(self, _value):
        """Sync sliders/hex/preview when a spinbox changes."""

        if self._updating:
            return

        self.sync_from_channels(source="spinbox")

    def sync_from_channels(self, source):
        """Read the R/G/B widgets (sliders or spinboxes) and propagate the value."""

        self._updating = True

        values = []

        for channel in "RGB":

            if source == "slider":
                value = self.sliders[channel].value()
                self.spinboxes[channel].setValue(value)
            else:
                value = self.spinboxes[channel].value()
                self.sliders[channel].setValue(value)

            values.append(value / 255.0)

        self._rgb = tuple(values)

        self.hex_edit.setText(self.to_hex(self._rgb))
        self.update_preview()

        self._updating = False

    def on_hex_changed(self):
        """Apply the hex field value, reverting it if invalid."""

        rgb = self.from_hex(self.hex_edit.text().strip())

        if rgb is None:
            self.hex_edit.setText(self.to_hex(self._rgb))
            return

        self.set_rgb(rgb)

    def update_preview(self):
        """Refresh the color preview swatch."""

        r, g, b = [int(value * 255) for value in self._rgb]

        self.preview.setStyleSheet(
            f"""
            QFrame {{
                background-color: rgb({r},{g},{b});
                border: 1px solid #555;
                border-radius: 4px;
            }}
            """
        )

    @staticmethod
    def to_hex(rgb):
        """Convert an RGB (0-1) tuple to a '#RRGGBB' string."""

        r, g, b = [max(0, min(255, round(value * 255))) for value in rgb]

        return f"#{r:02X}{g:02X}{b:02X}"

    @staticmethod
    def from_hex(text):
        """Convert a '#RRGGBB' (or 'RRGGBB') string to an RGB (0-1) tuple, or None if invalid."""

        text = text.lstrip("#")

        if len(text) != 6:
            return None

        try:
            r = int(text[0:2], 16) / 255.0
            g = int(text[2:4], 16) / 255.0
            b = int(text[4:6], 16) / 255.0
        except ValueError:
            return None

        return (r, g, b)

    def result_rgb(self):
        """Return the currently selected RGB value."""

        return self._rgb

    @staticmethod
    def getColor(initial=(1.0, 1.0, 1.0), parent=None):
        """Open the dialog and return the picked RGB, or None if cancelled."""

        dialog = ColorPickerDialog(initial=initial, parent=parent)

        if dialog.exec() == QtWidgets.QDialog.Accepted:
            return dialog.result_rgb()

        return None

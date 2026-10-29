from PySide6 import QtWidgets, QtCore

from . import log_panel, sliding_panel, main_panel, settings_panel, toolbar, guideSettings_panel
from ....core.autorig.modules import registry
from ....core import log

from importlib import reload

reload(log_panel)
reload(sliding_panel)
reload(main_panel)
reload(settings_panel)
reload(toolbar)
reload(guideSettings_panel)
reload(registry)
reload(log)


# ==========================================================
# RIG TAB
# ==========================================================

class RigTab(QtWidgets.QWidget):

    def __init__(self, parent=None):
        """Initialize the Rig tab (guides outliner, settings, modules, log)."""
        super().__init__(parent)

        self.settings = QtCore.QSettings("AlexisTools", "AutoRig")
        self.current_page = None

        self.build_widgets()
        self.build_layout()
        self.create_connections()
        self.load_settings()

        self.sync_settings_with_rig()

    # ------------------------------------------------------
    # UI
    # ------------------------------------------------------

    def build_widgets(self):
        """Create all widgets and splitters used by the Rig tab."""

        self.guideSettings_panel = guideSettings_panel.GuideSettingsPanel()
        self.settings_panel = settings_panel.SettingsPanel()
        self.main_panel = main_panel.MainPanel()
        self.log_panel = log_panel.LogPanel()
        log.register(self.log_panel.write)
        self.sliding_panel = sliding_panel.SlidingPanel()
        self.toolbar = toolbar.Toolbar()

        self.left_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.left_splitter.addWidget(self.guideSettings_panel)
        self.left_splitter.addWidget(self.main_panel)
        self.left_splitter.setSizes([300, 900])

        self.vertical_splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        self.vertical_splitter.addWidget(self.left_splitter)
        self.vertical_splitter.addWidget(self.log_panel)
        self.vertical_splitter.setSizes([650, 150])

        self.main_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.main_splitter.addWidget(self.vertical_splitter)
        self.main_splitter.addWidget(self.sliding_panel)
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 0)
        self.main_splitter.setSizes([1100, 0])

        self.create_panel_animation()

    def build_layout(self):
        """Create and apply the Rig tab layout."""

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        layout.addWidget(self.main_splitter)
        layout.addWidget(self.toolbar)

    # ------------------------------------------------------
    # UI LOGIC
    # ------------------------------------------------------

    def create_connections(self):
        """Connect all UI signals to their corresponding actions."""

        self.toolbar.pageRequested.connect(self.show_panel)

        self.main_panel.guideSelected.connect(self.guide_selected)
        self.main_panel.rigDataChanged.connect(
            self.sliding_panel.pages["Settings"].load_data
        )

        self.sliding_panel.pages["Settings"].update_button.clicked.connect(
            lambda: self.main_panel.refresh()
        )
        self.sliding_panel.pages["Settings"].update_button.clicked.connect(
            lambda: self.main_panel.select_rig_data(self.get_current_rig_name())
        )

        self.sliding_panel.pages["Settings"].create_button.clicked.connect(
            lambda: self.main_panel.refresh()
        )
        self.sliding_panel.pages["Settings"].create_button.clicked.connect(
            lambda: self.main_panel.select_rig_data(self.get_current_rig_name())
        )

        self.sliding_panel.pages["Modules"].create_clicked.connect(
            lambda module: self.sliding_panel.pages["Modules"].create_module(
                module,
                self.get_current_rig_name()
            )
        )
        self.sliding_panel.pages["Modules"].create_clicked.connect(
            lambda: self.main_panel.refresh()
        )
        self.sliding_panel.pages["Modules"].create_clicked.connect(
            lambda: self.main_panel.select_rig_data(self.get_current_rig_name())
        )

        self.sliding_panel.pages["Modules"].create_data_node.connect(
            self.module_created
        )

        self.sliding_panel.pages["Import/Export"].rigImported.connect(
            self.rig_imported
        )

        self.guideSettings_panel.attr_changed.connect(
            lambda: self.main_panel.refresh()
        )
        self.guideSettings_panel.attr_changed.connect(
            lambda: self.main_panel.select_rig_data(self.get_current_rig_name())
        )
        self.guideSettings_panel.attr_changed.connect(
            lambda guide_name: self.main_panel.select_guide(guide_name)
        )

    def create_panel_animation(self):
        """Create the animation used to open and close the sliding panel."""

        self.panel_animation = QtCore.QVariantAnimation(self)
        self.panel_animation.setDuration(300)
        self.panel_animation.setEasingCurve(QtCore.QEasingCurve.OutCubic)

        self.panel_animation.valueChanged.connect(
            self.update_panel_animation
        )

    def update_panel_animation(self, value):
        """Update the splitter sizes during the sliding panel animation."""

        sizes = self.main_splitter.sizes()
        total_width = sum(sizes)

        panel_width = int(value)
        main_width = max(0, total_width - panel_width)

        self.main_splitter.setSizes(
            [main_width, panel_width]
        )

    def animate_sliding_panel(self, target_width):
        """Animate the sliding panel toward the target width."""

        sizes = self.main_splitter.sizes()
        current_width = sizes[1]

        self.panel_animation.stop()
        self.panel_animation.setStartValue(current_width)
        self.panel_animation.setEndValue(target_width)

        self.panel_animation.start()

    def show_panel(self, page):
        """Show, change or close the requested sliding panel page."""

        if self.sliding_panel.opened and self.current_page == page:
            self.sliding_panel.collapse()
            self.animate_sliding_panel(0)
            self.current_page = None
            return

        self.sliding_panel.set_page(page)
        self.current_page = page

        if not self.sliding_panel.opened:
            self.sliding_panel.expand()
            self.animate_sliding_panel(
                self.sliding_panel.PANEL_WIDTH
            )

    @staticmethod
    def _as_int_sizes(value):
        """
        Normalise une valeur QSettings en liste d'int.

        QSettings peut relire une liste de tailles sous forme de chaînes
        (['300', '900']) ou d'une seule chaîne, ce que QSplitter.setSizes
        (Sequence[int]) refuse.
        """

        if value is None:
            return []

        if isinstance(value, (str, bytes)):
            value = [value]

        try:
            return [int(float(item)) for item in value]
        except (TypeError, ValueError):
            return []

    def load_settings(self):
        """Load saved splitter settings from QSettings."""

        sizes = self._as_int_sizes(self.settings.value("splitterSizes"))

        if sizes:
            self.left_splitter.setSizes(sizes)

        vertical_sizes = self._as_int_sizes(self.settings.value("verticalSizes"))

        if vertical_sizes:
            self.vertical_splitter.setSizes(vertical_sizes)

    def save_settings(self):
        """Save the current splitter settings to QSettings."""

        self.settings.setValue(
            "splitterSizes",
            self.left_splitter.sizes()
        )

        self.settings.setValue(
            "verticalSizes",
            self.vertical_splitter.sizes()
        )

    def sync_settings_with_rig(self):
        """
        Populate the Settings page with the rig_data restored/selected in
        main_panel on open, so 'rig_data' isn't None the first time a
        Create/Update/Create module button is clicked.
        """

        rig_data = self.main_panel.data_rig

        if rig_data:
            self.sliding_panel.pages["Settings"].load_data(rig_data)

    def get_current_rig_name(self):
        """Return the rig_name of the currently loaded Settings rig_data, or None."""

        rig_data = self.sliding_panel.pages["Settings"].rig_data

        return rig_data.rig_name if rig_data else None

    # ------------------------------------------------------
    # CORE
    # ------------------------------------------------------

    def module_created(self, data_node):
        """Sync the rig filter, refresh the outliner, then select the new module and its root."""

        settings_rig_data = self.sliding_panel.pages["Settings"].rig_data

        if settings_rig_data:
            self.main_panel.select_rig_data(settings_rig_data.rig_name)

        self.main_panel.refresh_outliner()

        self.main_panel.select_guide(data_node)

        base_guides_class = registry.get_base_guides_class()

        if base_guides_class:
            base_guides_class.select_root_node(data_node)

    def rig_imported(self):
        """Refresh the outliner and rig combo after a JSON import."""

        self.main_panel.refresh()

        settings_rig_data = self.sliding_panel.pages["Settings"].rig_data

        if settings_rig_data:
            self.main_panel.select_rig_data(settings_rig_data.rig_name)

    def guide_selected(self, guide):
        """Update the guide settings panel with the selected guide."""

        self.selected_guide = guide

        self.guideSettings_panel.set_node(
            self.selected_guide
        )

        print("Guide sélectionné :", guide)

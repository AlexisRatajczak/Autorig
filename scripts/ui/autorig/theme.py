# ==========================================================
# THEME
# ==========================================================

BG = "#14161f"
SURFACE = "#1a1d29"
SURFACE_LIGHT = "#2a2f42"
SURFACE_ALT = "#11131c"
BORDER = "#3a3f54"

TEXT = "#f5f6fa"
TEXT_MUTED = "#a7aec2"
TEXT_DIM = "#6b7188"

ACCENT_START = "#7c6cf5"
ACCENT_END = "#a78bfa"
ACCENT_HOVER_START = "#8d7ef8"
ACCENT_HOVER_END = "#b79cfd"
ACCENT_PRESSED_START = "#6a5bd6"
ACCENT_PRESSED_END = "#8f77e0"
ACCENT_SOFT = "rgba(124, 108, 245, 70)"

DISABLED_BG = "#20222e"
DISABLED_TEXT = "#767c8f"

RADIUS_XS = 4
RADIUS_SM = 6
RADIUS = 8
RADIUS_LG = 12


def _gradient(start, end, angle="x1:0, y1:0, x2:1, y2:0"):
    """qlineargradient QSS helper, horizontal par defaut."""
    return f"qlineargradient({angle}, stop:0 {start}, stop:1 {end})"


ACCENT_GRADIENT = _gradient(ACCENT_START, ACCENT_END)
ACCENT_HOVER_GRADIENT = _gradient(ACCENT_HOVER_START, ACCENT_HOVER_END)
ACCENT_PRESSED_GRADIENT = _gradient(ACCENT_PRESSED_START, ACCENT_PRESSED_END)


STYLESHEET = f"""
    QWidget {{
        background: transparent;
        color: {TEXT};
        font-size: 12px;
    }}

    #AutoRigTool {{
        background: {BG};
    }}

    QFrame {{
        background: {SURFACE};
        border: 1px solid {BORDER};
        border-radius: {RADIUS_LG}px;
    }}

    QLabel {{
        background: transparent;
        color: {TEXT};
        border: none;
    }}

    /* ---------------- TABS ---------------- */

    QTabWidget::pane {{
        background: {BG};
        border: none;
        top: 6px;
    }}

    QTabBar {{
        background: transparent;
    }}

    QTabBar::tab {{
        background: {SURFACE};
        color: {TEXT_MUTED};
        padding: 8px 4px;
        margin-right: 3px;
        min-width: 110px;
        border: none;
        border-top-left-radius: {RADIUS}px;
        border-top-right-radius: {RADIUS}px;
        font-weight: 600;
    }}

    QTabBar::tab:selected {{
        background: {ACCENT_GRADIENT};
        color: white;
    }}

    QTabBar::tab:hover:!selected {{
        background: {DISABLED_BG};
        color: {TEXT};
    }}

    /* ---------------- BUTTONS ---------------- */

    QPushButton {{
        background: {ACCENT_GRADIENT};
        color: white;
        font-weight: 600;
        border: none;
        border-radius: {RADIUS}px;
        padding: 6px 14px;
        min-height: 18px;
    }}

    QPushButton:hover {{
        background: {ACCENT_HOVER_GRADIENT};
    }}

    QPushButton:pressed {{
        background: {ACCENT_PRESSED_GRADIENT};
    }}

    QPushButton:disabled {{
        background: {DISABLED_BG};
        color: {DISABLED_TEXT};
    }}

    QToolButton {{
        background: {SURFACE_ALT};
        color: {TEXT};
        border: none;
        border-radius: {RADIUS_SM}px;
        padding: 6px;
    }}

    QToolButton:hover {{
        background: {DISABLED_BG};
    }}

    /* ---------------- FIELDS ---------------- */

    QLineEdit,
    QTextEdit,
    QComboBox {{
        background: {SURFACE_ALT};
        color: {TEXT};
        border: 1px solid {BORDER};
        border-radius: {RADIUS_SM}px;
        padding: 4px 8px;
        selection-background-color: {ACCENT_START};
    }}

    /* QSpinBox/QDoubleSpinBox a part : les fleches +/- prennent deja de la
       place sur un champ generalement etroit (ex. les weights sliders du
       Blendshape tab) - un padding/rayon plus petits laissent de la place
       a la valeur au lieu de la faire disparaitre sous la bordure. */
    QSpinBox,
    QDoubleSpinBox {{
        background: {SURFACE_ALT};
        color: {TEXT};
        border: 1px solid {BORDER};
        border-radius: {RADIUS_XS}px;
        padding: 2px 2px 2px 4px;
        selection-background-color: {ACCENT_START};
    }}

    QSpinBox::up-button, QSpinBox::down-button,
    QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
        width: 11px;
        border: none;
        background: transparent;
    }}

    QLineEdit:focus,
    QTextEdit:focus,
    QSpinBox:focus,
    QDoubleSpinBox:focus,
    QComboBox:focus {{
        border: 1px solid {ACCENT_START};
    }}

    QComboBox::drop-down {{
        border: none;
        width: 20px;
    }}

    QComboBox QAbstractItemView {{
        background: {SURFACE_ALT};
        color: {TEXT};
        border: 1px solid {BORDER};
        selection-background-color: {ACCENT_START};
        outline: none;
    }}

    /* ---------------- LISTS / TREES ---------------- */

    QTreeWidget,
    QListWidget {{
        background: {SURFACE_ALT};
        color: {TEXT};
        border: 1px solid {BORDER};
        border-radius: {RADIUS_SM}px;
        outline: none;
    }}

    QTreeWidget::item,
    QListWidget::item {{
        padding: 4px;
        border: none;
    }}

    QTreeWidget::item:selected,
    QListWidget::item:selected {{
        background: {ACCENT_SOFT};
        color: white;
        border-radius: 6px;
    }}

    QTreeWidget::item:hover,
    QListWidget::item:hover {{
        background: {DISABLED_BG};
    }}

    QHeaderView::section {{
        background: {SURFACE};
        color: {TEXT_MUTED};
        border: none;
        padding: 4px;
    }}

    /* ---------------- SLIDER ---------------- */

    QSlider::groove:horizontal {{
        height: 4px;
        background: {DISABLED_BG};
        border-radius: 2px;
    }}

    QSlider::sub-page:horizontal {{
        background: {ACCENT_GRADIENT};
        border-radius: 2px;
    }}

    QSlider::add-page:horizontal {{
        background: {DISABLED_BG};
        border-radius: 2px;
    }}

    QSlider::handle:horizontal {{
        background: white;
        width: 12px;
        height: 12px;
        margin: -5px 0;
        border-radius: 6px;
    }}

    /* ---------------- SCROLLBAR ---------------- */

    QScrollBar:vertical {{
        background: transparent;
        width: 10px;
        margin: 0;
    }}

    QScrollBar::handle:vertical {{
        background: {BORDER};
        border-radius: 5px;
        min-height: 24px;
    }}

    QScrollBar::handle:vertical:hover {{
        background: {ACCENT_START};
    }}

    QScrollBar::add-line:vertical,
    QScrollBar::sub-line:vertical {{
        height: 0;
    }}

    QScrollBar:horizontal {{
        background: transparent;
        height: 10px;
        margin: 0;
    }}

    QScrollBar::handle:horizontal {{
        background: {BORDER};
        border-radius: 5px;
        min-width: 24px;
    }}

    QScrollBar::handle:horizontal:hover {{
        background: {ACCENT_START};
    }}

    QScrollBar::add-line:horizontal,
    QScrollBar::sub-line:horizontal {{
        width: 0;
    }}

    /* ---------------- SPLITTER ---------------- */

    QSplitter::handle {{
        background: {BG};
    }}

    QSplitter::handle:horizontal {{
        width: 4px;
    }}

    QSplitter::handle:vertical {{
        height: 4px;
    }}

    /* ---------------- MENU ---------------- */

    QMenu {{
        background: {SURFACE};
        color: {TEXT};
        border: 1px solid {BORDER};
        border-radius: {RADIUS_SM}px;
        padding: 4px;
    }}

    QMenu::item {{
        padding: 6px 16px;
        border-radius: 6px;
    }}

    QMenu::item:selected {{
        background: {ACCENT_GRADIENT};
        color: white;
    }}

    QMenu::separator {{
        height: 1px;
        background: {BORDER};
        margin: 4px 8px;
    }}

    /* ---------------- CHECK / RADIO ---------------- */

    QCheckBox,
    QRadioButton {{
        background: transparent;
        color: {TEXT};
        spacing: 6px;
    }}

    QCheckBox::indicator,
    QRadioButton::indicator {{
        width: 14px;
        height: 14px;
        background: {SURFACE_ALT};
        border: 1px solid {BORDER};
    }}

    QCheckBox::indicator {{
        border-radius: 4px;
    }}

    QRadioButton::indicator {{
        border-radius: 7px;
    }}

    QCheckBox::indicator:checked,
    QRadioButton::indicator:checked {{
        background: {ACCENT_GRADIENT};
        border: 1px solid {ACCENT_START};
    }}

    QCheckBox::indicator:hover,
    QRadioButton::indicator:hover {{
        border: 1px solid {ACCENT_START};
    }}

    /* ---------------- TOOLBAR ---------------- */
    /*
      Ex. rig/toolbar.py : rail d'icones a gauche du Rig tab - fond plus
      clair que les cartes/le fond general pour le mettre en valeur, avec
      des boutons plats (pas le pilule degrade generique des QPushButton)
      pour rester lisible en rail vertical compact.
    */

    #Toolbar {{
        background: {SURFACE_LIGHT};
        border: 1px solid {BORDER};
        border-radius: {RADIUS_LG}px;
    }}

    #Toolbar QPushButton {{
        background: transparent;
        color: {TEXT_MUTED};
        border: none;
        border-radius: {RADIUS_SM}px;
        padding: 8px;
        font-size: 15px;
        font-weight: 400;
        min-height: 0;
    }}

    #Toolbar QPushButton:hover {{
        background: {DISABLED_BG};
        color: {TEXT};
    }}

    #Toolbar QPushButton:pressed,
    #Toolbar QPushButton:checked {{
        background: {ACCENT_GRADIENT};
        color: white;
    }}

    QGroupBox {{
        background: {SURFACE};
        border: 1px solid {BORDER};
        border-radius: {RADIUS_LG}px;
        margin-top: 14px;
        font-weight: 600;
        color: {TEXT_MUTED};
    }}

    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 4px;
    }}
"""

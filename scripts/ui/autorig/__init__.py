def show():
    """Affiche (ou recree) la fenetre principale de l'autorig."""

    from importlib import reload
    from . import main_window

    reload(main_window)

    return main_window.MainWindow.show_window()

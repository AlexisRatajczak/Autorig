"""Modeling checker for Maya.

    import modeling_checker
    modeling_checker.show()
"""


def show():
    from importlib import reload
    from ..modeling_checker import ui

    reload(ui)

    return ui.show()


def reload_all():
    """Reload every module after editing the code, without restarting Maya."""
    import sys

    from ..modeling_checker import ui

    ui.close()
    for name in [name for name in sys.modules if name.startswith(__name__ + ".")]:
        del sys.modules[name]
    return show()

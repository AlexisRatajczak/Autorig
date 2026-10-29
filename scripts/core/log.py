import maya.cmds as cmds


# ==========================================================
# LOG
# ==========================================================
#
# Point de passage unique pour les logs de creation/erreur du pipeline
# (core), independant de l'UI. La UI (Rig tab) s'enregistre via
# register() pour miroiter ces messages dans son panneau "OUTPUT LOG" ;
# sans UI enregistree, seuls print()/cmds.warning() s'appliquent.

_listeners = []


def register(listener):
    """Enregistre un callable(message, level) pour recevoir les logs."""
    if listener not in _listeners:
        _listeners.append(listener)


def unregister(listener):
    if listener in _listeners:
        _listeners.remove(listener)


def _dispatch(message, level):
    for listener in list(_listeners):
        try:
            listener(message, level)
        except Exception:
            pass


def info(message):
    print(f"[INFO] {message}")
    _dispatch(message, "INFO")


def success(message):
    print(f"[OK] {message}")
    _dispatch(message, "SUCCESS")


def warning(message):
    cmds.warning(message)
    _dispatch(message, "WARNING")


def error(message):
    cmds.warning(message)
    _dispatch(message, "ERROR")

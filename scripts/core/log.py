# ====================================================================================================================
# LOG
# ====================================================================================================================
#
#   Single entry point for the pipeline logs, independent of the UI. The UI (Rig tab) calls register()
#   to mirror them in its OUTPUT LOG panel; without a listener only print() / cmds.warning() run.
#
#   register(listener)      - add a callable(message, level)
#   unregister(listener)    - remove a listener
#   _dispatch(message, level) - send a message to every listener
#   info / success / warning / error(message) - log a message
#
# ====================================================================================================================

import maya.cmds as cmds


_listeners = []


def register(listener):
    """Register a callable(message, level) that receives the logs."""
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

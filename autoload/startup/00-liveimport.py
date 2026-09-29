"""
IPython startup file installed by the liveimport-autoload package.

Imports LiveImport at kernel startup so notebooks can use ``%%liveimport`` or
``#_%%liveimport`` in their very first cell, with no bootstrap import.  Install
with ``pip install liveimport[autoload]``; disable permanently with ``pip
ininstall liveimport-autoload``.

The startup file does nothing if the Python runtime does not include an IPython
interactive shell, LiveImport is not installed, or LIVEIMPORT_NO_AUTOLOAD is in
the environment with any value other than "0" or "false" (by case-insenstive
comparison).
"""

def _liveimport_autoload():

    import os
    no_autoload = os.environ.get("LIVEIMPORT_NO_AUTOLOAD")
    if no_autoload is not None and no_autoload.lower() not in ("0", "false"):
        return

    try:
        try:
            import IPython
            if IPython.get_ipython() is None:
                return
        except ModuleNotFoundError as ex:
            if ex.name == "IPython":
                return

        try:
            import liveimport
        except ModuleNotFoundError as ex:
            if ex.name == "liveimport":
                return

    except Exception:
        import warnings
        warnings.warn("LiveImport autoload failed", RuntimeWarning)


_liveimport_autoload()
del _liveimport_autoload

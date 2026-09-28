"""
IPython startup file installed by the liveimport-autoload package.

Imports LiveImport at kernel startup so notebooks can use ``%%liveimport`` or
``#_%%liveimport`` in their very first cell, with no bootstrap import.  Install
with ``pip install liveimport[autoload]``; disable permanently with ``pip
uninstall liveimport-autoload``, or for one kernel by setting
LIVEIMPORT_NO_AUTOLOAD=1 in its environment.
"""

def _liveimport_autoload():
    import os
    if os.environ.get("LIVEIMPORT_NO_AUTOLOAD", "") not in ("", "0", "false"):
        return
    try:
        import IPython
        if IPython.get_ipython() is None: #type:ignore
            return
        import liveimport  # noqa: F401
    except Exception:
        import warnings
        warnings.warn("LiveImport autoload failed", RuntimeWarning)


_liveimport_autoload()
del _liveimport_autoload
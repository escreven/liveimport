"""Automatically reload modified Python modules in notebooks and scripts.

See `the user guide
<https://liveimport.readthedocs.io/en/latest/userguide.html>`_.
"""

__version__ = "1.3.1dev1"

__all__ = ("register", "sync", "auto_sync", "hidden_cell_magic",
           "ReloadEvent", "ModuleError", "workspace")

from ._core import (register, sync, poll_lazy_imports,
                    workspace, ReloadEvent, ModuleError)

from ._nbi import auto_sync, hidden_cell_magic

#
# Pull up for debugging and testing
#

from ._core import _MODULE_TABLE, _REIFY_WATCH, _WORKSPACE, _is_lazy

from ._debug import (
    _dump, _is_registered, _is_tracked,
    _hash_state, _clear_all_state, _verify,
    _reload_liveimport)

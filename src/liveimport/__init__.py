"""Automatically reload modified Python modules in notebooks and scripts.

See `the user guide
<https://liveimport.readthedocs.io/en/latest/userguide.html>`_.
"""

from __future__ import annotations

__version__ = "1.2.4.dev1"

__all__ = ("register", "sync", "auto_sync", "hidden_cell_magic",
           "ReloadEvent", "ModuleError", "workspace")

from ._core import register, sync, ReloadEvent, ModuleError
from ._nbi import auto_sync, hidden_cell_magic
from ._workspace import workspace

#
# Pull up for debugging and testing
#

from ._core import _MODULE_TABLE

from ._debug import (
    _dump, _is_registered, _is_tracked,
    _hash_state, _clear_all_state, _verify)

from ._workspace import _WORKSPACE

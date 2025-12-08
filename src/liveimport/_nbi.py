import math
import re
import time
import IPython
from IPython.display import display, Markdown
from IPython.core.magic import Magics, magics_class, cell_magic
from IPython.core.error import UsageError
from IPython.core.inputtransformer2 import TransformerManager

from ._core import ModuleError, sync, register


#
# Notebook integration.
#

_IPYTHON_SHELL = IPython.get_ipython()  #type:ignore

_transform_cell = TransformerManager().transform_cell

#
# Implement %%liveimport cell magic as described in user guide.
# Note that re-registering magics does not cause accumulation.
#

@magics_class
class _LiveImportMagics(Magics):
    @cell_magic
    def liveimport(self,line:str,cell:str):
        """Usage: ``%%liveimport [-c|--clear]``\n
        Run a Python cell block, then register all top-level imports.  Option
        ``--clear`` deletes existing registrations first.
        """
        args = self.parse_options(line,"c","clear")
        if args[1]:
            raise UsageError(
                "Extraneous %%liveimport arguments: " + str(args[1]))
        clear = 'c' in args[0] or 'clear' in args[0]
        text = _transform_cell(cell)
        if (shell := self.shell) is None:
            raise RuntimeError("No IPython shell for %%liveimport magic")
        if shell.run_cell(cell).error_in_exec is None:
            register(shell.user_ns, text, clear=clear,
                     allow_other_statements=True)

#
# Display the given reload events as a Markdown console block.
#

def _display_reload_events(events):
    text = '\n'.join(str(event) for event in events)
    display(Markdown(f"```console\n{text}\n```"))

#
# Handle pre and post cell run events to implement automatic syncing.  We avoid
# reinstalling event handlers on module reload so the registrations don't
# accumulate.
#
# We defer displaying reload reports when the first cell after a grace period
# appears to be a bootstrap cell, a cell executed by a frontend to configure
# the kernel in some way.  We judge a cell to be bootstrap if store_history is
# False.  The deferred reports are displayed (if enabled) when a non-bootstrap
# cell is executed before the grace period expires.  If that doesn't happen,
# the deferred reports are never displayed -- we don't want reports showing up
# at surprising times.
#

class _LiveImportHandler:
    __slots__ = ("autosync_enabled", "autosync_report",
                 "autosync_grace", "post_cell_time",
                 "deferred_events")

    def __init__(self):
        self.autosync_enabled = True
        self.autosync_grace   = 1.0
        self.autosync_report  = True
        self.post_cell_time   = -math.inf
        self.deferred_events  = []

    def pre_run_cell(self,info):
        if not self.autosync_enabled:
            return
        looks_like_bootstrap = not info.store_history
        deferred_events = self.deferred_events
        now = time.monotonic()
        if now - self.post_cell_time >= self.autosync_grace:
            deferred_events.clear()
            events = []
            try:
                sync(observer=lambda event: events.append(event))
                sync_ex = None
            except Exception as ex:
                sync_ex = ex
            if events:
                if looks_like_bootstrap:
                    self.deferred_events = events
                elif self.autosync_report:
                    _display_reload_events(events)
            if isinstance(sync_ex,ModuleError):
                sync_ex = sync_ex.__cause__
            if sync_ex is not None:
                raise sync_ex.with_traceback(sync_ex.__traceback__)
        elif deferred_events and not looks_like_bootstrap:
            if self.autosync_report:
                _display_reload_events(deferred_events)
            deferred_events.clear()

    def post_run_cell(self,result):
        self.post_cell_time = time.monotonic()

#
# Input transformer that unhides %%liveimport magic.  It is installed and
# deinstalled by hidden_cell_magic() as needed.
#

_HIDDEN_LIVEMAGIC_RE = re.compile(r"#_%%liveimport\b")

def _unhide_cell_magic(lines:list[str]):
    if lines and lines[0].startswith("#_%%"):
        if _HIDDEN_LIVEMAGIC_RE.match(line := lines[0]):
            return [ lines[i] if i > 0 else line[2:]
                     for i in range(len(lines)) ]
    return lines

#
# Register magic, event handlers, and unhiding once at initial load.
#

if "_did_register" not in globals():
    _did_register = True
    if _IPYTHON_SHELL is not None:
        _IPYTHON_SHELL.register_magics(_LiveImportMagics)
        _HANDLER = _LiveImportHandler()
        _IPYTHON_SHELL.events.register('pre_run_cell',_HANDLER.pre_run_cell)
        _IPYTHON_SHELL.events.register('post_run_cell',_HANDLER.post_run_cell)
        _IPYTHON_SHELL.input_transformers_cleanup.append(_unhide_cell_magic)


############################################################################
#                                PUBLIC API
############################################################################

def auto_sync(enabled:bool|None=None,*,
              grace:float|None=None,
              report:bool|None=None) -> None:
    """
    Configure automatic sync behavior.  By default, automatic syncing is
    enabled with a grace period of 1.0 seconds and reloads are reported.

    :param enabled: LiveImport syncs whenever a notebook cell runs if and only
        if `enabled` is true and a grace period since the end of the last cell
        execution has expired.

    :param grace: The minimum time in seconds that must pass between the end of
        one cell execution and the beginning of the another before LiveImport
        will sync.  The grace period inhibits syncing between cell executions
        during a multi-cell run, such as running the entire notebook.

    :param report: Use Markdown console blocks to report when modules are
        reloaded by automatic syncing.
    """
    if _IPYTHON_SHELL is None: return
    if enabled is not None: _HANDLER.autosync_enabled = enabled
    if grace   is not None: _HANDLER.autosync_grace   = grace
    if report  is not None: _HANDLER.autosync_report  = report


def hidden_cell_magic(enabled:bool|None=None) -> None:
    """
    Configure hidden cell magic.

    :param enabled: Notebook cells that begin with ``#_%%liveimport`` run as if
        they began with ``%%livemagic`` if and only if `enabled` is true.  This
        makes LiveImport cell magic transparent to IDEs like Visual Studio
        Code, yet still function as desired.  Hidden cell magic is enabled by
        default.
    """
    if _IPYTHON_SHELL is None: return
    if enabled is None: return
    cleanup = _IPYTHON_SHELL.input_transformers_cleanup
    for i, transformer in enumerate(cleanup):
        if getattr(transformer,'__module__',None) == 'liveimport._nbi':
            del cleanup[i]
            break
    if enabled:
        cleanup.append(_unhide_cell_magic)

"""Automatically reload modified Python modules in notebooks and scripts.

Overview
--------

LiveImport eliminates the need to restart a notebook's Python server to
reimport code under development in external files.  Suppose you are maintaining
symbolic math code in ``symcode.py``, LaTex formatting utilities in
``printmath.py``, and a simulator in ``simulator.py``.  In the first cell of a
notebook, you might write

  .. code:: python

      import liveimport
      import numpy as np
      import matplotlib.plot as plot

      import symcode
      from printmath import print_math, print_equations as print_eq
      from simulator import *

      liveimport.register(globals(),\"\"\"
      import symcode
      from printmath import print_math, print_equations as print_eq
      from simulator import *
      \"\"\", clear=True)

Then, whenever you run cells, LiveImport will reload any of ``symcode``,
``printmath``, and ``simulator`` that have changed since they were registered
or last reloaded.  LiveImport deems a module changed when its source file
modification time changes.

LiveImport also updates imported module symbols.  For example, if you modify
``printmath.py``, LiveImport will reload ``printmath`` and bind ``print_math``
and ``print_eq`` in the global namespace to the new definitions.  Similarly, if
you update ``simulator.py``, LiveImport will create or update bindings for
every public symbol in ``simulator`` — that is, every symbol defined in the
module that does not start with ``_``, unless there is an ``__all__`` property
defined for the module, in which case it acts on only those symbols, just like
``from simulator import *``.

Modules referenced by registered import statements are called tracked modules.
The process of bringing registered imports up to date by reloading tracked
modules and updating symbols is called syncing.

The ``clear=True`` option used above causes `register()`:func: to discard all
prior import registrations targeting the given namespace.  So, if you wanted to
stop tracking modifications to ``symcode.py``, you could simply delete ``import
symcode`` from the `register()`:func: `importstmts` argument and rerun the
cell.

Cell Magic
----------

As an alternative to `register()`:func:, LiveImport defines a cell magic
``%%liveimport`` which both executes the cell content and registers every
top-level [#f1]_ import statement.  Option ``--clear`` of ``%%liveimport`` has
the same effect as ``clear=True`` with `register()`:func:.  So, you could split
the example cell above into two, making the second

  .. code:: python

      %%liveimport --clear
      import symcode
      from printmath import print_math, print_equations as print_eq
      from simulator import *

No `register()`:func: call is required.  Unfortunately, Visual Studio Code and
possibly other environments do not analyze magic cell content, making
``%%liveimport`` use awkward.  However, there is a workaround: calling
`hidden_cell_magic(enabled=True)<hidden_cell_magic>`:func: causes
``#_%%liveimport`` lines at the beginning of cells to act just like
``%%liveimport`` when the cell is run, and since ``#_%%liveimport`` is a Python
comment, Visual Studio Code and other environments do analyze the content.

A complete cell magic example equivalent to the first begins with cell

  .. code:: python

      import liveimport
      import numpy as np
      import matplotlib.plot as plot
      liveimport.hidden_cell_magic(enabled=True)

which is followed by cell

  .. code:: python

      #_%%liveimport --clear
      import symcode
      from printmath import print_math, print_equations as print_eq
      from simulator import *

Dependency Analysis
-------------------

LiveImport analyzes top-level import dependencies between tracked
modules to ensure reloading is consistent with those dependencies.  Suppose
``simulator`` imports ``symcode``.  Then, if you modify ``symcode.py``,
LiveImport reloads ``simulator`` after it reloads ``symcode`` even if
``simulator.py`` has not changed.  If you do modify both, LiveImport takes care
to reload ``symcode`` first.

Reload Reports
--------------

By default, LiveImport uses Markdown console blocks to report when it
automatically reloads modules in a notebook, something like

    .. code:: console

        Reloaded symcode modified 18 seconds ago
        Reloaded simulator because symcode reloaded

You can disable these reports by calling
`auto_sync(report=False)<auto_sync>`:func:.

Outside of Notebooks
--------------------

You can use LiveImport outside of notebook environments, but in that case,
there is no automatic syncing, so you must call `sync()`:func: explicitly.  You
can also disable automatic syncing in a notebook by calling
`auto_sync(enabled=False) <auto_sync>`:func: and rely on explicit syncing
instead.

.. [#f1] A "top-level import" is any ``import ...`` or ``from ... import ...``
   statement in Python source that is not nested within another Python
   construct such as an ``if`` or ``try`` statement.
"""
__version__ = "0.9.3"

import math
import re
import sys
import ast
import textwrap
import time
from types import ModuleType
from os.path import getmtime
from importlib import reload
from typing import Any, Callable, Literal, NoReturn, cast
import IPython
from IPython.display import display, Markdown
from IPython.core.magic import Magics, magics_class, cell_magic

__all__ = ("register", "sync", "auto_sync", "hidden_cell_magic",
           "ReloadEvent", "ModuleError")

#
# ========================= NOTEBOOK INTEGRATION =========================
#

_IPYTHON_SHELL = IPython.get_ipython()  #type:ignore

#
# Implement %%liveimport cell magic as described in the module docstring.
# Note that re-registering magics do not cause accumulation.
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
            print("Bad %%liveimport arguments:",args[1])
            return
        clear = 'c' in args[0] or 'clear' in args[0]
        text = "\n".join(line for line in cell.split('\n')
            if len(line) == 0 or line[0] != '%' and line[0] != '!')
        imports = _extract_imports(text,True)
        if (shell := self.shell) is None:
            raise RuntimeError("No IPython shell for %%liveimport magic")
        if shell.run_cell(cell).error_in_exec is None:
            _register_imports(shell.user_ns,imports,clear)

if _IPYTHON_SHELL is not None:
    _IPYTHON_SHELL.register_magics(_LiveImportMagics)

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

class _LiveImportHandler:
    __slots__ = ("autosync_enabled", "autosync_report",
                 "autosync_grace", "post_cell_time")

    def __init__(self):
        self.autosync_enabled = True
        self.autosync_grace   = 1.0
        self.autosync_report  = True
        self.post_cell_time   = -math.inf

    def pre_run_cell(self,info):
        if self.autosync_enabled:
            now = time.monotonic()
            if now - self.post_cell_time >= self.autosync_grace:
                events = []
                try:
                    sync(observer=lambda event: events.append(event))
                    sync_ex = None
                except Exception as ex:
                    sync_ex = ex
                if events:
                    _display_reload_events(events)
                if isinstance(sync_ex,ModuleError):
                    sync_ex = sync_ex.__cause__
                if sync_ex is not None:
                    raise sync_ex.with_traceback(sync_ex.__traceback__)

    def post_run_cell(self,result):
        self.post_cell_time = time.monotonic()

try:
    _IPYTHON_SHELL is None or _HANDLER #type:ignore
except:
    _HANDLER = _LiveImportHandler()
    if _IPYTHON_SHELL is not None:
        _IPYTHON_SHELL.events.register('pre_run_cell',_HANDLER.pre_run_cell)
        _IPYTHON_SHELL.events.register('post_run_cell',_HANDLER.post_run_cell)

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
# =========================== IMPORT MANAGEMENT ===========================
#

#
# _Bindings is None for "import A" imports, and "*" or a (<name>,<nameas>) pair
# list for "from A import ..." statements.
#

_Bindings = None|Literal["*"]|list[tuple[str,str]]

#
# Each registered import statement is transformed into one or more _Import
# directives.  Field modulename is always an absolute module name.  Field
# modulasname is the symbol in the target namespace referencing the loaded
# module.  It is None iff the directive is based on a "from ..." import.
#

class _Import:
    __slots__ = "modulename", "moduleasname", "bindings"

    def __init__(self, modulename:str, moduleasname:str|None,
                 bindings:_Bindings):
        self.modulename   = modulename
        self.moduleasname = moduleasname
        self.bindings     = bindings

    #
    # The string represention is an equivalent import statement.
    #

    def __str__(self) -> str:
        def alias_str(name,asname):
            return (name if asname is None or name == asname
                    else name + " as " + asname)
        modulename = self.modulename
        bindings = self.bindings
        if bindings is None:
            return "import " + alias_str(modulename,self.moduleasname)
        else:
            prefix = "from " + modulename + " import "
            if bindings == '*':
                return prefix + '*'
            else:
                return prefix + ", ".join(
                    alias_str(name,asname) for name, asname in bindings)

    def missing_import(self, issue:str) -> NoReturn:
        raise ValueError(f"{issue}; missing {self}?")

    #
    # Return the module instance referenced by the directive, raising a
    # ValueError exception if there is evidence an equivalent import statement
    # has not executed.
    #

    def require_imported(self, namespace:dict[str,Any]) -> ModuleType:
        modulename = self.modulename
        moduleasname = self.moduleasname
        bindings = self.bindings
        if (module := sys.modules.get(self.modulename)) is None:
            self.missing_import(f"Module {modulename} not loaded")
        modulesym = moduleasname
        if bindings is None and modulesym is None:
            modulesym = modulename.split('.',1)[0]
        if modulesym is not None and modulesym not in namespace:
            self.missing_import(f"No symbol {modulesym} in namespace")
        if type(bindings) is list:
            for name, asname in bindings:
                if not hasattr(module,name):
                    self.missing_import(f"No symbol {name} in {modulename}")
                if asname not in namespace:
                    self.missing_import(f"No symbol {asname} in namespace")
        return module

#
# A _Projection is mapping of module symbols into a namespace.  There is a
# projection for every tracked module with imports registered in a namespace,
# possibly an empty one.
#

class _Projection:
    __slots__ = "namespace", "aliases", "star"

    aliases : set[tuple[str,str]]

    def __init__(self, namespace:dict[str, Any]):
        self.namespace = namespace
        self.aliases   = set()
        self.star      = False

#
# Information LiveImport tracks about a module in _MODULE_TABLE.
#

class _ModuleInfo:
    __slots__ = ("module", "file", "parent",
                 "mtime", "projections", "dependencies",
                 "next_mtime", "mark")

    projections : dict[int,_Projection]

    def __init__(self, module:ModuleType):

        spec = module.__spec__
        if spec is None:
            raise ValueError("Module {module.__name__} has no spec")

        if not spec.has_location:
            raise ValueError("Module {module.__name__} has no associated file")

        assert (file := spec.origin) is not None
        assert (parent := spec.parent) is not None

        self.module      = module         # loaded module instance
        self.file        = file           # source file name 
        self.parent      = parent         # parent package or ''
        self.mtime       = getmtime(file) # last known modification time
        self.projections = dict()         # projections keyed by namespace id
        self.next_mtime  = self.mtime     # see sync()
        self.mark        = 0              # see sync()

        self.analyze_dependencies()

    #
    # Return the names of modules possibly referenced by top level import
    # statements of the given module file. "Possibly" because in the case of
    # "from A import B", we include "A.B".  Often, of course, A.B is not a
    # module -- but that doesn't matter because we only act on an "A.B"
    # dependency when A.B turns out to be a tracked module.
    #

    def analyze_dependencies(self) -> None:

        with open(self.file) as f:
            source = f.read()

        result = []

        try:
            for stmt in ast.parse(source,self.file).body:
                if isinstance(stmt,ast.Import):
                    for alias in stmt.names:
                        result.append(alias.name)
                elif isinstance(stmt,ast.ImportFrom):
                    module = _absolute_module(stmt,self.parent,self.file)
                    result.append(module)
                    for alias in stmt.names:
                        result.append(module + '.' + alias.name)
        except BaseException as ex:
            raise ModuleError(self.module.__name__,"analysis") from ex

        self.dependencies = result

_MODULE_TABLE:dict[str,_ModuleInfo] = dict()

#
# Return an absolute module reference for "from ... import ..." statements.
# _absolute_module() embeds functionality equivalent to importlib's
# resolve_name(), avoiding the need to form a "<dots><name>" string, and
# assembling the exception message we want.
#

def _absolute_module(node:ast.ImportFrom, parent:str,
                     sourcefile:str|None = None) -> str:

    module:str = node.module #type:ignore

    if (level := node.level) < 1:
        return module

    if len(parent) > 0:
        segments = parent.split('.')
        if level <= len(segments):
            return '.'.join(segments[:len(segments)-level+1]) + '.' + module

    message = "Relative import " + ('.' * level) + module

    if len(parent) == 0:
        message += " is outside any package"
    else:
        message += " would escape package " + parent

    if sourcefile is not None:
        message += " in file " + sourcefile

    raise ImportError(message)

#
# Extract import directives from Python source.  Non-import statements are
# allowed iff allow_other_statements is True (needed for %%liveimport cell
# magic.)
#

def _extract_imports(source:str, allow_other_statements:bool,
                     parent:str = '') -> list[_Import]:

    imports:list[_Import] = []

    for stmt in ast.parse(source,"<importstmts>").body:
        if isinstance(stmt,ast.Import):
            for alias in stmt.names:
                imports.append(_Import(alias.name,alias.asname,None))
        elif isinstance(stmt,ast.ImportFrom):
            modulename = _absolute_module(stmt,parent)
            bindings = []
            for alias in stmt.names:
                name = alias.name
                if name == '*':
                    # By the Python grammar, the only names entry
                    bindings = '*'
                    break
                asname = alias.asname
                if asname is None: asname = name
                bindings.append((name,asname))
            imports.append(_Import(modulename,None,bindings))
        elif not allow_other_statements:
            bad = ast.get_source_segment(source,stmt)
            raise ValueError("Expected only imports, found " +
                             bad if bad else "something else")

    return imports

#
# Ensure module is tracked, and return its projection in the given namespace.
#

def _situate(module:ModuleType, namespace:dict[str,Any]) -> _Projection:

    if (info := _MODULE_TABLE.get(module.__name__)) is None:
        info = _ModuleInfo(module)
        _MODULE_TABLE[module.__name__] = info

    if (projection := info.projections.get(id(namespace))) is None:
        projection = _Projection(namespace)
        info.projections[id(namespace)] = projection

    return projection

#
# Update _MODULE_TABLE with the provided import directives.  Observe that a
# single "from ..." import directive can add multiple entries.
#

def _register_imports(namespace:dict[str,Any], imports:list[_Import],
                      clear:bool):

    if clear:
        _MODULE_TABLE.clear()

    for imp in imports:

        module = imp.require_imported(namespace)
        projection = _situate(module, namespace)

        if (bindings := imp.bindings) == '*':
            projection.star = True
        elif bindings is not None:
            for name_asname in bindings:
                value = getattr(module,name_asname[0])
                if isinstance(value,ModuleType):
                    _situate(value, namespace)
                projection.aliases.add(name_asname) #type:ignore

#
# Dump the module table content (for debugging).
#

def _dump():
    items = sorted(_MODULE_TABLE.items())
    for name, info in items:
        print(f"Module {name} parent={info.parent}"
              f" mtime={info.mtime} file={info.file}"
              f" dependencies={info.dependencies}")
        for nsid, projection in info.projections.items():
            print(f"  Projection nsid={nsid} star={projection.star}")
            for alias in sorted(projection.aliases):
                print(f"    {alias[0]} as {alias[1]}")

#
# Check registration status (for testing).
#

def _is_registered(namespace:dict[str,Any], modulename:str,
                   name:str|None=None, asname:str|None=None) -> bool:
    if asname is None: asname = name
    info = _MODULE_TABLE.get(modulename)
    if info is None: return False
    projection = info.projections.get(id(namespace))
    if projection is None: return False
    if name is None: return True
    if name == '*': return projection.star
    return (name,asname) in projection.aliases

#
# ============================ PUBLIC API ============================
#

def register(namespace:dict[str,Any], importstmts:str,
             *, package:str='', clear:bool=False) -> None:
    """
    Register import statements for syncing.

    :param namespace: The import statement target, usually the caller's value
        of ``globals()``.

    :param importstmts: Python code consisting of zero or more import
        statements and nothing else.  The application should have already
        executed these or equivalent imports.

    :param package: Context for interpreting relative import statements.  When
        given, `package` is usually the caller's immediate parent package,
        accessible as ``__spec__.parent`` if it exists.  If no package is
        specified, relative imports are not allowed.  Relative imports are only
        useful when using LiveImport outside a notebook, since notebook code is
        not in a package.

    :param clear: If and only if true, discard all prior registrations
        targeting `namespace` before registering the given import statements.

    All modules referenced by the import statements must already be loaded and
    have associated source files, and all symbols mentioned must already exist.
    If an associated source file is later modified, then a sync will reload the
    corresponding module and update symbols from the module.  Example:

      .. code:: python

        liveimport.register(globals(),\"\"\"
        import printmath as pm
        from simulator import stop as halt
        from verify import *
        \"\"\")

    If ``verify.py`` is modified, a sync will reload ``verify`` and create or
    update bindings in `namespace` for the same symbols that executing ``from
    verify import *`` would.  Similarly, if ``simulator.py`` is modified, a
    sync will reload the module and create or update a binding for ``halt``
    with the value of ``stop`` in ``simulator``.

    Using multiline strings to specify multiple import statements, each on its
    own line as shown above is convenient and easy to read, but in any case
    statements must have identical indentation.

      .. code:: python

        # Raises a SyntaxError because "import green" has leading whitespace
        # while "import red" does not.
        liveimport.register(globals(),\"\"\"import red
            import green\"\"\")

        # This works.
        liveimport.register(globals(),\"\"\"import red
        import green\"\"\")

        # And so does this.
        liveimport.register(globals(),\"\"\"
            import red
            import green\"\"\")

    Since the statements given are Python code, you can also use semicolons to
    separate statements.

      .. code:: python

        liveimport.register(globals(),"import red; import green")


    Registration is idempotent, multiple registrations are allowed, and
    overlapping registrations such as

      .. code:: python

        liveimport.register(globals(),"from symcode import x, hermite_poly")
        liveimport.register(globals(),"from sycmode import x, lagrange_poly")
        liveimport.register(globals(),"from sycmode import lagrange_poly as lp")
        liveimport.register(globals(),"from symcode import *")
        liveimport.register(globals(),"import symcode")

    are perfectly fine.

    :raises SyntaxError: `importstmts` is not syntactically valid.

    :raises ImportError: `importstmts` includes an improper relative import

    :raises ValueError: `importstmts` includes non-import statements, a
        referenced module is not loaded or has no associated source file, or an
        included symbol does not already exist.

    :raises ModuleError: The content of a module referenced by an import
        statement is erroneous.
    """
    imports = _extract_imports(textwrap.dedent(importstmts),False,package)
    _register_imports(namespace,imports,clear)

#
# Return an easily readable approximation to elapsed time t.
#

def _nice_time_ago(t:float) -> str:
    return (
        "in the future (!)"                      if t < 0 else
        str(int(t * 1000)) + " milliseconds ago" if t < 2 else
        str(int(t))        + " seconds ago"      if t < 120 else
        str(int(t/60))     + " minutes ago"      if t < 7200 else
        str(int(t/3600))   + " hours ago"        if t < 172800 else
        str(int(t/86400))  + " days ago")

#
# Return a conventionally written English list phrase.
#

def _nice_list(strs:list[str]) -> str:
    assert len(strs) > 0
    if len(strs) == 1: return strs[0]
    if len(strs) == 2: return strs[0] + " and " + strs[1]
    return ", ".join(strs[:-1]) + ", and " + strs[-1]


class ReloadEvent:
    """
    Describes a successful reload.  Attributes:

    .. attribute:: module
        :type: str

        The name of the module reloaded.

    .. attribute:: reason
        :type: str

        The reason the module was reloaded, either ``"modified"`` or
        ``"dependent"``.

    .. attribute:: mtime
        :type: float

        The modification time of the module source file last seen by
        LiveImport.  If reason is ``"modified"``, this time changed since the
        module was registered or last reloaded.

    .. attribute:: after
        :type: list[str]

        The modules on which `module` depends which reloaded prior to `module`
        as part of the same sync.  `after` is never empty if `reason` is
        ``"dependent"``.

    The string representation of a `ReloadEvent`:class: is an English-language
    description similar to

        ``Reloaded printmath modified 18 seconds ago``

    or

        ``Reloaded simulator because printmath reloaded``
    """
    __slots__ = "module", "reason", "mtime", "after"
    def __init__(self, module:str, reason:str, mtime:float, after:list[str]):
        self.module = module
        self.reason = reason
        self.mtime  = mtime
        self.after  = after

    def __str__(self)->str:
        return (
            "Reloaded " + self.module +
            (" modified " + _nice_time_ago(time.time() - self.mtime)
             if self.reason == "modified" else
             f" because {_nice_list(self.after)} reloaded"))


class ModuleError(Exception):
    """
    LiveImport has determined there is an issue with the content of a module.

    .. attribute:: module
        :type: str

        The name of the module.

    .. attribute:: phase
        :type: str

        Phase of processing during which LiveImport detected the erroneous
        condition, currently either ``"analysis"`` or ``"reload"``.

    .. attribute:: __cause__
        :type: BaseException

        The issue LiveImport encountered.  This could be a source error, such
        as a `SyntaxError`:class:, or an exception raised while the module is
        executing during a reload.
    """
    def __init__(self, module:str, phase:str):
        self.module = module
        self.phase  = phase

    def __str__(self) -> str:
        return (f"{self.phase.capitalize()} of {self.module} failed: " +
                str(self.__cause__))

#
# Generate (<namespace>,<name>,<asname>) triples for reloaded modules.
#

def _assignments(info:_ModuleInfo):
    module = info.module
    for projection in info.projections.values():
        aliases = projection.aliases
        if projection.star:
            if hasattr(module,'__all__'):
                names = module.__all__
            else:
                names = (name for name in dir(module)
                         if not name.startswith('_'))
            aliases = set(aliases)
            for name in names:
                aliases.add((name,name))
        namespace = projection.namespace
        for name, asname in aliases:
            yield namespace, name, asname


def sync(*, observer:Callable[[ReloadEvent],None]|None=None) -> None:
    """
    Bring all registered imports up to date.  This includes reloading
    out-of-date tracked modules and rebinding imported symbols.  A tracked
    module is out-of-date if either the module has changed since registration
    or last sync, or the module depends on an out-of-date tracked module.

    "Depends on" is a strict partial order LiveImport computes between tracked
    modules based on the top level import statements in those modules.  In most
    cases, those imports naturally define a strict partial order.  If they do
    not (meaning there is an import cycle), LiveImport ignores the imports by
    more recently tracked modules that prevent it.

    `sync()`:func: guarantees that reload order is consistent with the "depends
    on" partial order, so if A depends on B, then B will reload before A.

    `sync()`:func: uses source file modification times to determine if a module
    has changed — any change triggers a reload, even becoming older than the
    currently loaded version.  (So reverted modules reload.)

    :param observer: If given, `sync()`:func: calls `observer` with a
      `ReloadEvent`:class: describing each successful reload.

    :raises ModuleError: The content of a tracked module is erronous or raised
        an exception when executed during a reload.

    .. note::
        Unless automatic syncing is disabled, calling `sync()`:func: in a
        notebook should not be necessary.
    """
    #
    # Determine if any modules have been updated, preparing to schedule
    # topologically by clearing marks.  We refresh dependencies of modified
    # modules to make the dependency information current for the topological
    # sort.  We defer adjusting info.mtime so that reload() exceptions will
    # leave modules in an out-of-date state.
    #

    any_updates = False

    for info in _MODULE_TABLE.values():
        info.mark = 0
        current_mtime = getmtime(info.file)
        if current_mtime != info.mtime:
            info.next_mtime = current_mtime
            info.analyze_dependencies()
            any_updates = True

    if not any_updates:
        return

    #
    # At least one module needs to be reloaded.  Schedule reloads ordered
    # topologically by module dependency, including reloads of modules that
    # haven't changed but depend on modules that will reload.
    #
    # Mark intepretation:
    #
    #   0 - Unvisited
    #   1 - On current depth first traversal path
    #   2 - Visit complete; will not reload
    #   3 - Visit complete; will reload
    #

    schedule:list[tuple[_ModuleInfo,list[str]]] = []

    def visit(info:_ModuleInfo):
        info.mark = 1
        dependent_reload = []
        for othername in info.dependencies:
            if (otherinfo := _MODULE_TABLE.get(othername)) is not None:
                if otherinfo.mark == 1: continue
                if otherinfo.mark == 0: visit(otherinfo)
                if otherinfo.mark == 3: dependent_reload.append(othername)
        if dependent_reload or info.next_mtime != info.mtime:
            info.mark = 3
            schedule.append((info,dependent_reload))
        else:
            info.mark = 2

    for info in _MODULE_TABLE.values():
        if info.mark == 0:
            visit(info)

    #
    # Execute the reloads.  Because we defer updating info.mtime, if there is a
    # reload error, sync() will try again after the user fixes the issue.
    #

    for info, dependent_reload in schedule:
        module = info.module
        try:
            reload(module)
        except BaseException as ex:
            raise ModuleError(info.module.__name__,"reload") from ex
        for globals, modulevar, globalvar in _assignments(info):
            if not hasattr(module,modulevar):
                #
                # This is not possible in normal use since reload() never
                # deletes symbols from loaded modules. Likely it can only
                # happen if the application explcitly deletes symbols from the
                # module dictionary.  Because it is so obscure, we judge it
                # more confusing to document than not.
                #
                raise RuntimeError(
                    f"Module symbol {modulevar} referenced in registered"
                    f" import from {module.__name__} has disappeared")
            else:
                globals[globalvar] = getattr(module,modulevar)
        if observer is not None:
            observer(ReloadEvent(
                info.module.__name__,
                "modified" if info.next_mtime != info.mtime else "dependent",
                info.next_mtime, list(dependent_reload)))
        info.mtime = info.next_mtime


def auto_sync(*, enabled:bool|None=None, 
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
    if enabled is not None: _HANDLER.autosync_enabled = enabled
    if grace   is not None: _HANDLER.autosync_grace   = grace
    if report  is not None: _HANDLER.autosync_report  = report


def hidden_cell_magic(*,enabled:bool|None=None) -> None:
    """
    Configure hidden cell magic.

    :param enabled: Notebook cells that begin with ``#_%%liveimport`` run as if
        they began with ``%%livemagic`` if and only if `enabled` is true.  This
        makes LiveImport cell magic transparent to IDEs like Visual Studio
        Code, yet still function as desired.  Hidden cell magic is disabled by
        default.
    """
    if _IPYTHON_SHELL is None: return
    if enabled is None: return
    cleanup = _IPYTHON_SHELL.input_transformers_cleanup
    for i, transformer in enumerate(cleanup):
        if getattr(transformer,'__module__',None) == 'liveimport':
            del cleanup[i]
            break
    if enabled:
        cleanup.append(_unhide_cell_magic)

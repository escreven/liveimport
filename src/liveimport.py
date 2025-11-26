"""Automatically reload modified Python modules in notebooks and scripts.

See `the user guide
<https://liveimport.readthedocs.io/en/latest/userguide.html>`_.
"""
__version__ = "1.2.0.dev1"

from importlib.machinery import ModuleSpec
import math
from pathlib import Path
import re
import sys
import ast
import textwrap
import time
import os
from types import ModuleType
from os.path import getmtime
from importlib import reload
from typing import Any, Callable, Iterable, Literal, NoReturn, TextIO
import IPython
from IPython.display import display, Markdown
from IPython.core.magic import Magics, magics_class, cell_magic
from IPython.core.error import UsageError
from IPython.core.inputtransformer2 import TransformerManager

__all__ = ("register", "sync", "auto_sync", "hidden_cell_magic",
           "ReloadEvent", "ModuleError")

#
# ========================= NOTEBOOK INTEGRATION =========================
#

_IPYTHON_SHELL = IPython.get_ipython()  #type:ignore

_transform_cell = TransformerManager().transform_cell

#
# Implement %%liveimport cell magic as described in the module docstring.
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
        imports = _extract_imports(text,True)
        if (shell := self.shell) is None:
            raise RuntimeError("No IPython shell for %%liveimport magic")
        if shell.run_cell(cell).error_in_exec is None:
            _register_imports(shell.user_ns,imports,clear)

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
                if events and self.autosync_report:
                    _display_reload_events(events)
                if isinstance(sync_ex,ModuleError):
                    sync_ex = sync_ex.__cause__
                if sync_ex is not None:
                    raise sync_ex.with_traceback(sync_ex.__traceback__)

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
        _IPYTHON_SHELL.register_magics(_LiveImportMagics)
        _HANDLER = _LiveImportHandler()
        _IPYTHON_SHELL.events.register('pre_run_cell',_HANDLER.pre_run_cell)
        _IPYTHON_SHELL.events.register('post_run_cell',_HANDLER.post_run_cell)
        _IPYTHON_SHELL.input_transformers_cleanup.append(_unhide_cell_magic)

#
# =========================== IMPORT MANAGEMENT ===========================
#

#
# The workspace is a possibly empty list of directory paths.  We use Path
# objects so we can use is_relative_to(), and we normalize using absolute()
# instead of resolve() because we don't want to follow symbolic links -- most
# likely what a user expects.
#

if "_WORKSPACE" not in globals():
    _WORKSPACE:list[Path] = [ Path(".").absolute() ]

#
# Return true iff the named file is in the workspace.
#

def _in_workspace(file:str) -> bool:

    filepath = Path(file).absolute()

    for dirpath in _WORKSPACE:
        if filepath.is_relative_to(dirpath):
            return True

    return False

#
# _Bindings is None for "import A" imports, and "*" or a (<name>,<nameas>) pair
# list for "from A import ..." statements.
#

_Bindings = None | Literal["*"] | list[tuple[str,str]]

#
# Each registered import statement is transformed into one or more _Import
# directives.  Field modulename is always an absolute module name.  Field
# modulasname is the name in the target namespace referencing the loaded
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
            self.missing_import(f"No name {modulesym} in namespace")
        if type(bindings) is list:
            for name, asname in bindings:
                if not hasattr(module,name):
                    self.missing_import(f"No name {name} in {modulename}")
                if asname not in namespace:
                    self.missing_import(f"No name {asname} in namespace")
        return module

#
# A _Projection is mapping of module provided names into a namespace.  There is
# a projection for every tracked module with imports registered in a namespace,
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
# Observe that a module is directly imported iff projections is non-empty.
# sync() uses that fact.
#
# We never delete _ModuleInfo objects from _MODULE_TABLE.  That means we can
# maintain what we know about module source file modification times if the
# module becomes relevant again.  We do delete projections when registrations
# are cleared.
#

class _ModuleInfo:
    __slots__ = ("module", "file", "parent",
                 "mtime", "projections", "dependencies",
                 "next_mtime", "mark")

    projections : dict[int,_Projection]

    def __init__(self, module:ModuleType):

        spec = module.__spec__
        if spec is None:
            raise ValueError(f"Module {module.__name__} has no spec")

        if not _has_source_file(spec):
            raise ValueError(f"Module {module.__name__} has no source file")

        assert (file   := spec.origin) is not None
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
    # Assign to self.dependencies the names of modules possibly referenced by
    # top level import statements of the given module file. "Possibly" because
    # in the case of "from A import B", we include "A.B".  Often, of course,
    # A.B is not a module -- but that doesn't matter because we only act on an
    # "A.B" dependency when A.B turns out to be a tracked module.  Returning
    # possibly instead of definitely referenced module names is an
    # implementation necessity: it enables the depedency graph to evolve
    # naturally as imports are registered and cleared.
    #

    def analyze_dependencies(self) -> None:

        with open(self.file) as f:
            source = f.read()

        result:list[str] = []

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
# Return true iff the given module spec has a source file.
#

def _has_source_file(spec:ModuleSpec) -> bool:
    if not spec.has_location: return False
    origin = spec.origin
    assert origin is not None
    if not origin.endswith(".py"): return False
    return os.path.exists(origin)

#
# Return the named file's modification time if it exists, otherwise return
# None.
#

def _mtime_if_exists(file:str) -> float|None:
    try:
        return getmtime(file)
    except Exception as ex:
        if not os.path.exists(file):
            return None
        raise

#
# Return an absolute module reference for "from ... import ..." statements.
# _absolute_module() embeds functionality equivalent to importlib's
# resolve_name(), avoiding the need to form a "<dots><name>" string, and
# assembling the exception message we want.
#

def _absolute_module(node:ast.ImportFrom, parent:str,
                     sourcefile:str|None = None) -> str:

    module:str|None = node.module

    if (level := node.level) < 1:
        assert module is not None
        return module

    if len(parent) > 0:
        segments = parent.split('.')
        if level <= len(segments):
            result = '.'.join(segments[:len(segments)-level+1])
            if module is not None:
                result += '.' + module
            return result

    message = "Relative import " + ('.' * level)
    if module is not None:
        message += module

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
        nsid = id(namespace)
        for info in _MODULE_TABLE.values():
            if nsid in info.projections:
                del info.projections[nsid]

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

    _track_new_indirects()

#
# Dump the module table content (for debugging).
#

def _dump(file:TextIO|None=None):
    items = sorted(_MODULE_TABLE.items())
    for name, info in items:
        print(f"Module {name} parent={info.parent}"
              f" mtime={info.mtime} file={info.file}"
              f" dependencies={info.dependencies}",file=file)
        for nsid, projection in info.projections.items():
            print(f"  Projection nsid={nsid} star={projection.star}",file=file)
            for alias in sorted(projection.aliases):
                print(f"    {alias[0]} as {alias[1]}",file=file)

#
# Check registration and tracking status (for testing).
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

def _in_module_table(modulename:str):
    return modulename in _MODULE_TABLE

#
# Clear the module table (for testing).
#

def _clear_all_module_info():
    _MODULE_TABLE.clear()

#
# Make sure all tracked module dependencies are themselves tracked if they have
# source files in the workspace.  _track_new_indirects() should be called after
# imports are registered, and after modules are reloaded.
#

def _track_new_indirects():

    #
    # We perform a breadth-first traveral of the dependency graph.  The initial
    # cohort is all currently tracked modules.  Subsequent cohorts are modules
    # tracked because of emergent dependencies in the prior cohort.  Note that
    # added is implicitly a set, since a named module isn't added to
    # _MODULE_TABLE more than once.
    #

    cohort:list[_ModuleInfo] = list(_MODULE_TABLE.values())

    while True:
        added:list[_ModuleInfo] = []
        for info in cohort:
            for modulename in info.dependencies:
                #
                # A dependee should be added if it isn't already tracked, is
                # loaded, has a spec, and has a source file that is in the
                # workspace.
                #
                if modulename in _MODULE_TABLE: continue
                if (module := sys.modules.get(modulename)) is None: continue
                if (spec := module.__spec__) is None: continue
                if not _has_source_file(spec): continue
                assert (file := spec.origin) is not None
                if not _in_workspace(file): continue
                #
                # Start tracking the dependee.
                #
                newinfo = _ModuleInfo(module)
                assert modulename == module.__name__
                _MODULE_TABLE[modulename] = newinfo
                added.append(newinfo)
        if not added: break
        cohort = added

    return added

#
# ============================ PUBLIC API ============================
#

def register(namespace:dict[str,Any], importstmts:str,
             *, package:str='', clear:bool=False) -> None:
    """
    Register import statements for syncing.

    All modules referenced by the import statements must already be loaded and
    have associated source files, and all names mentioned must already exist in
    `namespace`.  If an associated source file is later modified, then a sync
    will reload the corresponding module and update names from the module.

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

    :raises SyntaxError: `importstmts` is not syntactically valid.

    :raises ImportError: `importstmts` includes an improper relative import.

    :raises ValueError: `importstmts` includes non-import statements, a
        referenced module is not loaded or has no associated source file, or an
        included name does not already exist.

    :raises ModuleError: The content of a module referenced by an import
        statement is erroneous.

    Example:

      .. code:: python

        liveimport.register(globals(),\"\"\"
        import printmath as pm
        from simulator import stop as halt
        from verify import *
        \"\"\")

    If ``verify.py`` is modified, a sync will reload ``verify`` and create or
    update bindings in `namespace` for the same names that executing ``from
    verify import *`` would.  Similarly, if ``simulator.py`` is modified, a
    sync will reload the module and create or update a binding for ``halt``
    with the value of ``stop`` in ``simulator``.

    Using multiline strings to specify multiple import statements, each on its
    own line as shown above is convenient and easy to read, but statements must
    have identical indentation.

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
        liveimport.register(globals(),"from symcode import x, lagrange_poly")
        liveimport.register(globals(),"from symcode import lagrange_poly as lp")
        liveimport.register(globals(),"from symcode import *")
        liveimport.register(globals(),"import symcode")

    are perfectly fine.
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

        The reason LiveImport reloaded `module`, either ``"modified"`` or
        ``"dependent"``.

    .. attribute:: mtime
        :type: float

        The modification time of the module source file last seen by
        LiveImport.  If reason is ``"modified"``, this time changed since
        LiveImport began tracking or last reloaded `module`.

    .. attribute:: after
        :type: list[str]

        Modules on which `module` depends which LiveImport has already reloaded
        as part of the same sync.  If `reason` is ``"dependent"``, LiveImport
        reloaded `module` solely because it reloaded these modules.

    The string representation of a :class:`ReloadEvent` is an English-language
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
        as a :class:`SyntaxError`, or an exception raised while the module is
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
    out-of-date tracked modules and rebinding imported names.  A tracked
    module is out-of-date if either the module has changed since registration
    or last sync, or the module depends on an out-of-date tracked module.

    "Depends on" is a strict partial order LiveImport computes between tracked
    modules based on the top level import statements in those modules.  In most
    cases, those imports naturally define a strict partial order.  If they do
    not (meaning there is an import cycle), LiveImport ignores the imports by
    more recently tracked modules that prevent it.

    :func:`sync()` guarantees that reload order is consistent with the "depends
    on" partial order, so if A depends on B, then B will reload before A.

    :func:`sync()` uses source file modification times to determine if a module
    has changed.  Any change triggers a reload, including being reset to an
    older time.  (So reverted modules reload.)

    :param observer: If given, :func:`sync()` calls `observer` with a
      :class:`ReloadEvent` describing each successful reload.

    :raises ModuleError: The content of a tracked module is erronous or raised
        an exception when executed during a reload.

    .. note::
        Unless automatic syncing is disabled, calling :func:`sync()` in a
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
        current_mtime = _mtime_if_exists(info.file)
        if current_mtime is None:
            #
            # The module source file is missing.  Pre-mark the module as "Visit
            # complete; will not reload".  (See below).  That prevents the
            # topological sort from visiting the module, and ensures the module
            # will not be added to the reload schedule.
            #
            info.mark = 2
        elif current_mtime != info.mtime:
            info.next_mtime = current_mtime
            info.analyze_dependencies()
            any_updates = True

    if not any_updates:
        return

    #
    # At least one module is out of date.  Schedule reloads ordered
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
    # The roots of the depth first search are the directly imported modules.
    # That way we don't reload indirect modules if they no longer have
    # dependants.
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
        if info.mark == 0 and info.projections:
            visit(info)

    if not schedule:
        return

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
                # deletes names from loaded modules. Likely it can only
                # happen if the application explicitly deletes names from the
                # module dictionary.  Because it is so obscure, we judge it
                # more confusing to document than not.
                #
                raise RuntimeError(
                    f"Name {modulevar} referenced in registered"
                    f" import from {module.__name__} has disappeared")
            else:
                globals[globalvar] = getattr(module,modulevar)
        if observer is not None:
            observer(ReloadEvent(
                info.module.__name__,
                "modified" if info.next_mtime != info.mtime else "dependent",
                info.next_mtime, list(dependent_reload)))
        info.mtime = info.next_mtime

    #
    # We check for new indirects after reloads since we need new indirects to
    # be already loaded.
    #

    _track_new_indirects()


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
        if getattr(transformer,'__module__',None) == 'liveimport':
            del cleanup[i]
            break
    if enabled:
        cleanup.append(_unhide_cell_magic)


def workspace(*directories:str) -> None:
    """
    Define the workspace, a set of directories.

    LiveImport tracks modules that are either imported by a registered import
    statement, or are imported by a tracked module and have a source file in
    the workspace.  A source file is in the workspace if it's under a workspace
    directory.

    The default workspace is the current working directory when the LiveImport
    module is imported.  Thus, when LiveImport is used in a notebook, the
    workspace is the directory containing the notebook.

    :param directories: Zero or more path strings.  Each path must identify an
        existing directory.

    :raises ValueError: One of the specified directories does not exist or
        exists but is not a directory.

    Example: After calling

      .. code:: python

        liveimport.workspace("src", "/opt/notebook-utils")

    the workspace is the directory ``src`` in the current working directory and
    the directory ``/opt/notebook-utils``.

    If you call

      .. code:: python

        liveimport.included_directories()

    the workspace is empty, so only modules referenced by registered imports
    will be tracked.

    .. note::
        Changing the workspace does not alter tracking decisions
        LiveImport has already made.  It only affects future decisions.  It's
        best to specify a non-default workspace before registering any imports.
    """
    global _WORKSPACE

    workspace:list[Path] = []

    for dir in directories:

        path = Path(dir).absolute()

        if not path.exists():
            raise ValueError(f"Path {path} does not exist")

        if not path.is_dir():
            raise ValueError(f"Path {path} is not a directory")

        workspace.append(path)

    _WORKSPACE = workspace

    _track_new_indirects()

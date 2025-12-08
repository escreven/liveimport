from __future__ import annotations
import math
import sys
import ast
import time
import textwrap
from os.path import exists, getmtime
from importlib import reload
from importlib.machinery import ModuleSpec
from types import ModuleType
from typing import Any, Callable, NoReturn

from ._workspace import _in_workspace


##############################################################################
#                                 UTILITY
##############################################################################

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

#
# Return a file's modification time if it exists, otherwise return None.
#

def _mtime_if_exists(file:str|None) -> float|None:
    if file is None:
        return None
    try:
        return getmtime(file)
    except Exception as ex:
        if not exists(file):
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
# Return true iff the given module spec has a source file.
#

def _has_source_file(spec:ModuleSpec, must_exist=False) -> bool:
    if not spec.has_location: return False
    origin = spec.origin
    assert origin is not None
    if not origin.endswith(".py"): return False
    return not must_exist or exists(origin)

#
# Rebind asname in namespace to a named value in module, raising a descriptive
# error if name is missing from module.
#

def _assign(module:ModuleType, name:str, asname:str,
            namespace:dict[str,Any]) -> None:

    if not hasattr(module,name):
        #
        # This is not possible in normal use since reload() never
        # deletes names from loaded modules. Likely it can only
        # happen if the application explicitly deletes names from the
        # module dictionary.  Because it is so obscure, we judge it
        # more confusing to document than not.
        #
        raise RuntimeError(
            f"Name {name} referenced in registered"
            f" import from {module.__name__} has disappeared")
    else:
        namespace[asname] = getattr(module,name)


##############################################################################
#                                 MODEL
##############################################################################

#
# We record a name rebinding journal for target namespaces as import statements
# are registered.  The journal has three kinds of rebind records, all
# implemented as triples:
#
#     (modulename, None, asname)  Rebind module object to asname
#     (modulename, name, asname)  Rebind module named value to asname
#     (modulename, '*',  None)    Rebind module public named values to same
#
# A journal is a list of rebind records.  We compact journals after extending
# them so they don't grow without bound.
#

_Rebind = tuple[str, str|None, str|None]
_Journal = list[_Rebind]

#
# Return string representation of a rebind.
#

def _rebind_str(rebind:_Rebind) -> str:
    modulename, name, asname = rebind
    return ("Rebind " + modulename +
            ("." + name if name is not None else "") +
            " --> " +
            (asname if asname is not None else "_"))

#
# Return an equivalent journal that has no superfluous entries according to
# these lemmas: only the last rebind of an asname can be detected, and only the
# last '*' rebind for a module can be detected.
#

def _journal_compact(journal:_Journal) -> _Journal:

    star_set   = set()
    asname_set = set()
    result     = []

    for i in range(len(journal)-1,-1,-1):

        rebind = journal[i]
        modulename, name, asname = rebind

        if asname is not None:
            if asname not in asname_set:
                asname_set.add(asname)
                result.append(rebind)
        else:
            assert name == '*'
            if modulename not in star_set:
                star_set.add(modulename)
                result.append(rebind)

    result.reverse()
    return result

#
# Apply the journal to a namespace.
#

def _journal_apply(journal:_Journal, namespace:dict[str,Any]):
    modules = sys.modules
    for modulename, name, asname in journal:
        module = modules[modulename]
        if asname is not None:
            if name is not None:
                _assign(module,name,asname,namespace)
            else:
                namespace[asname] = module
        else:
            star_names = (module.__all__ if hasattr(module,'__all__') else
                          (name for name in dir(module)
                           if not name.startswith('_')))
            for name in star_names:
                _assign(module,name,name,namespace)

#
# Information LiveImport tracks about namespaces in _NAMESPACE_TABLE keyed by
# id.  A namespace as an entry in _NAMESPACE_TABLE iff there are registered
# imports for it.  Each has a compacted rebind journal equivalent to executing
# those registered imports in the order they are registered.
#

class _NamespaceInfo:
    __slots__ = "namespace", "journal"

    namespace:dict[str,Any]
    journal:_Journal

    def __init__(self,namespace:dict[str,Any]):
        self.namespace = namespace
        self.journal = []

_NAMESPACE_TABLE:dict[int,_NamespaceInfo] = dict()

#
# Information LiveImport tracks about a module in _MODULE_TABLE.  We never
# delete _ModuleInfo objects from _MODULE_TABLE, except in testing.  That means
# we can maintain what we know about module source file modification times if
# registrations are cleared.
#
# A module is directly imported iff it is attached to a namespace.
#

class _ModuleInfo:
    __slots__ = ("module", "file", "parent",
                 "mtime", "attachedto", "dependencies",
                 "next_mtime", "mark")

    module       : ModuleType  # loaded module instance
    file         : str|None    # source file name or None if no file
    parent       : str         # parent package or ''
    mtime        : float       # last known modification time
    attachedto   : set[int]    # imported into these namespaces
    next_mtime   : float       # see sync()
    mark         : int         # see sync()
    dependencies : list[str]   # known to depend on these named modules

    def __init__(self, module:ModuleType):

        spec = module.__spec__
        if spec is None:
            raise ValueError(f"Module {module.__name__} has no spec")

        self.module       = module
        self.parent       = '' if spec.parent is None else spec.parent
        self.attachedto   = set()
        self.mark         = 0
        self.mtime        = -math.inf
        self.next_mtime   = -math.inf
        self.dependencies = []

        if _has_source_file(spec, must_exist=False):
            assert (file := spec.origin) is not None
            self.file = file
            if (mtime := _mtime_if_exists(file)) is not None:
                self.mtime      = mtime
                self.next_mtime = mtime
                self.analyze_dependencies()
        else:
            self.file = None

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

        assert self.file

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
# Make sure all tracked module dependencies are themselves tracked if they have
# source files in the workspace.  _track_new_indirects() should be called after
# imports are registered, and after modules are reloaded.
#

def _track_new_indirects() -> None:

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

#
# Ensure module is tracked.
#

def _track(module:ModuleType) -> _ModuleInfo:
    modulename = module.__name__
    if (info := _MODULE_TABLE.get(modulename)) is None:
        info = _ModuleInfo(module)
        _MODULE_TABLE[modulename] = info
    return info

#
# Register a piece of an import statement.  _register_piece() also verifies
# there is evidence that an encompassing import statement was actually
# executed.
#
# Parameters:
#
#     namespace    - target namespace
#     journal      - extend this journal
#     trackmodname - track this named module
#     valuemodname - rebind value of or from this named module
#     name         - assign from this attribute (None means module itself)
#     asname       - assign to this attribute; none for '*' rebinds
#
# _register_piece() returns the tracked module info.
#

def _register_piece(namespace:dict[str,Any], journal:_Journal,
                    trackmodname:str, valuemodname:str,
                    name:str|None, asname:str|None) -> _ModuleInfo:

    def invalid(reason:str) -> NoReturn:
        if name is None:
            stmt = "import " + trackmodname
            assert asname is not None
            if asname != valuemodname:
                stmt += " as " + asname
        else:
            stmt = "from " + trackmodname + " import " + name
            if asname is not None and asname != name:
                stmt += " as " + asname
        raise ValueError(f"{reason}; missing {stmt}?")

    trackmod = sys.modules.get(trackmodname)
    if trackmod is None: invalid(f"Module {trackmodname} not loaded")

    valuemod = sys.modules.get(valuemodname)
    if valuemod is None: invalid(f"Module {valuemodname} not loaded")

    if name is not None and name != '*' and not hasattr(valuemod, name):
        invalid(f"No name {name} in {valuemodname}")

    if asname is not None and not asname in namespace:
        invalid(f"No name {asname} in namespace")

    journal.append((valuemodname,name,asname))
    return _track(trackmod)


##############################################################################
#                               PUBLIC API
##############################################################################

def register(namespace:dict[str,Any], importstmts:str,
             *, package:str='', clear:bool=False,
             allow_other_statements:bool=False) -> None:
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
    #
    # Extract the import directives from Python source, construct an equivalent
    # journal, and start tracking referenced modules.  Non-import statements
    # are allowed iff allow_other_statements is True (needed for %%liveimport
    # cell magic.)  We require import statements supporting the journal to have
    # been executed (as far as we can tell.)
    #
    # See the Python language reference section on import statements.
    #

    journal:_Journal = []
    attachments:list[_ModuleInfo] = []

    source = textwrap.dedent(importstmts)
    for stmt in ast.parse(source,"<importstmts>").body:
        if isinstance(stmt,ast.Import):
            #
            # Case 1 import a.b.c -->
            #     track a.b.c
            #     rebind module(a) to a
            #
            # Case 2: import a.b.c as x -->
            #     track a.b.c
            #     rebind module(a.b.c) to x
            #
            for alias in stmt.names:
                modulename = alias.name
                asname = alias.asname
                if asname is None:
                    topname = modulename.split('.',1)[0]
                    info = _register_piece(namespace,journal,modulename,
                                           topname,None,topname)
                else:
                    info = _register_piece(namespace,journal,modulename,
                                           modulename,None,asname)
                attachments.append(info)

        elif isinstance(stmt,ast.ImportFrom):
            #
            # Case 3: from [.*] a.b.c import * -->
            #     track absolute(.* a.b.c)
            #     rebind absolute(.* a.b.c).* as _
            #
            # Case 4: from .* a.b.c import x -->
            #     track absolute(.* a.b.c)
            #     rebind absolute(.* a.b.c).x as x
            #
            # Case 5: from [.*] a.b.c import x as y -->
            #     track absolute(.* a.b.c)
            #     rebind absolute(.* a.b.c).x as y
            #
            # PLUS for cases 4 and 5, if it turns out absolute(.* a.b.c).x is a
            # module, track(absolute(.* a.b.c).x)
            #
            modulename = _absolute_module(stmt,package)
            for alias in stmt.names:
                name = alias.name
                asname = alias.asname
                if name == '*':
                    info = _register_piece(namespace,journal,modulename,
                                           modulename,'*',None)
                else:
                    if asname is None: asname = name
                    info = _register_piece(namespace,journal,modulename,
                                           modulename,name,asname)
                    value = getattr(info.module,name)
                    if isinstance(value,ModuleType):
                        attachments.append(_track(value))
                attachments.append(info)
        elif not allow_other_statements:
            bad = ast.get_source_segment(source,stmt)
            raise ValueError("Expected only imports, found " +
                             bad if bad else "something else")

    #
    # The logic below clears existing registrations if requested, returns if
    # the journal is empty, and makes sure there is a _NamespaceInfo instance
    # for the target namespace if we are continuing on further down.
    #

    nsid   = id(namespace)
    nsinfo = _NAMESPACE_TABLE.get(nsid)

    if clear and nsinfo is not None:
        for info in _MODULE_TABLE.values():
            if nsid in info.attachedto:
                info.attachedto.remove(nsid)
        nsinfo.journal = []

    if not journal:
        if clear and nsinfo is not None:
            del _NAMESPACE_TABLE[nsid]
        return

    if nsinfo is None:
        nsinfo = _NamespaceInfo(namespace)
        _NAMESPACE_TABLE[nsid] = nsinfo

    #
    # Attach the referenced modules to the namespace and append the new journal
    # segment to the namespace's existing journal.
    #

    for info in attachments:
        info.attachedto.add(nsid)

    (combined := nsinfo.journal).extend(journal)
    nsinfo.journal = _journal_compact(combined)

    #
    # Newly tracked modules may have additional indirect imports.
    #

    _track_new_indirects()


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
        if info.mark == 0 and info.attachedto:
            visit(info)

    if not schedule:
        return

    #
    # Execute the reloads.  Because we defer updating info.mtime, if there is a
    # reload error, sync() will try again after the user fixes the issue.  We
    # break the loop and re-raise further down on error since some modules may
    # have successfully reloaded, so we need to apply the journal to maintain
    # consistency.
    #

    reload_error = None

    for info, dependent_reload in schedule:
        module = info.module
        try:
            reload(module)
        except BaseException as ex:
            reload_error = ex
            break
        if observer is not None:
            observer(ReloadEvent(
                info.module.__name__,
                "modified" if info.next_mtime != info.mtime else "dependent",
                info.next_mtime, list(dependent_reload)))
        info.mtime = info.next_mtime

    #
    # Apply rebind journals related to reloaded modules.
    #

    affected = set()
    for module, _ in schedule:
        affected |= module.attachedto

    for nsid in affected:
        nsinfo = _NAMESPACE_TABLE[nsid]
        _journal_apply(nsinfo.journal,nsinfo.namespace)

    if reload_error is not None:
        raise ModuleError(info.module.__name__,"reload") from reload_error

    #
    # We check for new indirects after reloads since we need new indirects to
    # be already loaded.
    #

    _track_new_indirects()


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
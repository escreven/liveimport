from __future__ import annotations
from abc import ABC, abstractmethod
import math
import sys
import ast
import time
import textwrap
from os.path import exists, getmtime
from importlib import import_module, reload
from importlib.machinery import ModuleSpec
from types import ModuleType
from typing import Any, Callable
from ._workspace import _in_workspace

_sys_lazy_modules:set[str] = getattr(sys,"lazy_modules",set())


##############################################################################
#                                 UTILITY
##############################################################################

#
# Return True iff the named module is lazily imported.
#

def _is_lazy(modulename:str):
    return modulename not in sys.modules and modulename in _sys_lazy_modules

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
# Return the module state specification and Python source file name for the
# given module if they exist for the module.  A module can have both, have only
# a spec, or have neither.
#

def _locate(module:ModuleType) -> tuple[ModuleSpec|None, str|None]:
    spec = module.__spec__
    if spec is None: return None, None
    if not spec.has_location: return spec, None
    origin = spec.origin
    assert origin is not None
    if not origin.endswith(".py"): return spec, None
    return spec, origin


##############################################################################
#                                 MODEL
##############################################################################

#
# We record an import journal for target namespaces as import statements are
# registered.  Each journal entry is an _ImportRecord instance with a
# rebind(namespace) method executing the name binding actions of the
# corresponding import statements with respect to the target namespace.
#

class _ImportJournal:
    __slots__ = "sequence"

    def __init__(self):
        self.sequence:list[_ImportRecord] = []

    #
    # Apply the journal to a namespace.
    #

    def apply(self, namespace:dict[str,Any]):
        for record in self.sequence:
            record.rebind(namespace)

    #
    # Extend the journal by adding the given records in order.  Then, remove
    # superseded records having identical statements.
    #

    def extend(self, additional:list[_ImportRecord]):

        sequence = self.sequence
        sequence.extend(additional)

        statement_set = set[str]()
        result        = list[_ImportRecord]()

        for record in reversed(sequence):
            statement = record.statement()
            if statement not in statement_set:
                result.append(record)
                statement_set.add(statement)

        result.reverse()
        self.sequence = result

    #
    # Return true iff the implied single binding import statement is covered by
    # an import record in the journal.  Used for testing and debugging only.
    # See _is_registered() in _debug.py.
    #

    def covers(self, modulename:str, name:str|None, asname:str|None) -> bool:
        return any(record.covers(modulename, name, asname)
                   for record in self.sequence)

    #
    # Used for testing and debugging.  See _hash_state() in _debug.py.
    #

    def __hash__(self) -> int:
        return hash(tuple(record.statement() for record in self.sequence))

#
# An _ImportIssue describes a problem related to an import record, either
# related to the underlying import statement not having been executed or some
# mutation in the environment preventing rebinding.  Import issues never escape
# the public API.
#

class _ImportIssue(Exception):
    __slots__ = "issue"

    def __init__(self, issue:str):
        self.issue = issue

    def __str__(self):
        return "IMPORT ISSUE ESCAPED: " + self.issue

#
# Return the named module, which must be loaded.
#

def _require_module(modulename:str) -> ModuleType:
    if (module := sys.modules.get(modulename)) is None:
        raise _ImportIssue(f"Module {modulename} not loaded")
    return module

#
# Return the named module attribute, which must exist.
#

def _require_attr(module:ModuleType, name:str) -> Any:
    try:
        return getattr(module,name)
    except AttributeError:
        raise _ImportIssue(f"No name {name} in {module.__name__}")

#
# Require the named variable to exist in the given namespace.
#

def _require_name_exists(namespace:dict[str,Any], name:str) -> None:
    if name not in namespace:
        raise _ImportIssue(f"No name {name} in namespace")

#
# Ensure modulename refers to a loaded module with loaded ancestors, returning
# the module object.  _validate_hierarchy() loads the named module if it's
# lazily imported.
#
# We previously wrapped exceptions during validation module loads in
# ImportError -- but that's wrong.  In a normal notebook cell, importing a
# module with, say, a bad top level name use results in a NameError exception,
# not an ImportError.  We want to match that behavior.
#

def _validate_hierarchy(modulename:str) -> ModuleType:
    if _is_lazy(modulename):
        import_module(modulename)
    hierarchy = modulename.split('.')
    parentname = hierarchy[0]
    parent = _require_module(parentname)
    for subname in hierarchy[1:]:
        childname = parentname + '.' + subname
        child = _require_module(childname)
        _require_attr(parent,subname)
        parentname = childname
        parent = child
    return parent

#
# Describe a registered import statement, possibly in part.
#
# The correspondence between import records and registered import statements is
# not one-to-one: referring to Python language grammar elements, each
# dotted_as_name of an import_name statement is mapped to a unique record,
# while an import_from statement is always mapped to a single record.
#
# There is, however, a one-to-one relationship between import records and a set
# of equivalent import statements.  See method _ImportRecord.statement().
#

class _ImportRecord(ABC):

    __slots__ = "modulename"

    def __init__(self, modulename:str):
        self.modulename = modulename

    #
    # Determine if the import record may correspond to an executed import
    # statement.  If not, validate() raises an _ImportIssue exception.  As a
    # side effect, validate() causes all referenced modules that are only
    # lazily imported to be loaded.
    #
    # validate() does NOT reify namespace names.  So, assuming a.b.x is a
    # module, validating the record for "lazy from a.b import x" will load
    # "a.b", load "a.b.x", and leave variable x bound to a proxy.
    #

    @abstractmethod
    def validate(self, namespace:dict[str,Any]) -> None:
        pass # pragma: no cover

    #
    # Return an import statement equivalent to the import record.
    #

    @abstractmethod
    def statement(self) -> str:
        pass # pragma: no cover

    #
    # Carry out namespace binding actions of the equivalent import record.
    #

    @abstractmethod
    def rebind(self, namespace:dict[str,Any]) -> None:
        pass # pragma: no cover

    #
    # Return true iff the import actions implied by modulename, name, and
    # asname (see _debug._is_registered()) are a subset of the actions of the
    # record's equivalent import statement.  covers() is only used for
    # debugging and testing.
    #

    @abstractmethod
    def covers(self, modulename:str, name:str|None, asname:str|None) -> bool:
        pass # pragma: no cover

    def __repr__(self):
        return ("Record<" + self.statement() + ">")

#
# import a.b.c
#

class _ImportNameRecord(_ImportRecord):
    __slots__ = "topname"

    def __init__(self, modulename:str):
        super().__init__(modulename)
        self.topname = modulename.split(".",1)[0]

    def validate(self, namespace:dict[str,Any]) -> None:
        _validate_hierarchy(self.modulename)
        _require_name_exists(namespace,self.topname)

    def statement(self) -> str:
        return f"import {self.modulename}"

    def rebind(self, namespace:dict[str,Any]):
        topname = self.topname
        namespace[topname] = _require_module(topname)

    def covers(self, modulename:str, name:str|None, asname:str|None) -> bool:
        return (name is None and asname is None and
                modulename == self.modulename)

#
# import a.b.c as x
#

class _ImportNameAsRecord(_ImportRecord):
    __slots__ = "asname"

    def __init__(self, modulename:str, asname:str):
        super().__init__(modulename)
        self.asname = asname

    def validate(self, namespace:dict[str,Any]) -> None:
        _validate_hierarchy(self.modulename)
        _require_name_exists(namespace,self.asname)

    def statement(self) -> str:
        return f"import {self.modulename} as {self.asname}"

    def rebind(self, namespace:dict[str,Any]):
        asname = self.asname
        namespace[asname] = _require_module(self.modulename)

    def covers(self, modulename:str, name:str|None, asname:str|None) -> bool:
        return (name is None and asname == self.asname and
                modulename == self.modulename)

#
# from a.b.c import name1 as asname1, name2 as asname2, ...
#
# The asname elements must not be None -- they should be aliases of the
# corresponding names if not provided in the from import statement.
#

class _ImportFromNamesRecord(_ImportRecord):
    __slots__ = "namepairs"

    def __init__(self, modulename:str, namepairs:list[tuple[str,str]]):
        super().__init__(modulename)
        self.namepairs = namepairs

    def validate(self, namespace:dict[str,Any]) -> None:
        modulename = self.modulename
        module = _validate_hierarchy(modulename)
        for name, asname in self.namepairs:
            #
            # SOMEDAY: Consider relying on reify behavior of getattr() instead
            # of checking __dict__ and explicitly importing.
            #
            if name not in module.__dict__:
                submodname = modulename + '.' + name
                if _is_lazy(submodname):
                    import_module(submodname)
            _require_attr(module,name)
            _require_name_exists(namespace,asname)

    def statement(self) -> str:
        return (f"from {self.modulename} import " +
                ", ".join(
                    name + ('' if asname is None else " as " + asname)
                    for name, asname in self.namepairs))

    def rebind(self, namespace:dict[str,Any]):
        module = _require_module(self.modulename)
        for name, asname in self.namepairs:
            namespace[asname] = _require_attr(module,name)

    def covers(self, modulename:str, name:str|None, asname:str|None) -> bool:
        if asname is None: asname = name
        return (modulename == self.modulename and
                any(name == pair[0] and asname == pair[1]
                    for pair in self.namepairs))

#
# from a.b.c import *
#

class _ImportFromStarRecord(_ImportRecord):
    __slots__ = ()

    def __init__(self, modulename:str):
        super().__init__(modulename)

    def validate(self, namespace:dict[str,Any]) -> None:
        # Wildcard imports cannot be lazy.
        _require_module(self.modulename)
        _validate_hierarchy(self.modulename)

    def statement(self) -> str:
        return f"from {self.modulename} import *"

    def rebind(self, namespace:dict[str,Any]):
        module = _require_module(self.modulename)
        star_names = (module.__all__ if hasattr(module,'__all__') else
                      (name for name in dir(module)
                      if not name.startswith('_')))
        for name in star_names:
            namespace[name] = _require_attr(module,name)

    def covers(self, modulename:str, name:str|None, asname:str|None) -> bool:
        return (name == '*' and asname is None and
                modulename == self.modulename)

#
# Information LiveImport tracks about namespaces in _NAMESPACE_TABLE keyed by
# id.  A namespace has an entry in _NAMESPACE_TABLE iff there are registered
# imports for it.  Each has a compacted rebind journal equivalent to executing
# those registered imports in the order they are registered.
#

class _NamespaceInfo:
    __slots__ = "namespace", "journal"

    namespace:dict[str,Any]
    journal:_ImportJournal

    def __init__(self,namespace:dict[str,Any]):
        self.namespace = namespace
        self.journal = _ImportJournal()

_NAMESPACE_TABLE:dict[int,_NamespaceInfo] = dict()

#
# Information LiveImport tracks about a loaded module in _MODULE_TABLE.  We
# never delete _ModuleInfo objects from _MODULE_TABLE, except in testing.  That
# means we can maintain what we know about module source file modification
# times if registrations are cleared.
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

        spec, file = _locate(module)
        if spec is None:
            raise ValueError(f"Module {module.__name__} has no spec")

        self.module       = module
        self.parent       = '' if spec.parent is None else spec.parent
        self.attachedto   = set()
        self.mark         = 0
        self.mtime        = -math.inf
        self.next_mtime   = -math.inf
        self.dependencies = []

        if file is not None:
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
    # "A.B" dependency when A.B turns out to be a tracked module.  Recording
    # possibly instead of definitely referenced module names is an
    # implementation necessity: it enables the dependency graph to evolve
    # naturally as imports are registered and cleared.
    #

    def analyze_dependencies(self) -> None:

        assert self.file

        with open(self.file) as f:
            source = f.read()

        result:set[str] = set()

        try:
            for stmt in ast.parse(source,self.file).body:
                if isinstance(stmt,ast.Import):
                    for alias in stmt.names:
                        result.add(alias.name)
                elif isinstance(stmt,ast.ImportFrom):
                    module = _absolute_module(stmt,self.parent,self.file)
                    result.add(module)
                    for alias in stmt.names:
                        result.add(module + '.' + alias.name)
        except Exception as ex:
            raise ModuleError(self.module.__name__,"analysis") from ex

        for modulename in result:
            if _is_lazy(modulename):
                _REIFY_WATCH.add(modulename)

        self.dependencies = list(result)

_MODULE_TABLE:dict[str,_ModuleInfo] = dict()

#
# Make sure all tracked module dependencies are themselves tracked if they have
# source files in the workspace.  _track_new_indirects() should be called after
# imports are registered, and after modules are reloaded.
#

def _track_new_indirects() -> None:

    #
    # We perform a breadth-first traversal of the dependency graph.  The initial
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
                _, file = _locate(module)
                if file is None: continue
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
# The set of lazily imported modules discovered during dependency analysis.
#

_REIFY_WATCH:set[str] = set()

#
# Register an import record, verifying there is evidence that an encompassing
# import statement was actually executed.  _register_record() tracks modules
# and adds namespace attachments as needed.
#

def _register_record(record:_ImportRecord, namespace:dict[str,Any],
                     records:list[_ImportRecord],
                     attachments:list[_ModuleInfo]):

    try:
        record.validate(namespace)
    except _ImportIssue as ex:
        raise ValueError(ex.issue + "; missing " +
                         record.statement() + "?") from None

    modules = sys.modules
    module = modules[modulename := record.modulename]
    attachments.append(_track(module))

    if isinstance(record,_ImportFromNamesRecord):
        prefix = modulename + "."
        for name, _ in record.namepairs:
            child = modules.get(prefix + name)
            if child is not None and getattr(module,name,None) is child:
                attachments.append(_track(child))

    records.append(record)


##############################################################################
#                               PUBLIC API
##############################################################################

def register(namespace:dict[str,Any], importstmts:str,
             *, package:str='', clear:bool=False,
             allow_other_statements:bool=False) -> None:
    """
    Register import statements for syncing.

    All modules referenced by the import statements must have specs and either
    be loaded or lazily imported, and all names mentioned must already exist in
    `namespace`.  If a referenced module is lazily imported, :func:`register`
    loads it.  If an associated source file is later modified, then a sync will
    reload the corresponding module and update names from the module.

    :param namespace: The import statement target, usually the caller's value
        of ``globals()``.

    :param importstmts: Python code consisting of zero or more import
        statements.  The application should have already executed these or
        equivalent imports.

    :param package: Context for interpreting relative import statements.  When
        given, `package` is usually the caller's immediate parent package,
        accessible as ``__spec__.parent`` if it exists.  If no package is
        specified, relative imports are not allowed.  Relative imports are only
        useful when using LiveImport outside a notebook, since notebook code is
        not in a package.

    :param clear: If and only if true, discard all prior registrations
        targeting `namespace` before registering the given import statements.

    :param allow_other_statements: If true, non-import statements are allowed
        in `importstmts` and ignored.  Otherwise, only import statements are
        allowed.

    :raises SyntaxError: `importstmts` is not syntactically valid.

    :raises ImportError: `importstmts` includes an improper relative import.

    :raises ValueError: `importstmts` includes a non-import statement and
        `allow_other_statements` is false, a referenced module has no spec or
        is not loaded and not lazily imported, or an included name does not
        already exist.

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
    own line as shown above, is convenient and easy to read, but statements must
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

    records:list[_ImportRecord] = []
    attachments:list[_ModuleInfo] = []

    source = textwrap.dedent(importstmts)
    for stmt in ast.parse(source,"<importstmts>").body:
        if isinstance(stmt,ast.Import):
            #
            # Case 1: import a.b.c
            # Case 2: import a.b.c as x
            #
            for alias in stmt.names:
                modulename = alias.name
                asname = alias.asname
                _register_record(
                    _ImportNameRecord(modulename) if asname is None
                    else _ImportNameAsRecord(modulename, asname),
                    namespace, records, attachments)

        elif isinstance(stmt,ast.ImportFrom):
            #
            # Case 3: from [.*] a.b.c import *
            # Case 4: from [.*] a.b.c import x [ as y ], ...
            #
            modulename = _absolute_module(stmt,package)
            if len(stmt.names) == 1 and stmt.names[0].name == '*':
                record = _ImportFromStarRecord(modulename)
            else:
                record = _ImportFromNamesRecord(modulename,
                    [ (a.name, a.name if a.asname is None else a.asname)
                      for a in stmt.names ])
            _register_record(record,namespace,records,attachments)
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
        nsinfo.journal = _ImportJournal()

    if not records:
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

    nsinfo.journal.extend(records)

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

    :raises ModuleError: The content of a tracked module is erroneous or raised
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
    # Mark interpretation:
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
        except Exception as ex:
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
        try:
            nsinfo.journal.apply(nsinfo.namespace)
        except _ImportIssue as ex:
            raise RuntimeError(ex.issue) from None

    if reload_error is not None:
        raise ModuleError(info.module.__name__,"reload") from reload_error

    #
    # We check for new indirects after reloads since we need new indirects to
    # be already loaded.
    #

    _track_new_indirects()


def poll_lazy_imports():
    """
    Begin tracking modules of lazy imports that have now resolved.

    During dependency analysis, LiveImport may discover that a tracked module
    depends on a module which is not loaded but is lazily imported.  LiveImport
    defers tracking such modules until the first :func:`poll_lazy_imports()`
    call after the application loads the lazily imported module, usually
    through reification.  If :func:`poll_lazy_imports()` discovers a lazily
    imported dependency has loaded, it begins tracking that module if the
    module is in the workspace.

    :raises ModuleError: The content of a newly tracked module is erroneous.

    .. note::
        Calling :func:`poll_lazy_imports()` in a notebook should not be
        necessary.  LiveImport automatically polls lazy imports after each cell
        execution.
    """
    modules = sys.modules
    reified = [ x for x in _REIFY_WATCH if x in modules ]
    if reified:
        for modulename in reified:
            _REIFY_WATCH.remove(modulename)
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

from __future__ import annotations
import sys
from abc import ABC, abstractmethod
from types import ModuleType
from typing import Any

#
# We record an import journal for target namespaces as import statements are
# registered.  Each journal entry is an _ImportRecord instance with a
# rebind(namespace) method executing the name binding actions of the
# corresponding import statements with respect to the target namespace.
#
# An import record can be eager (example: _ImportNameAsRecorc) or lazy
# (example: _LazyImportNameAsRecord).  Eager rebind steps correspond to imports
# of modules known to be loaded (Python <= 3.14 imports, or non-lazy or reified
# Python >= 3.15 imports).  Lazy rebind steps correspond to imports of lazily
# imported modules not yet known to be loaded.
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
    # superceded records having identical statements.
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
# We judge an import statement to have not executed if
#
#    1. Some module in the hierarchy is not loaded.
#    2. An expected name in the target namespace is not present.
#    3. An expected name in a module is not present.
#
# We could be more strict -- we could require names in modules and namespaces
# to actually reference the expected modules.  However, applications could
# break that by assigning to those names between import execution and
# registration.  (Applications could also delete names from modules and the
# target namespace, and delete modules from sys.modules, but that would be
# unusual to say the least.)
#

class _ImportIssue(Exception):
    __slots__ = "issue"

    def __init__(self, issue:str):
        self.issue = issue

    def __str__(self):
        return "IMPORT ISSUE ESCAPED: " + self.issue


def _require_module(modulename:str) -> ModuleType:
    if (module := sys.modules.get(modulename)) is None:
        raise _ImportIssue(f"Module {modulename} not loaded")
    return module


def _require_attr(module:ModuleType, name:str) -> Any:
    try:
        return getattr(module,name)
    except AttributeError:
        raise _ImportIssue(f"No name {name} in {module.__name__}")


def _require_name(namespace:dict[str,Any], name:str) -> None:
    if name not in namespace:
        raise _ImportIssue(f"No name {name} in namespace")


def _validate_hierarchy(modulename:str) -> None:
    modules = sys.modules
    hierarchy = modulename.split('.')
    parentname = hierarchy[0]
    parent = _require_module(parentname)
    for subname in hierarchy[1:]:
        childname = parentname + '.' + subname
        child = _require_module(childname)
        _require_attr(parent,subname)
        parentname = childname
        parent = child


class _ImportRecord(ABC):

    __slots__ = "modulename"

    @abstractmethod
    def validate(self, namespace:dict[str,Any]) -> None:
        pass # pragma: no cover

    @abstractmethod
    def statement(self) -> str:
        pass # pragma: no cover

    @abstractmethod
    def rebind(self, namespace:dict[str,Any]) -> None:
        pass # pragma: no cover

    @abstractmethod
    def covers(self, modulename:str, name:str|None, asname:str|None) -> bool:
        pass # pragma: no cover

    def __repr__(self):
        return f"Record<{self.statement()}>"

#
# import a.b.c
#

class _ImportNameRecord(_ImportRecord):
    __slots__ = "topname"

    def __init__(self, modulename:str):
        self.modulename = modulename
        self.topname = modulename.split(".",1)[0]

    def validate(self, namespace:dict[str,Any]) -> None:
        _validate_hierarchy(self.modulename)
        _require_name(namespace,self.topname)

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
        self.modulename = modulename
        self.asname = asname

    def validate(self, namespace:dict[str,Any]) -> None:
        _validate_hierarchy(self.modulename)
        _require_name(namespace,self.asname)

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
# NB: The asname elements must not be None -- the should be aliases of the
# corresponding names if not provided in the from import statement.
#

class _ImportFromNamesRecord(_ImportRecord):
    __slots__ = "namepairs"

    def __init__(self, modulename:str, namepairs:list[tuple[str,str]]):
        self.modulename = modulename
        self.namepairs = namepairs

    def validate(self, namespace:dict[str,Any]) -> None:
        _validate_hierarchy(self.modulename)
        module = _require_module(self.modulename)
        for name, asname in self.namepairs:
            _require_attr(module,name)
            _require_name(namespace,asname)

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
        self.modulename = modulename

    def validate(self, namespace:dict[str,Any]) -> None:
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

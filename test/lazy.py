#
# Lazy import tests -- even on pre-3.15 Python.
#

from abc import ABC, abstractmethod
import sys
from typing import Any, Collection
from importlib import import_module
import liveimport
from setup import *
from liveimport._core import _sys_lazy_modules


is_registered = is_registered_fn(globals())


_DEPENDS_ON = [
    ("su4a.b.y","su5a.b.y"),
    ("su5a.b.y","su6a.b.y"),
    ("su5a.b.y","su7a.b.y"),
]


#
# Mock lazy import proxies (LazyImportType).  Only used when running without
# real lazy imports.
#

class _MockLazyImportType(ABC):
    @abstractmethod
    def resolve(self) -> Any:
        pass

class _MockLazyImportNameType(_MockLazyImportType):
    __slots__ = "modulename", "namespace", "topname"

    def __init__(self, modulename:str, namespace:dict[str,Any]):
        self.modulename = modulename
        self.namespace  = namespace
        self.topname    = modulename.split('.',1)[0]

    def resolve(self) -> Any:
        import_module(self.modulename)
        value = sys.modules[self.topname]
        self.namespace[self.topname] = value
        return value

    def __repr__(self) -> str:
        return f"<mock_lazy_import {self.modulename}>"

class _MockLazyImportNameAsType(_MockLazyImportType):
    __slots__ = "modulename", "namespace", "asname"

    def __init__(self, modulename:str, namespace:dict[str,Any], asname:str):
        self.modulename = modulename
        self.namespace  = namespace
        self.asname     = asname

    def resolve(self) -> Any:
        value = import_module(self.modulename)
        self.namespace[self.asname] = value
        return value

    def __repr__(self) -> str:
        return f"<mock_lazy_import {self.modulename} as {self.asname}>"

class _MockLazyImportFromType(_MockLazyImportType):
    __slots__ = "modulename", "namespace", "name", "asname"

    def __init__(self, modulename:str, namespace:dict[str,Any], name:str,
                 asname:str):
        self.modulename = modulename
        self.namespace  = namespace
        self.name       = name
        self.asname     = asname

    def resolve(self) -> Any:
        module = import_module(self.modulename)
        value = (getattr(module,self.name) if hasattr(module,self.name) else
                 import_module(self.modulename + '.' + self.name))
        self.namespace[self.asname] = value
        return value

    def __repr__(self) -> str:
        return (f"<mock_lazy_import_from {self.modulename} "
                f"{self.name} as {self.asname}>")

#
# Fortunately, it's easy to dynamically lazy import into the current module.
# That make mocking lazy imports straightforward.
#

if REAL_LAZY_IMPORTS:

    def lazy_import_name(modulename:str, asname:str|None=None) -> None:
        exec(f"lazy import {modulename}" if asname is None else
             f"lazy import {modulename} as {asname}",globals())


    def lazy_import_from(modulename:str,
                         *namepairs:tuple[str,str|None]) -> None:
        exec(f"lazy from {modulename} import " +
             ", ".join(name if asname is None else name + " as " + asname
                       for name, asname in namepairs), globals())

    from types import LazyImportType # type: ignore
    def is_proxy(name:str):
        return isinstance(globals()[name],LazyImportType)

else:

    def lazy_import_name(modulename:str, asname:str|None=None) -> None:
        _sys_lazy_modules.add(modulename)
        if asname is None:
            topname = modulename.split('.',1)[0]
            globals()[topname] = _MockLazyImportNameType(modulename,globals())
        else:
            globals()[asname] = _MockLazyImportNameAsType(
                modulename,globals(),asname)

    def lazy_import_from(modulename:str,
                         *namepairs:tuple[str,str|None]) -> None:
        _sys_lazy_modules.add(modulename)
        for name, asname in namepairs:
            if asname is None: asname = name
            extendedname = modulename + '.' + name
            _sys_lazy_modules.add(extendedname)
            globals()[asname] = _MockLazyImportFromType(
                modulename,globals(),name,asname)

    def is_proxy(name:str):
        return isinstance(globals()[name],_MockLazyImportType)

#
# While mocking lazy imports into the current module is easy, dependency
# imports are another matter.  We could make the machinery above available in
# the subject modules, but instead we use force_mock_lazy() to cause force
# select imports to look lazy after the fact.
#

def force_mock_lazy(population:Collection[str], modulename:str):
    if is_lazy(modulename):
        return
    modules = sys.modules
    assert (module := modules.get(modulename)) is not None
    del modules[modulename]
    _sys_lazy_modules.add(modulename)
    for othername in population:
        if (other := modules.get(othername)) is not None:
            for name, value in other.__dict__.items():
                if value is module:
                    setattr(other,name,_MockLazyImportNameAsType(
                        modulename,other.__dict__,name))


su1a:Any = None
su2ab:Any = None
su3abx:Any = None
su3aby:Any = None

def test_resolve_on_register():
    """
    Lazily imported modules are resolved when related import statements are
    registered.
    """
    lazy_import_name("su1a.b")
    lazy_import_name("su2a.b", "su2ab")
    lazy_import_from("su3a.b",("x","su3abx"),("y","su3aby"))

    assert is_lazy("su1a.b")
    assert is_lazy("su2a.b")
    assert is_lazy("su3a.b")
    assert is_lazy("su3a.b.x")  # Because it *might* be a module
    assert is_lazy("su3a.b.y")

    liveimport.register(globals(),"""
    import su1a.b
    import su2a.b as su2ab
    from su3a.b import x as su3abx, y as su3aby
    """, clear=True)

    assert is_registered("su1a.b")
    assert is_registered("su2a.b",None,"su2ab")
    assert is_registered("su3a.b","x","su3abx")
    assert is_registered("su3a.b","y","su3aby")

    assert not is_lazy("su1a.b")
    assert not is_lazy("su2a.b")
    assert not is_lazy("su3a.b")
    assert not is_lazy("su3a.b.y")

    assert is_proxy("su1a")
    assert is_proxy("su2ab")
    assert is_proxy("su3abx")
    assert is_proxy("su3aby")

    su1ab_tag = get_tag("su1a.b")
    su2ab_tag = get_tag("su2a.b")
    su3ab_tag = get_tag("su3a.b")
    su3aby_tag = get_tag("su3a.b.y")

    touch_module("su1a.b",0)
    touch_module("su2a.b",0)
    touch_module("su3a.b",0)
    touch_module("su3a.b.y")

    liveimport.sync()

    expect_tag("su1a.b",next_tag(su1ab_tag))
    expect_tag("su2a.b",next_tag(su2ab_tag))
    expect_tag("su3a.b",next_tag(su3ab_tag))
    expect_tag("su3a.b.y",next_tag(su3aby_tag))


#
# There are two versions of test_dependencies, real and mock.  The mock test is
# a large subset of the real test we can run without absurd gyrations (though
# some tricky surgery is still required.)  The mock subset is large enough to
# exercise all of LiveImport's lazy import machinery.
#

import su4a.b.y as su4aby  # type: ignore

def real_test_dependencies():
    """
    Lazily import dependencies are resolved only by the application, assuming
    the module of the dependency is referenced by a registered import
    statement.
    """
    #
    # su4a.b.y lazy imports su5a.b.y, which lazy imports su5a.b.y.
    #

    assert not is_lazy("su4a.b.y")

    liveimport.register(globals(),"""
    import su4a.b.y as su4aby
    """, clear=True)

    assert is_registered("su4a.b.y",None,"su4aby")

    #
    # Dependencies should be not be loaded or tracked yet.  However, su5a.b.y
    # should be lazy and watched for reification because su4a.b.y depends on
    # it.  su[67]a.b.y are not lazy because they are not yet imported in any
    # way.
    #

    assert "su5a.b.y" not in sys.modules
    assert "su6a.b.y" not in sys.modules
    assert "su7a.b.y" not in sys.modules
    assert is_lazy("su5a.b.y")
    assert not is_lazy("su6a.b.y")
    assert not is_lazy("su7a.b.y")
    assert not is_tracked("su5a.b.y")
    assert not is_tracked("su6a.b.y")
    assert not is_tracked("su7a.b.y")
    assert is_reify_watched("su5a.b.y")
    assert not is_reify_watched("su6a.b.y")
    assert not is_reify_watched("su7a.b.y")

    #
    # If su7a.b.y becomes loaded (perhaps by an import not stemming from a
    # registered import) it should still remain untracked even after poll
    # because there is no path from a tracked module to su7a.b.y.
    #

    import_module("su7a.b.y")

    assert "su5a.b.y" not in sys.modules
    assert "su6a.b.y" not in sys.modules
    assert "su7a.b.y" in sys.modules
    assert is_lazy("su5a.b.y")
    assert not is_lazy("su6a.b.y")
    assert not is_lazy("su7a.b.y")
    assert not is_tracked("su5a.b.y")
    assert not is_tracked("su6a.b.y")
    assert not is_tracked("su7a.b.y")
    assert is_reify_watched("su5a.b.y")
    assert not is_reify_watched("su6a.b.y")
    assert not is_reify_watched("su7a.b.y")

    #
    # Polling should make no difference since the application hasn't reified
    # the imports yet.
    #

    liveimport.poll_lazy_imports()

    assert "su5a.b.y" not in sys.modules
    assert "su6a.b.y" not in sys.modules
    assert "su7a.b.y" in sys.modules
    assert is_lazy("su5a.b.y")
    assert not is_lazy("su6a.b.y")
    assert not is_lazy("su7a.b.y")
    assert not is_tracked("su5a.b.y")
    assert not is_tracked("su6a.b.y")
    assert not is_tracked("su7a.b.y")
    assert is_reify_watched("su5a.b.y")
    assert not is_reify_watched("su6a.b.y")
    assert not is_reify_watched("su7a.b.y")

    #
    # After the application reifies the reference to su5a.b.y, su5a.b.y should
    # become loaded, but still not tracked since there has been no poll yet.
    # su6a.b.y becomes lazy because the lazy import in su5a.b.y executed.
    # (su7a.b.y does not become lazy because it is loaded.)
    #

    su4aby.__dict__['su5aby'].resolve()  #type:ignore

    assert "su5a.b.y" in sys.modules
    assert "su6a.b.y" not in sys.modules
    assert "su7a.b.y" in sys.modules
    assert not is_lazy("su5a.b.y")
    assert is_lazy("su6a.b.y")
    assert not is_lazy("su7a.b.y")
    assert not is_tracked("su5a.b.y")
    assert not is_tracked("su6a.b.y")
    assert not is_tracked("su7a.b.y")
    assert is_reify_watched("su5a.b.y")
    assert not is_reify_watched("su6a.b.y")
    assert not is_reify_watched("su7a.b.y")

    #
    # After polling, su5a.b.y should become tracked, causing su7a.b.y to become
    # tracked and su6a.b.y watched for reification.
    #

    liveimport.poll_lazy_imports()

    assert "su5a.b.y" in sys.modules
    assert "su6a.b.y" not in sys.modules
    assert "su7a.b.y" in sys.modules
    assert not is_lazy("su5a.b.y")
    assert is_lazy("su6a.b.y")
    assert not is_lazy("su7a.b.y")
    assert is_tracked("su5a.b.y")
    assert not is_tracked("su6a.b.y")
    assert is_tracked("su7a.b.y")
    assert not is_reify_watched("su5a.b.y")
    assert is_reify_watched("su6a.b.y")
    assert not is_reify_watched("su7a.b.y")

    #
    # We touch su6a.b.y's source file, but because it isn't yet loaded, it will
    # not reload.  Module is su7a.b.y is loaded and tracked, so it will reload,
    # along with su5a.b.y and su4a.b.y because of the dependency chain.
    #

    touch_file("su6a/b/y.py")
    touch_module("su7a.b.y")

    reload_clear()
    liveimport.sync(observer=reload_observe)
    reload_expect("su4a.b.y","su5a.b.y","su7a.b.y",
                  depends_on=_DEPENDS_ON)

    #
    # After a load and poll, su6a.b.y reloads when touched.
    #

    import_module("su6a.b.y")
    liveimport.poll_lazy_imports()

    touch_module("su6a.b.y")
    reload_clear()
    liveimport.sync(observer=reload_observe)
    reload_expect("su4a.b.y","su5a.b.y","su6a.b.y",
                  depends_on=_DEPENDS_ON)


def mock_test_dependencies():
    """
    Lazily import dependencies are resolved only by the application, assuming
    the module of the dependency is referenced by a registered import
    statement.
    """
    #
    # su4a.b.y lazy imports su5a.b.y, which lazy imports su5a.b.y.
    #

    assert not is_lazy("su4a.b.y")

    #
    # (Imports of su[567]a.b.y should all be lazy.  su[67]a.b.y should not
    # actually be imported at all yet su5a.b.y isn't loaded.)
    #

    force_mock_lazy(("su4a.b.y", "su5a.b.y"), "su6a.b.y")
    force_mock_lazy(("su4a.b.y", "su5a.b.y"), "su7a.b.y")
    force_mock_lazy(("su4a.b.y",), "su5a.b.y")
    _sys_lazy_modules.remove("su6a.b.y")
    _sys_lazy_modules.remove("su7a.b.y")

    liveimport.register(globals(),"""
    import su4a.b.y as su4aby
    """, clear=True)

    assert is_registered("su4a.b.y",None,"su4aby")

    #
    # Dependencies should be not be loaded or tracked yet.  However, su5a.b.y
    # should be lazy and watched for reification because su4a.b.y depends on
    # it.
    #

    assert "su5a.b.y" not in sys.modules
    assert "su6a.b.y" not in sys.modules
    assert "su7a.b.y" not in sys.modules
    assert is_lazy("su5a.b.y")
    assert not is_lazy("su6a.b.y")
    assert not is_lazy("su7a.b.y")
    assert not is_tracked("su5a.b.y")
    assert not is_tracked("su6a.b.y")
    assert not is_tracked("su7a.b.y")
    assert is_reify_watched("su5a.b.y")
    assert not is_reify_watched("su6a.b.y")
    assert not is_reify_watched("su7a.b.y")

    #
    # If su7a.b.y becomes loaded (perhaps by an import not stemming from a
    # registered import) it should still remain untracked even after poll
    # because there is no path from a tracked module to su7a.b.y.
    #

    import_module("su7a.b.y")

    assert "su5a.b.y" not in sys.modules
    assert "su6a.b.y" not in sys.modules
    assert "su7a.b.y" in sys.modules
    assert is_lazy("su5a.b.y")
    assert not is_lazy("su6a.b.y")
    assert not is_lazy("su7a.b.y")
    assert not is_tracked("su5a.b.y")
    assert not is_tracked("su6a.b.y")
    assert not is_tracked("su7a.b.y")
    assert is_reify_watched("su5a.b.y")
    assert not is_reify_watched("su6a.b.y")
    assert not is_reify_watched("su7a.b.y")

    #
    # Polling should make no difference since the application hasn't reified
    # the imports yet.
    #

    liveimport.poll_lazy_imports()

    assert "su5a.b.y" not in sys.modules
    assert "su6a.b.y" not in sys.modules
    assert "su7a.b.y" in sys.modules
    assert is_lazy("su5a.b.y")
    assert not is_lazy("su6a.b.y")
    assert not is_lazy("su7a.b.y")
    assert not is_tracked("su5a.b.y")
    assert not is_tracked("su6a.b.y")
    assert not is_tracked("su7a.b.y")
    assert is_reify_watched("su5a.b.y")
    assert not is_reify_watched("su6a.b.y")
    assert not is_reify_watched("su7a.b.y")

    #
    # After the application reifies the reference to su5a.b.y, su5a.b.y should
    # become loaded, but still not tracked since there has been no poll yet.
    # su6a.b.y becomes lazy because the lazy import in su5a.b.y executed.
    # (su7a.b.y does not become lazy because it is loaded.)
    #

    su4aby.__dict__['su5aby'].resolve()  #type:ignore
    assert "su5a.b.y" in sys.modules

    #
    # (Here we have to force su6a.b.y back to lazy since when mocked the
    # su5a.b.y reification load eager imported su6a.b.y.)
    #

    force_mock_lazy(("su4a.b.y", "su5a.b.y"), "su6a.b.y")

    assert "su6a.b.y" not in sys.modules
    assert "su7a.b.y" in sys.modules
    assert not is_lazy("su5a.b.y")
    assert is_lazy("su6a.b.y")
    assert not is_lazy("su7a.b.y")
    assert not is_tracked("su5a.b.y")
    assert not is_tracked("su6a.b.y")
    assert not is_tracked("su7a.b.y")
    assert is_reify_watched("su5a.b.y")
    assert not is_reify_watched("su6a.b.y")
    assert not is_reify_watched("su7a.b.y")

    #
    # After polling, su5a.b.y should become tracked, causing su7a.b.y to become
    # tracked and su6a.b.y watched for reification.
    #

    liveimport.poll_lazy_imports()

    assert "su5a.b.y" in sys.modules
    assert "su6a.b.y" not in sys.modules
    assert "su7a.b.y" in sys.modules
    assert not is_lazy("su5a.b.y")
    assert is_lazy("su6a.b.y")
    assert not is_lazy("su7a.b.y")
    assert is_tracked("su5a.b.y")
    assert not is_tracked("su6a.b.y")
    assert is_tracked("su7a.b.y")
    assert not is_reify_watched("su5a.b.y")
    assert is_reify_watched("su6a.b.y")
    assert not is_reify_watched("su7a.b.y")


test_dependencies = (
    real_test_dependencies if REAL_LAZY_IMPORTS else
    mock_test_dependencies)

#
# Common support for testing liveimport in both scripts and notebooks.
#

import atexit
from contextlib import contextmanager
import importlib.util
import importlib.metadata
import os
import sys
import textwrap
import time
import tempfile
from typing import Any
import liveimport
from liveimport import ReloadEvent

"""
_setup() generates the following file hierarchy in a temporary directory:

    mod1.py
    mod2.py
    mod3.py  ; imports pkg.subpkg.ssmod2
    mod4.py  ; has __all__ for mod4_public1 and mod4_public2
    mod5.py  ; imported as hide_mod5
    mod6.pt  ; imports A, pkg.smod1, altpkg.amod1
    pkg/
        __init__.py
        smod1.py
        smod2.py
        smod3.py
        smod4.py
        subpkg/
            __init__.py
            ssmod1.py
            ssmod2.py  ; has relative imports from ssmod1 and smod1
    altpkg/
        __init__.py
        amod1.py
    A.py  ; depends on C
    B.py  ; depends on C, D, G
    C.py  ; depends on E, F
    D.py  ; depends on F
    E.py  ; depends on A
    F.py  ; depends on [none]
    G.py  ; depends on [none]

All the modules include "import re", "from math import nan", a _tag variable,
three <basename>_public<n>() functions, three <basename>_private<n>() functions,
and varying additional imports and __all__ declarations upon which tests rely.
<basename> is the part of a module's name past the last dot.

On first load, a module's tag is the pair (<modulename>,1).  On a reload,
because the tag already exists in the loaded module, the tag becomes
(<modulename>,<prior>+1).  That enables us to determine if modules have
actually reloaded or not.
"""

try:
    TEMPDIR  #type:ignore
    raise RuntimeError("Cannot reload test setup module")
except NameError:
    TEMPDIR = None

_TEMPFILES:set[str] = set()

_MODULE_DEFS:dict[str,dict[str,Any]] = dict()

_MODULE_TEMPLATE="""
import re
from math import nan
{imports}
{alldecl}
{publicfns}
{privatefns}
try: _tag = (_tag[0],_tag[1]+1)
except: _tag = ('{modulename}',1)
{postscript}
"""

#
# Source for public or private module functions.
#

def _functions(basename:str, public:bool, count:int):
    prefix = '' if public else '_'
    tail = 'public' if public else 'private'
    return '\n'.join(f"def {prefix}{basename}_{tail}{n}(): pass"
                     for n in range(1,count+1))
#
# Source for a module.
#

def _module_src(modulename:str, public_count:int=3, private_count:int=3,
                imports:list[str]=[], all:list[str]|None=None,
                postscript:str=""):

    basename = modulename.split('.')[-1]

    alldecl = ("__all__ = [" + ",".join(map(repr,all)) + "]"
              if all is not None else "")

    return _MODULE_TEMPLATE.format(
        imports='\n'.join(imports),
        alldecl=alldecl,
        publicfns=_functions(basename,True,public_count),
        privatefns=_functions(basename,False,private_count),
        modulename=modulename,
        postscript=textwrap.dedent(postscript))

#
# Create a module file.
#

def _create_module(modulename:str, **kwargs):

    assert TEMPDIR is not None

    assert modulename not in _MODULE_DEFS

    filename = TEMPDIR + "/" + modulename.replace('.','/') + ".py"

    assert filename not in _TEMPFILES

    with open(filename,"w") as f:
        _TEMPFILES.add(filename)
        _MODULE_DEFS[modulename] = kwargs
        f.write(_module_src(modulename,**kwargs))

#
# Create __init__.py for a package.
#

def _create_package(packagename:str):

    assert TEMPDIR is not None

    dirname = TEMPDIR + "/" + packagename.replace('.','/') + "/"
    filename = dirname + "__init__.py"

    assert filename not in _TEMPFILES

    with open(filename,"w") as f:
        _TEMPFILES.add(filename)
        f.write("")

#
# Create the temporary directory and file hierarchy.  Note the call to _setup()
# from the top level just after the definition of _cleanup().
#

def _setup():
    global TEMPDIR

    assert TEMPDIR is None
    TEMPDIR = tempfile.mkdtemp(prefix="liveimport-test-")

    atexit.register(_cleanup)

    assert TEMPDIR not in sys.path
    sys.path.append(TEMPDIR)

    os.mkdir(TEMPDIR + "/pkg")
    os.mkdir(TEMPDIR + "/pkg/subpkg")
    os.mkdir(TEMPDIR + "/altpkg")

    _create_package("pkg")
    _create_package("pkg.subpkg")
    _create_package("altpkg")

    _create_module("mod1")
    _create_module("mod2")
    _create_module("mod3",imports=["import pkg.subpkg.ssmod2"])
    _create_module("mod4",all=["mod4_public1","mod4_public2"])
    _create_module("mod5")
    _create_module("mod6",imports=["import A, pkg.smod1, altpkg.amod1"])

    _create_module("pkg.smod1")
    _create_module("pkg.smod2")
    _create_module("pkg.smod3")
    _create_module("pkg.smod4")
    _create_module("altpkg.amod1")

    _create_module("pkg.subpkg.ssmod1")
    _create_module("pkg.subpkg.ssmod2",imports=[
                   "from . ssmod1 import ssmod1_public1",
                   "from .. smod1 import smod1_public1",
                   "from .. import smod4"])

    _create_module("A",imports=["import C"])
    _create_module("B",imports=["import C; from D import nan; import G"])
    _create_module("C",imports=["import E, F"])
    _create_module("D",imports=["from F import *"])
    _create_module("E",imports=["import A as littlea"])
    _create_module("F")
    _create_module("G")

#
# Carefully remove temporary files and directories.
#

_KEEP_TEMPDIR = False

def _cleanup():
    global TEMPDIR, _TEMPFILES

    assert TEMPDIR is not None

    if _KEEP_TEMPDIR:
        return

    def require_safe(path):
        if "liveimport-test-" not in path:
            raise RuntimeError("UNSAFE REMOVAL: " + path)

    def safe_remove(path):
        require_safe(path)
        os.remove(path)

    def safe_rmdir(path):
        require_safe(path)
        os.rmdir(path)

    def safe_remove_pycache(parent):
        pycachedir = parent + "/__pycache__"
        if not os.path.exists(pycachedir): return
        for filename in os.listdir(pycachedir):
            assert type(filename) == str
            if filename.endswith(".pyc"):
                safe_remove(pycachedir + '/' + filename)
        safe_rmdir(pycachedir)

    for filename in _TEMPFILES:
        safe_remove(filename)

    for tail in ["/pkg/subpkg", "/pkg", "/altpkg", ""]:
        dir = TEMPDIR + tail
        safe_remove_pycache(dir)
        safe_rmdir(dir)

#
# Execute setup, including imports on which the tests will depend.  We need
# "#type: ignore" the imports because while they test files will exist when the
# imports execute, static code analyzers don't know that.
#

_setup()

import mod1 #type:ignore
from mod2 import mod2_public1, mod2_public2 as mod2_public2_alias #type:ignore
from mod3 import * #type:ignore
from mod4 import * #type:ignore
import mod5 as hide_mod5 #type:ignore
import mod6 #type:ignore
import pkg.smod1 #type:ignore
from pkg.smod2 import smod2_public1 #type:ignore
from pkg import smod3 #type:ignore
import pkg.smod4 as hide_smod4 #type:ignore
import pkg.subpkg.ssmod1 #type:ignore
import pkg.subpkg.ssmod2 #type:ignore
from pkg.subpkg.ssmod1 import ssmod1_public1 #type:ignore
import pkg.subpkg #type:ignore
import A, B, C, D, E, F, G #type:ignore
from altpkg import amod1 #type:ignore

#
# Given a module name, return its source file.
#

def _module_filename(modulename:str) -> str:
    module = sys.modules[modulename]
    filename = module.__file__
    assert filename is not None
    return filename

#
# Modify a module.
#

def modify_module(modulename:str, sleep:float=0.05, **kwargs):
    filename = _module_filename(modulename)
    olddef = _MODULE_DEFS[modulename]
    with open(filename,'w') as f:
        newdef = olddef.copy()
        newdef.update(kwargs)
        f.write(_module_src(modulename,**newdef))
    time.sleep(sleep)

#
# Restore a module to its original state.
#

def restore_module(modulename:str, sleep:float=0.05):
    filename = _module_filename(modulename)
    olddef = _MODULE_DEFS[modulename]
    with open(filename,'w') as f:
        f.write(_module_src(modulename,**olddef))
    time.sleep(sleep)

#
# Revise a module within a dynamic scope.  Example:
#
#       with revised_module("mod2",postscript="not valid python"):
#           ... make sure bad syntax is handled ...
#
# On scope exit, the module's original content is restored.
#

@contextmanager
def revised_module(modulename:str, sleep:float=0.05, **kwargs):
    modify_module(modulename,sleep,**kwargs)
    yield
    restore_module(modulename,sleep)

#
# Psuedo-delete a module's source file by renaming it.  (Renaming it means we
# can easily restore it with its original mtime.)
#

def delete_module(modulename:str):
    filename = _module_filename(modulename)
    if "liveimport-test-" not in filename:
        raise RuntimeError("UNSAFE RENAME: " + filename)
    os.rename(filename,filename + '.DELETED')

#
# Undelete module.
#

def undelete_module(modulename:str):
    filename = _module_filename(modulename)
    os.rename(filename + '.DELETED',filename)
    importlib.invalidate_caches()

#
# Delete a module source file within a dynamic scope.  Example:
#
#       with deleted_module("mod2"):
#           ... make sure removal is handled correctly ...
#
# On scope exit, the module source file is restored with its original mtime.
#

@contextmanager
def deleted_module(modulename:str):
    delete_module(modulename)
    yield
    undelete_module(modulename)

#
# Change a module's modification time to the current time, sleeping for the
# specified number of seconds afterward.
#

def touch_module(modulename:str, sleep:float=0.05):
    os.utime(_module_filename(modulename))
    time.sleep(sleep)

#
# For verifying reloads.  Typical use:
#
#       tag = get_tag("mod1")
#       ... do something that should cause mod1 to reload ...
#       expect_tag(next_tag(tag))
#
# Generated modules include a tag variable.  On first load, the tag is the pair
# (<modulename>,1).  On a reload after a rewrite or touch, because tag already
# exists in the loaded module, the tag becomes (<modulename>,<prior>+1).  That
# enables us to determine if modules are reloaded or not.
#

def get_tag(modulename:str):
    module = sys.modules.get(modulename,None)
    assert module is not None
    assert hasattr(module,'_tag')
    return getattr(module,'_tag')

def next_tag(tag):
    return (tag[0],tag[1]+1)

def expect_tag(modulename:str, tag):
    assert get_tag(modulename) == tag

#
# Verify sync() reload events.  While tags verify that modules are actually
# reloaded, reload_*() can be used to test the observer option of sync() as
# well as check reload order.
#

reload_list:list[ReloadEvent] = []

def reload_clear():
    reload_list.clear()

def reload_observe(event:ReloadEvent):
    reload_list.append(event)

def reload_expect(*expected:str):
    reports = [ event.module for event in reload_list ]
    if (len(reports) != len(expected) or
        any(reports[i] != expected[i] for i in range(0,len(expected)))):
        print("UNEXPECTED RELOAD REPORT(S)")
        print()
        print("Expected")
        for report in expected:
            print(f"    {report}")
        print()
        print("Actual")
        for report in reload_list:
            print(f"    {report}")
        print()
        raise RuntimeError("Unexpected reload report(s)s")


#
# Do not remove the temporary directories and files on exit.
#

def keep_tempdir():
    global _KEEP_TEMPDIR
    _KEEP_TEMPDIR = True


#
# Print a description of the test runtime environment.
#

def _pkg_version(name:str):
    return (importlib.metadata.version(name)
            if importlib.util.find_spec(name) else None)

def describe_environment() -> dict[str,str|None]:

    env_prompt = os.environ.get('VIRTUAL_ENV_PROMPT',None)
    ipython_version = _pkg_version("IPython")
    notebook_version = _pkg_version("notebook")

    print(f"Temporary directory is {TEMPDIR}")

    print(f"Python {sys.version}")

    print(f"Platform {sys.platform}")

    print("Global environment" if env_prompt is None else
          f"Virtual environment {env_prompt}")

    print("IPython", ipython_version)

    if notebook_version is not None:
        print("Notebook", notebook_version)
    else:
        print("Notebook not installed")

    print("LiveImport", liveimport.__version__)

    if _KEEP_TEMPDIR:
        print("Will keep temporary directory on exit")

    return {
        'python': f"{sys.version_info.major}.{sys.version_info.minor}",
        'ipython': ipython_version,
        'notebook': notebook_version,
    }

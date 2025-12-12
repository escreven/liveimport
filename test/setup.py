#
# Common support for testing liveimport in both scripts and notebooks.
#

from __future__ import annotations
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
from liveimport import _hash_state as hash_state
from liveimport import _is_tracked as is_tracked

__all__ = [
    "modify_module", "restore_module", "revised_module",
    "deleted_module",
    "touch_module",
    "is_registered_fn", "is_tracked", "hash_state",
    "get_tag", "next_tag", "expect_tag",
    "reload_list", "reload_clear", "reload_observe", "reload_expect",
    "root", "keep_tempdir", "describe_environment",
]


# =============================================================================
#                           HIERARCHY UNDER TEST
#
# When setup.py is imported, it creates a file hierarchy in a temporary
# directory used by the various tests, including the notebook.  Each module
# has source
#
#     import re
#     from math import nan
#     <imports>                             -- optional
#     <alldecl>                             -- optional
#     def <basename>_public<i>(): pass      -- i in [1..3] by default
#     def _<basename>_private<i>(): pass    -- i in [1..3] by default
#     try: _tag = (_tag[0],_tag[1]+1)
#     except: _tag = ('<basename>',1)
#     x='<basename>'
#     <postscript>                          -- optional
#
# <basename> is the part of a module's name past the last dot.  The contents of
# the optional sections are the values of _Node properties "imports", "all",
# and "postscript".  Properties "public_count" and "private_count" respectively
# determine the number of public and private functions.
#
# On first load, a module's tag is the pair ('<basename>',1).  On a reload,
# because the tag already exists in the loaded module, the tag becomes
# (<modulename>,<prior>+1).  That enables us to determine if modules have
# actually reloaded or not.
#
# See also setup_imports.py which contains import statements referencing the
# generated modules.  Test modules include "from setup_imports import *" to
# define names on which the tests depend.
# =============================================================================

def _hierarchy():

    def dir(name:str,*children:_Node):
        return _Node(kind='dir',name=name,children=children)

    def file(name:str,**properties):
        return _Node(kind='file',name=name,properties=properties)

    return dir("",
        file("mod1"),
        file("mod2"),
        file("mod3",imports=["import pkg.subpkg.ssmod2"]),
        file("mod4",all=["mod4_public1","mod4_public2"]),
        file("mod5"),
        file("mod6",imports=["import A, pkg.smod1, altpkg.amod1"]),
        dir("pkg",
            file("__init__"),
            file("smod1"),
            file("smod2"),
            file("smod3"),
            file("smod4"),
            dir("subpkg",
                file("__init__"),
                file("ssmod1"),
                file("ssmod2",imports=[
                        "from . ssmod1 import ssmod1_public1",
                        "from .. smod1 import smod1_public1",
                        "from .. import smod4"]))),
        dir("altpkg",
            file("__init__"),
            file("amod1")),
        file("A",imports=["import C"]),
        file("B",imports=["import C; from D import nan; import G"]),
        file("C",imports=["import E, F"]),
        file("D",imports=["from F import *"]),
        file("E",imports=["import A as littlea"]),
        file("F"),
        file("G"),
        dir("subdir1",
            file("mod7"),
            dir("nspkg",
                file("mod8"))),
        dir("subdir2",
            file("mod9"),
            dir("nspkg",
                file("mod10"))))

#
# setup.py must not be reloaded.
#

try:
    _ROOT  #type:ignore
    raise RuntimeError("Cannot reload test setup module")
except NameError:
    _ROOT = None

#
# Source for a module.
#

_MODULE_TEMPLATE="""
import re
from math import nan
{imports}
{alldecl}
{publicfns}
{privatefns}
try: _tag = (_tag[0],_tag[1]+1)
except: _tag = ('{modulename}',1)
x='{modulename}'
{postscript}
"""

def _functions(basename:str, public:bool, count:int):
    prefix = '' if public else '_'
    tail = 'public' if public else 'private'
    return '\n'.join(f"def {prefix}{basename}_{tail}{n}(): pass"
                     for n in range(1,count+1))

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
# The node tree is used to create the temporary sub-directories and files, but
# not destroy them.  Instead, we record created directories and files in
# _TEMPFILES and _TEMPDIRS so we can clean up even if tree creation fails.  We
# also maintain a modulename->_Node dictionary used to restore modules modified
# during a test to their initial condition.
#

_TEMPFILES = []
_TEMPDIRS = []

class _Node:
    __slots__ = "kind", "name", "properties", "children", "path"

    module_nodes:dict[str,_Node] = dict()

    def __init__(self, kind:str, name:str,
                 properties:dict[str,Any] = {},
                 children:tuple[_Node,...] = ()):
        if kind not in ('dir','file'):
            raise ValueError(f"Bad node kind {kind}")
        self.kind = kind
        self.name = name
        self.properties = properties
        self.children = children

    def create(self, parent_path:str, module_prefix=''):
        if self.kind == 'dir':
            self.path = parent_path + '/' + self.name
            if self.name != '':
                os.mkdir(self.path)
                _TEMPDIRS.append(self.path)
                module_prefix += self.name + '.'
            for child in self.children:
                child.create(self.path, module_prefix)
        else:
            self.path = parent_path + '/' + self.name + '.py'
            with open(self.path,"w") as f:
                if self.name == '__init__':
                    f.write("")
                else:
                    modulename = module_prefix + self.name
                    _Node.module_nodes[modulename] = self
                    f.write(_module_src(modulename,**self.properties))
                _TEMPFILES.append(self.path)


#
# Create the temporary directory and file hierarchy, and put them in sys.path.
# There is a call to _setup() from the top level just after the definition of
# _cleanup().
#

def _setup():
    global _ROOT

    assert _ROOT is None
    _ROOT = tempfile.mkdtemp(prefix="liveimport-test-")
    _TEMPDIRS.append(_ROOT)

    atexit.register(_cleanup)

    assert _ROOT not in sys.path
    sys.path.append(_ROOT)

    _hierarchy().create(_ROOT)

    subdir1_path = _ROOT + "/subdir1"
    subdir2_path = _ROOT + "/subdir2"

    sys.path = [ subdir1_path, subdir2_path ] + sys.path

#
# Carefully remove temporary files and directories.
#

_KEEP_TEMPDIR = False

def _cleanup():
    assert _ROOT is not None

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

    for subdir in reversed(_TEMPDIRS):
        safe_remove_pycache(subdir)
        safe_rmdir(subdir)

#
# Execute setup.
#

_setup()


# =============================================================================
#                                  MUTATION
# =============================================================================

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
    olddef = _Node.module_nodes[modulename].properties
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
    olddef = _Node.module_nodes[modulename].properties
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

def _delete_module(modulename:str):
    filename = _module_filename(modulename)
    if "liveimport-test-" not in filename:
        raise RuntimeError("UNSAFE RENAME: " + filename)
    os.rename(filename,filename + '.DELETED')

#
# Undelete module.
#

def _undelete_module(modulename:str):
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
    _delete_module(modulename)
    yield
    _undelete_module(modulename)

#
# Change a module's modification time to the current time, sleeping for the
# specified number of seconds afterward.
#

def touch_module(modulename:str, sleep:float=0.05):
    os.utime(_module_filename(modulename))
    time.sleep(sleep)



# =============================================================================
#                                EXAMINATION
# =============================================================================

#
# Many tests want to determine if an import is registered in the test module's
# global namespace.  Because that requires access to globals(), we provide a
# common implementation via a closure.
#

def is_registered_fn(module_globals:dict[str,Any]):
    def body(modulename:str, name:str|None=None, asname:str|None=None,
             namespace:dict[str,Any]|None=None):
        if namespace is None: namespace = module_globals
        return liveimport._is_registered(namespace,modulename,name,asname)
    return body

#
# For verifying reloads.  Typical use:
#
#       tag = get_tag("mod1")
#       ... do something that should cause mod1 to reload ...
#       expect_tag(next_tag(tag))
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


# =============================================================================
#                               ADMINISTRATION
# =============================================================================

#
# Return the root of the hierarchy.
#

def root():
    assert _ROOT
    return _ROOT

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

    print(f"Temporary directory is {_ROOT}")

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

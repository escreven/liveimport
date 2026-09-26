import sys
from typing import Any, TextIO
from ._core import _MODULE_TABLE, _NAMESPACE_TABLE

##############################################################################
#                              TEST AND DEBUG
##############################################################################

#
# Dump the module and namespace tables.
#

def _dump(file:TextIO|None=None):
    for name, info in sorted(_MODULE_TABLE.items()):
        print(f"Module {name} parent={info.parent}"
              f" mtime={info.mtime} file={info.file}"
              f" dependencies={info.dependencies}",
              f" attachedto={info.attachedto}", file=file)
    for id, info in sorted(_NAMESPACE_TABLE.items()):
        print(f"Namespace {id}",file=file)
        for record in info.journal.sequence:
            print(f"    {record}",file=file)

#
# Check registration.  The arguments describe an import statement.
#
# (modulename, None, None)   --> import <modulename>
# (modulename, None, asname) --> import <modulename> as <asname>
# (modulename, name, None)   --> from <modulename> import <name>
# (modulename, name, asname) --> from <modulename> import <name> as <asname>
# (modulemame, '*',  None)   --> from <modulename> import '*'
#
# _is_registered() returns true iff there is an import journal for the given
# namespace covering that statement.  Furthermore, if the statement is so
# covered, _is_registered() raises an AssertionError if
# _is_tracked(modulename,namespace) would return False.
#
#  TODO: THE BELOW IS NO LONGER TRUE.  VERIFY IT ISN'T REQUIRED FOR
# TESTING, AND REMOVE IF SO.
#
# Journal coalescing means the rebinds of some registrations can hide others.
# Example:
#
#       from mod1 import <name> as x
#       from mod2 import <name> as x
#
# _is_registered() returns True for the second import and False for the first.
# Not a problem unless imports conflict as above.
#

def _is_registered(namespace:dict[str,Any], modulename:str,
                   name:str|None=None, asname:str|None=None) -> bool:

    nsinfo = _NAMESPACE_TABLE.get(nsid := id(namespace))
    if nsinfo is None: return False

    assert name != '*' or asname is None

    if nsinfo.journal.covers(modulename,name,asname):
        assert (modulename in _MODULE_TABLE and
                nsid in _MODULE_TABLE[modulename].attachedto), (
            f"Module {modulename} for registration is not attached")
        return True
    else:
        return False

#
# Check tracking status.  Note the internal notion of "is tracked" is more
# generous than the external view.  Externally, "tracked" means in the module
# table and reachable by import chain from a module referenced by a registered
# import.
#

def _is_tracked(modulename:str, and_attached_to:dict[str,Any]|None=None):
    if not modulename in _MODULE_TABLE: return False
    return (and_attached_to is None or
            id(and_attached_to) in _MODULE_TABLE[modulename].attachedto)

#
# Hash state related to namespace.  Can be used to verify no change in state.
#

def _hash_state() -> int:
    hashcode = 0
    for nsid, nsinfo in _NAMESPACE_TABLE.items():
        hashcode = hash((hashcode,nsinfo.journal))
    for modulename, info in _MODULE_TABLE.items():
        hashcode = hash((hashcode,modulename,tuple(sorted(info.attachedto))))
    return hashcode

#
# Clear the module and namespace tables (for testing).
#

def _clear_all_state():
    _MODULE_TABLE.clear()
    _NAMESPACE_TABLE.clear()

#
# Verify (for testing and debugging)
#    + all attachedto namespaces are tracked
#    + all tracked namespaces have an attachment
#    + all name and '*' rebinds are for tracked modules
#    + all tracked modules are loaded
#    + all tracked module names are correct
#

def _verify():

    attachedto_union = set()

    for modulename, info in _MODULE_TABLE.items():
        assert modulename in sys.modules, (
            f"Tracked module {modulename} is not loaded")
        assert modulename == info.module.__name__, (
            f"Tracked module {modulename}'s module "
            f"has name {info.module.__name__}")
        for nsid in info.attachedto:
            assert nsid in _NAMESPACE_TABLE, (
                f"Module {modulename} attachedto {nsid} namespace missing")
            attachedto_union.add(nsid)

    for nsid, nsinfo in _NAMESPACE_TABLE.items():
        assert nsid in attachedto_union, (
            f"Namespace {nsid} has no attachments")
        for record in nsinfo.journal.sequence:
            assert record.modulename in _MODULE_TABLE, (
                f"Namespace {nsid} record {record} not for tracked module" )


#
# Reset all liveimport state by reloading all implementation modules.
#

def _reload_liveimport():
    from importlib import reload
    reload(sys.modules['liveimport._workspace'])
    reload(sys.modules['liveimport._importrec'])
    reload(sys.modules['liveimport._core'])
    reload(sys.modules['liveimport._nbi'])
    reload(sys.modules['liveimport._debug'])
    reload(sys.modules['liveimport'])

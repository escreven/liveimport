import sys
from typing import Any, TextIO
from ._core import _MODULE_TABLE, _NAMESPACE_TABLE, _rebind_str

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
        for rebind in info.journal:
            print(f"    {_rebind_str(rebind)}",file=file)

#
# Check registration.  The arguments describe an import statement.
# _is_registered() returns true iff there are rebinds consistent with that
# statement.
#
# (modulename, None, None)   --> import <modulename>
# (modulename, None, asname) --> import <modulename> as <asname>
# (modulename, name, None)   --> from <modulename> import <name>
# (modulename, name, asname) --> from <modulename> import <name> as <asname>
# (modulemame, '*',  None)   --> from <modulename> import '*'
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

    valmodname = modulename
    if name is None and asname is None:
        valmodname = modulename.split('.',1)[0]
        asname = valmodname
    elif asname is None and name != '*':
        asname = name

    if (valmodname,name,asname) in nsinfo.journal:
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
        hashcode = hash((hashcode,tuple(nsinfo.journal)))
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
        for rebind in nsinfo.journal:
            modulename, name, _ = rebind
            assert name is None or modulename in _MODULE_TABLE, (
                f"Namespace {nsid} rebind {rebind} not for tracked module" )

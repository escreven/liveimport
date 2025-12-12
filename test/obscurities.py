#
# Tests exercising parts of the liveimport implementation that are hard to
# reach without being very aware of the implementation or abusing the Python
# environment.
#

from importlib.util import spec_from_loader
import os
import sys
from IPython.core.error import UsageError
import io
from types import ModuleType
import liveimport
from liveimport._nbi import _LiveImportMagics
from setup import *
from setup_imports import *


def test_magic_missing_shell():
    """
    _LiveImportsMagic without a shell.
    """
    m = _LiveImportMagics()
    try:
        m.liveimport('','')
        error = None
    except RuntimeError as ex:
        error = ex
    assert error is not None and "No IPython shell" in str(error)


def test_extra_magic_arguments():
    """
    %%liveimport cell magic should throw UsageError given arguments past any
    options.  Testing this in notebook.ipynb isn't possible because notebook
    execution halts when UsageError is raised.
    """
    m = _LiveImportMagics()
    try:
        m.liveimport('--clear extra','')
        error = None
    except UsageError as ex:
        error = ex
    assert error is not None and "extra" in str(error)


def test_dump():
    """
    _dump() should at least mention relevant parts of registered import
    statements.
    """
    liveimport.register(globals(),"""
    import mod1
    from mod2 import mod2_public1, mod2_public2 as mod2_public2_alias
    """)
    textbuf = io.StringIO()
    liveimport._dump(textbuf)
    text = textbuf.getvalue()
    names = ("mod1","mod2","mod2_public1","mod2_public2", "mod2_public2_alias")
    for name in names:
        assert name in text, f"Did not mention {name}"


def test_disappearing_name():
    """
    If a module name somehow disappears, liveimport should raise a
    descriptive error.
    """
    liveimport.register(globals(),"""
    from mod2 import mod2_public1
    """, clear=True)

    mod2 = sys.modules['mod2']

    with revised_module("mod2",public_count=0):
        del mod2.mod2_public1  #type:ignore
        try:
            liveimport.sync()
            error = None
        except RuntimeError as ex:
            error = ex
        assert error is not None and "disappeared" in str(error)

    liveimport.sync()
    assert hasattr(mod2,'mod2_public1') #type:ignore


def test_no_spec():
    """
    register() should raise a ValueError if a module has no spec.
    """
    #
    # Create a specless module that is apparently imported.
    #
    module = ModuleType("untethered_no_spec")
    exec("def hello(): print('hello')", module.__dict__)
    sys.modules['untethered_no_spec'] = module
    globals()['untethered_no_spec'] = module

    try:
        liveimport.register(globals(),"import untethered_no_spec")
        error = None
    except ValueError as ex:
        error = ex
    assert error is not None and "no spec" in str(error)


def test_no_file():
    """
    register() should allow modules with no source file.
    """
    #
    # Create a module with a spec but no source file that is apparently
    # imported.
    #
    spec = spec_from_loader("untethered_no_file",None)
    module = ModuleType("untethered_no_file")
    module.__spec__ = spec
    exec("def hello(): print('hello')", module.__dict__)
    sys.modules['untethered_no_file'] = module
    globals()['untethered_no_file'] = module

    liveimport.register(globals(),"import untethered_no_file")


def test_unknown_extension():
    """
    register() should allow modules with unknown extensions.
    """
    #
    # Create a module with a spec but no source file that is apparently
    # imported.
    #
    spec = spec_from_loader("untethered_unknown_extension",None)
    assert spec is not None
    spec.has_location = True
    spec.origin = "untethered_unknown_extension.so"
    module = ModuleType("untethered_unknown_extension")
    module.__spec__ = spec
    exec("def hello(): print('hello')", module.__dict__)
    sys.modules['untethered_unknown_extension'] = module
    globals()['untethered_unknown_extension'] = module

    liveimport.register(globals(),"import untethered_unknown_extension")


def test_getmtime_failure():
    """
    sync() should raise the exception thrown by os.getmtime() when checking for
    modifications if the reason getmtime() fails is not because the file is
    missing.
    """
    def fake_getmtime(x):
        raise OSError()

    liveimport.register(globals(),"import mod1")

    try:
        liveimport._core.getmtime = fake_getmtime
        try:
            liveimport.sync()
            error = None
        except OSError as ex:
            error = ex
        assert error is not None
    finally:
        liveimport._core.getmtime = os.path.getmtime

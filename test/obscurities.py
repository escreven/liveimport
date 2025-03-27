#
# Tests exercising parts of the liveimport implementation that are hard to
# reach without using non-public APIs or abusing the Python environment.
#

from importlib.util import spec_from_loader
from IPython.core.error import UsageError
import io
from types import ModuleType
import liveimport
from liveimport import _LiveImportMagics, _Import
from common import *


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


def test_import_description():
    """
    Make sure _Import objects convert to the correct statements.
    """
    assert(str(_Import("foo",None,None)) == "import foo")
    assert(str(_Import("foo","bar",None)) == "import foo as bar")
    assert(str(_Import("foo",None,"*")) == "from foo import *")
    assert(str(_Import("foo",None,[("x","x"),("y","z")])) ==
           "from foo import x, y as z")


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
        assert name in text


def test_disappearing_symbol():
    """
    If a module symbol somehow disappears, liveimport should raise a
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
    register() should raise a ValueError if a module has no source file.
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

    try:
        liveimport.register(globals(),"import untethered_no_file")
        error = None
    except ValueError as ex:
        error = ex
    assert error is not None and "no source file" in str(error)

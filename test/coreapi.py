#
# Core API tests.
#

import liveimport
import common
from common import *


# globals() access means this can't be defined in setup
def is_registered(modulename:str, name:str|None=None, asname:str|None=None,
                  namespace:dict[str,Any]|None=None):
    if namespace is None: namespace = globals()
    return liveimport._is_registered(namespace,modulename,name,asname)


def test_empty():
    """
    Make sure registering zero import statements with and without clear=True is
    allowed, and make sure syncing with no registrations is allowed.
    """
    liveimport.register(globals(),"",clear=False)
    liveimport.register(globals(),"",clear=True)
    liveimport.sync()


def test_unloaded():
    """
    Registering an unloaded module should fail.
    """
    try:
        liveimport.register(globals(),"import does_not_exist")
        error = None
    except ValueError as ex:
        error = ex

    assert error is not None


def test_invalid_import():
    """
    Invalid import statements should throw a syntax error.
    """
    try:
        liveimport.register(globals(),"""
        from mod1 import public1 public2 public3
        """)
        error = None
    except SyntaxError as ex:
        error = ex

    assert error is not None


def test_non_import():
    """
    Invalid statements other than imports are not allowed for register().
    """
    try:
        liveimport.register(globals(),"""
        import mod1
        print("did it!")
        """)
        error = None
    except ValueError as ex:
        error = ex

    assert error is not None


def test_three_forms():
    """
    Register using the three different import statement forms.
    """
    liveimport.register(globals(),"""
    import mod1
    from mod2 import mod2_public1, mod2_public2 as mod2_public2_alias
    from mod3 import *
    from mod4 import *
    """)

    assert is_registered('mod1')
    assert is_registered('mod2','mod2_public1')
    assert is_registered('mod2','mod2_public2','mod2_public2_alias')
    assert is_registered('mod3','*')
    assert is_registered('mod4','*')
    assert not is_registered('mod1','*')
    assert not is_registered('mod1','mod1_public1')
    assert not is_registered('mod2','*')
    assert not is_registered('mod2','mod2_public2')
    assert not is_registered('mod2','mod2_public3')
    assert not is_registered('mod3','mod3_public1')
    assert not is_registered('mod4','mod4_public1')


def test_clear():
    """
    Verify clear=True
    """
    liveimport.register(globals(),"""
    import mod1
    from mod2 import mod2_public1, mod2_public2 as mod2_public2_alias
    from mod3 import *
    from mod4 import *
    """)

    liveimport.register(globals(),"""
    import mod1
    from mod2 import mod2_public1
    """, clear=True)

    assert is_registered('mod1')
    assert is_registered('mod2','mod2_public1')
    assert not is_registered('mod2','mod2_public2','mod2_public2_alias')
    assert not is_registered('mod3')
    assert not is_registered('mod4')

    mod1_tag = get_tag("mod1")
    mod2_tag = get_tag("mod2")
    mod3_tag = get_tag("mod3")
    mod4_tag = get_tag("mod4")

    touch_module("mod1")
    touch_module("mod2")
    touch_module("mod3")
    touch_module("mod4")

    liveimport.sync()

    expect_tag("mod1",next_tag(mod1_tag))
    expect_tag("mod2",next_tag(mod2_tag))
    expect_tag("mod3",mod3_tag)
    expect_tag("mod4",mod4_tag)


def test_undefined_name():
    """
    Registering an import statement with undefined module names should fail.
    """
    try:
        liveimport.register(globals(),"from mod1 import does_not_exist")
        error = None
    except ValueError as ex:
        error = ex

    assert error is not None


def test_general_reload():
    """
    All tracked modules should reload after update, rebind imported names,
    and not bind non-imported names.  Registered "from ... import *" should
    only bind public names including paying attention to __all__.
    """
    liveimport.register(globals(),"""
    import mod1
    from mod2 import mod2_public1, mod2_public2 as mod2_public2_alias
    from mod3 import *
    from mod4 import *
    """)

    mod1_tag = get_tag("mod1")
    mod2_tag = get_tag("mod2")
    mod3_tag = get_tag("mod3")
    mod4_tag = get_tag("mod4")

    touch_module("mod1")
    touch_module("mod2")
    touch_module("mod3")
    touch_module("mod4")

    expect_tag("mod1",mod1_tag)
    expect_tag("mod2",mod2_tag)
    expect_tag("mod3",mod3_tag)
    expect_tag("mod4",mod4_tag)

    liveimport.sync()

    expect_tag("mod1",next_tag(mod1_tag))
    expect_tag("mod2",next_tag(mod2_tag))
    expect_tag("mod3",next_tag(mod3_tag))
    expect_tag("mod4",next_tag(mod4_tag))

    # No global names for these
    mod2 = sys.modules['mod2']
    mod3 = sys.modules['mod3']
    mod4 = sys.modules['mod4']

    # What should and should not have changed
    assert common.mod2_public1 is not mod2.mod2_public1 #type:ignore
    assert mod2_public1 is mod2.mod2_public1 #type:ignore
    assert mod2_public2_alias is mod2.mod2_public2 #type:ignore
    assert mod3_public1 is mod3.mod3_public1 #type:ignore
    assert mod3_public2 is mod3.mod3_public2 #type:ignore
    assert mod3_public3 is mod3.mod3_public3 #type:ignore
    assert mod4_public1 is mod4.mod4_public1 #type:ignore
    assert mod4_public2 is mod4.mod4_public2 #type:ignore

    assert '_mod1_private1' not in globals()
    assert '_mod2_private1' not in globals()
    assert '_mod3_private1' not in globals()
    assert '_mod4_private1' not in globals()
    assert 'mod1_public1' not in globals()
    assert 'mod2_public2' not in globals()
    assert 'mod2_public3' not in globals()
    assert 'mod4_public3' not in globals()


def test_reload_one():
    """
    Updating mod2 should only lead to mod2 reloading.
    """
    liveimport.register(globals(),"""
    import mod1
    from mod2 import mod2_public1, mod2_public2 as mod2_public2_alias
    from mod3 import *
    from mod4 import *
    """)

    mod1_tag = get_tag("mod1")
    mod2_tag = get_tag("mod2")
    mod3_tag = get_tag("mod3")
    mod4_tag = get_tag("mod4")

    touch_module("mod2")

    liveimport.sync()

    expect_tag("mod1",mod1_tag)
    expect_tag("mod2",next_tag(mod2_tag))
    expect_tag("mod3",mod3_tag)
    expect_tag("mod4",mod4_tag)


def test_observer():
    """
    sync() should record module reloading
    """
    liveimport.register(globals(),"""
    import mod1
    from mod2 import mod2_public1, mod2_public2 as mod2_public2_alias
    from mod3 import *
    from mod4 import *
    """)

    touch_module("mod2")
    touch_module("mod3")

    reload_clear()

    liveimport.sync(observer=reload_observe)

    reload_expect("mod2",
                  "mod3")


def test_alignment():
    """
    Import statement indentation should be consistent, but not necessarily
    left-aligned.
    """
    liveimport.register(globals(),"""
    import mod1
    from mod3 import *
    from mod4 import *""")

    liveimport.register(globals(),"""import mod1
from mod3 import *
from mod4 import *""")

    liveimport.register(globals(),"""
import mod1
from mod3 import *
from mod4 import *""")

    liveimport.register(globals(),
        "import mod1; from mod3 import *; from mod4 import *")

    try:
        liveimport.register(globals(),"""import mod1
            from mod3 import *
            from mod4 import *""")
        error = None
    except SyntaxError as ex:
        error = ex

    assert error is not None


def test_register_syntax_error():
    """
    If the underlying module is made syntactically invalid, registering an
    import referencing that module should throw ModuleError with a SyntaxError
    cause.
    """
    with revised_module("mod1",postscript="not valid python"):
        try:
            liveimport.register(globals(),"import mod1")
            error = None
        except liveimport.ModuleError as ex:
            error = ex

        assert error is not None
        assert isinstance(error.__cause__,SyntaxError)
        assert not is_registered("mod1")


def test_sync_syntax_error():
    """
    If the underlying module is made syntactically invalid, sync() should throw
    ModuleError with a SyntaxError cause.  The invalid module should remain out
    of date until the error is fixed.  There should be no reload report.
    """
    liveimport.register(globals(),"import mod1")

    with revised_module("mod1",postscript="not valid python"):
        try:
            reload_clear()
            liveimport.sync(observer=reload_observe)
            error = None
        except liveimport.ModuleError as ex:
            error = ex

        assert error is not None
        assert 'Analysis of mod1' in str(error)
        assert isinstance(error.__cause__,SyntaxError)
        reload_expect()

        try:
            reload_clear()
            liveimport.sync(observer=reload_observe)
            error = None
        except liveimport.ModuleError as ex:
            error = ex

        assert error is not None
        assert isinstance(error.__cause__,SyntaxError)
        reload_expect()

    reload_clear()
    liveimport.sync(observer=reload_observe)
    reload_expect("mod1")


def test_load_exception():
    """
    If a module being reloaded raises an exception, sync() should throw a
    ModuleError with the module's exception as the cause.  The invalid module
    should remain out of date until the error is fixed.  The failure should be
    reported as an exception, and there should be no reload report.
    """
    liveimport.register(globals(),"import mod1")

    with revised_module("mod1",postscript="raise RuntimeError('expected')"):
        try:
            reload_clear()
            liveimport.sync(observer=reload_observe)
            error = None
        except liveimport.ModuleError as ex:
            error = ex

        assert error is not None
        assert isinstance(error.__cause__,RuntimeError)
        reload_expect()

        try:
            reload_clear()
            liveimport.sync(observer=reload_observe)
            error = None
        except liveimport.ModuleError as ex:
            error = ex

        assert error is not None
        assert isinstance(error.__cause__,RuntimeError)
        reload_expect()

    reload_clear()
    liveimport.sync(observer=reload_observe)
    reload_expect("mod1")


def test_dropped_name():
    """
    If we drop a name from a module, even a name that is referenced in a
    registered import statement, there should be no sync issue.
    """

    liveimport.register(globals(),
    "from mod2 import mod2_public2 as mod2_public2_alias")

    mod2_public2_alias = sys.modules['mod2'].mod2_public2 #type:ignore

    with revised_module("mod2",public_count=0):
        assert is_registered("mod2","mod2_public2","mod2_public2_alias")
        old_value = mod2_public2_alias
        liveimport.sync()
        assert mod2_public2_alias is old_value


def test_additive():
    """
    Verify registrations are additive and idempotent.
    """
    liveimport.register(globals(),"import mod1")
    assert is_registered("mod1")
    assert not is_registered("mod2")

    liveimport.register(globals(),"from mod2 import mod2_public1")
    assert is_registered("mod1")
    assert is_registered("mod2")
    assert is_registered("mod2","mod2_public1")
    assert not is_registered("mod2","mod2_public2")
    assert not is_registered("mod2","mod2_public2","mod2_public2_alias")

    liveimport.register(globals(),"from mod2 import mod2_public2 as mod2_public2_alias")
    assert is_registered("mod1")
    assert is_registered("mod2")
    assert is_registered("mod2","mod2_public1")
    assert not is_registered("mod2","mod2_public2")
    assert is_registered("mod2","mod2_public2","mod2_public2_alias")

    liveimport.register(globals(),"from mod3 import mod3_public1")
    assert is_registered("mod3")
    assert is_registered("mod3","mod3_public1")
    assert not is_registered("mod3","*")

    liveimport.register(globals(),"from mod3 import *")
    assert is_registered("mod3")
    assert is_registered("mod3","mod3_public1")
    assert is_registered("mod3","*")

    liveimport.register(globals(),"import mod1")
    liveimport.register(globals(),"from mod2 import mod2_public1")
    liveimport.register(globals(),"from mod2 import mod2_public2 as mod2_public2_alias")
    liveimport.register(globals(),"from mod3 import mod3_public1")
    liveimport.register(globals(),"from mod3 import *")
    assert is_registered("mod1")
    assert is_registered("mod2")
    assert is_registered("mod2","mod2_public1")
    assert not is_registered("mod2","mod2_public2")
    assert is_registered("mod2","mod2_public2","mod2_public2_alias")
    assert is_registered("mod3")
    assert is_registered("mod3","mod3_public1")
    assert is_registered("mod3","*")


def test_package_module_registration():
    """
    Registration of modules in packages.
    """
    liveimport.register(globals(),"""
    import pkg.smod1
    from pkg.smod2 import smod2_public1
    from pkg.smod3 import *
    """)

    assert is_registered("pkg.smod1")
    assert is_registered("pkg.smod2","smod2_public1")
    assert is_registered("pkg.smod3","*")


def test_package_module_reload():
    """
    Verify syncing of updated modules in packages.
    """
    liveimport.register(globals(),"""
    import pkg.smod1
    from pkg.smod2 import smod2_public1
    from pkg.smod3 import *
    """)

    smod1_tag = get_tag("pkg.smod1")
    smod2_tag = get_tag("pkg.smod2")
    smod3_tag = get_tag("pkg.smod3")

    touch_module("pkg.smod1")
    touch_module("pkg.smod2")
    touch_module("pkg.smod3")

    liveimport.sync()

    expect_tag("pkg.smod1",next_tag(smod1_tag))
    expect_tag("pkg.smod2",next_tag(smod2_tag))
    expect_tag("pkg.smod3",next_tag(smod3_tag))


def test_package_init_registration():
    """
    Registration of a package itself.
    """
    liveimport.register(globals(),"import pkg.subpkg")
    assert is_registered("pkg.subpkg")


def test_package_init_reload():
    """
    Modifying __init__.py should cause the package to reload.  Note that we
    don't put tags in __init__.py, so we verify with reload events.
    """
    liveimport.register(globals(),"import pkg.subpkg")

    touch_module("pkg.subpkg")

    reload_clear()
    liveimport.sync(observer=reload_observe)
    reload_expect("pkg.subpkg")


def test_implicit_package_register():
    """
    Statements of the form "from pkg import smod3" should result in both
    pkg and pkg.submod3 being tracked, while "import pkg.smod1" should
    only track pkg.smod1
    """
    liveimport.register(globals(),"import pkg.smod1")

    assert not is_registered("pkg")
    assert is_registered("pkg.smod1")

    liveimport.register(globals(),"from pkg import smod3")
    assert is_registered("pkg")
    assert is_registered("pkg.smod3")


def test_auto_sync_outside_nb():
    """
    Calling ``auto_sync`` outside a notebook should be a no-op.
    """
    liveimport.auto_sync(enabled=False, grace=3.1, report=False)


def test_hidden_cell_magic_outside_nb():
    """
    Calling ``hidden_cell_magic`` outside a notebook should be a no-op.
    """
    liveimport.hidden_cell_magic(enabled=True)


def test_two_namespaces():
    """
    Simultaneous registrations in two namespaces should work and not interfere
    with each other on reload.
    """
    #
    # Fake namespaces for imports we will register.
    #
    ns1 = { 'mod1': mod1,
            'mod2_public1': mod2_public1,
            'mod2_public2_alias': mod2_public2_alias }

    ns2 = { 'mod1': mod1,
            'mod2_public1': mod2_public1,
            'mod3_public1': mod3_public1 }  #type: ignore

    liveimport.register(ns1,"""
    import mod1
    from mod2 import mod2_public1, mod2_public2 as mod2_public2_alias
    """)

    liveimport.register(ns2,"""
    import mod1
    from mod2 import mod2_public1
    from mod3 import mod3_public1
    """)

    mod1_tag = get_tag("mod1")
    mod2_tag = get_tag("mod2")
    mod3_tag = get_tag("mod3")

    touch_module("mod1")
    touch_module("mod2")
    touch_module("mod3")

    liveimport.sync()

    expect_tag("mod1",next_tag(mod1_tag))
    expect_tag("mod2",next_tag(mod2_tag))
    expect_tag("mod3",next_tag(mod3_tag))

    # No global names for these
    mod2 = sys.modules['mod2']
    mod3 = sys.modules['mod3']

    # Should have changed
    assert ns1['mod1'] is mod1
    assert ns1['mod2_public1'] is mod2.mod2_public1
    assert ns1['mod2_public2_alias'] is mod2.mod2_public2
    assert ns2['mod1'] is mod1
    assert ns2['mod2_public1'] is mod2.mod2_public1
    assert ns2['mod3_public1'] is mod3.mod3_public1

    # Should be no extraneous bindings.
    assert 'mod3_public1' not in ns1
    assert 'mod2_public2_alias' not in ns2


def test_clear_two_namespaces():
    """
    clear=True should clear imports for the specified namespace and only the
    specified namespace.
    """
    #
    # Fake namespaces for imports we will register.
    #
    ns1 = { 'mod1': mod1,
            'mod2_public1': mod2_public1,
            'mod2_public2_alias': mod2_public2_alias,
            'mod4_public1': mod4_public1 }  #type: ignore

    ns1_copy = ns1.copy()

    ns2 = { 'mod2_public1': mod2_public1,
            'mod3_public1': mod3_public1 }  #type: ignore

    liveimport.register(ns1,"""
    import mod1
    from mod2 import mod2_public1, mod2_public2 as mod2_public2_alias
    from mod4 import mod4_public1
    """)

    liveimport.register(ns2,"""
    from mod2 import mod2_public1
    from mod3 import mod3_public1
    """)

    assert is_registered('mod1',namespace=ns1)
    assert is_registered('mod2','mod2_public1',namespace=ns1)
    assert is_registered('mod2','mod2_public2','mod2_public2_alias',ns1)
    assert is_registered('mod4',namespace=ns1)

    assert is_registered('mod2','mod2_public1',namespace=ns2)
    assert is_registered('mod3','mod3_public1',namespace=ns2)

    liveimport.register(ns1,"",clear=True)

    assert not is_registered('mod1',namespace=ns1)
    assert not is_registered('mod2','mod2_public1',namespace=ns1)
    assert not is_registered('mod2','mod2_public2','mod2_public2_alias',ns1)
    assert not is_registered('mod4',namespace=ns1)

    assert is_registered('mod2','mod2_public1',namespace=ns2)
    assert is_registered('mod3','mod3_public1',namespace=ns2)

    mod1_tag = get_tag("mod1")
    mod2_tag = get_tag("mod2")
    mod3_tag = get_tag("mod3")
    mod4_tag = get_tag("mod4")

    touch_module("mod1")
    touch_module("mod2")
    touch_module("mod3")
    touch_module("mod4")

    liveimport.sync()

    expect_tag("mod1",mod1_tag)
    expect_tag("mod2",next_tag(mod2_tag))
    expect_tag("mod3",next_tag(mod3_tag))
    expect_tag("mod4",mod4_tag)

    # No global names for these
    mod2 = sys.modules['mod2']
    mod3 = sys.modules['mod3']

    # Should not have changed
    assert ns1 == ns1_copy

    # Should have changed
    assert ns2['mod2_public1'] is mod2.mod2_public1
    assert ns2['mod3_public1'] is mod3.mod3_public1

    liveimport.register(ns2,"",clear=True)
    assert not is_registered('mod2','mod2_public1',namespace=ns2)
    assert not is_registered('mod3','mod3_public1',namespace=ns2)

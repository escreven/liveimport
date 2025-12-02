#
# Workspace tests.
#

import liveimport
from common import *


# globals() access means this can't be defined in setup
def is_registered(modulename:str, name:str|None=None, asname:str|None=None,
                  namespace:dict[str,Any]|None=None):
    if namespace is None: namespace = globals()
    return liveimport._is_registered(namespace,modulename,name,asname)


def test_direct_deleted():
    """
    Deleting a directly imported module should not cause sync() to fail; it
    should simply mean the module does not reload if modified before delete.  If
    it is restored with an updated mtime, it should reload.
    """
    liveimport.register(globals(),"""
    import mod1
    from mod2 import mod2_public1
    """)

    assert is_registered("mod1")
    assert is_registered("mod2","mod2_public1")

    mod1_tag = get_tag("mod1")
    mod2_tag = get_tag("mod2")

    touch_module("mod1")
    touch_module("mod2")

    with deleted_module("mod1"):
        assert is_registered("mod1")

        reload_clear()
        liveimport.sync(observer=reload_observe)
        reload_expect("mod2")

        expect_tag("mod1",mod1_tag)
        expect_tag("mod2",next_tag(mod2_tag))

    reload_clear()
    liveimport.sync(observer=reload_observe)
    reload_expect("mod1")

    expect_tag("mod1",next_tag(mod1_tag))
    expect_tag("mod2",next_tag(mod2_tag))


def test_indirect_deleted():
    """
    Deleting an indirectly imported module should not cause sync() to fail; it
    should simply mean the module does not reload if modified before delete.
    If it is restored with an updated mtime, it should reload, triggering
    reloads of dependent modules.
    """
    liveimport.register(globals(),"""
    import mod6
    """)

    assert is_registered("mod6")
    assert is_tracked("A")

    mod6_tag = get_tag("mod6")
    A_tag    = get_tag("A")

    touch_module("A")

    with deleted_module("A"):
        assert is_tracked("A")

        reload_clear()
        liveimport.sync(observer=reload_observe)
        reload_expect()

        expect_tag("mod6", mod6_tag)
        expect_tag("A"   , A_tag)

    reload_clear()
    liveimport.sync(observer=reload_observe)
    reload_expect("A","mod6")

    expect_tag("mod6", next_tag(mod6_tag))
    expect_tag("A"   , next_tag(A_tag))


def test_thru_deleted():
    """
    Deleting an indirectly imported module should not cause sync() to fail; it
    should mean that it should stop being a link in a reload chain.  If it is
    restored, through dependencies to updated modules should cause reloads.
    """
    liveimport.register(globals(),"""
    import mod6
    """)

    assert is_registered("mod6")
    assert is_tracked("A")
    assert is_tracked("C")

    mod6_tag = get_tag("mod6")
    A_tag    = get_tag("A")
    C_tag    = get_tag("C")

    touch_module("C")

    with deleted_module("A"):
        assert is_tracked("A")
        assert is_tracked("C")

        reload_clear()
        liveimport.sync(observer=reload_observe)
        reload_expect()

        expect_tag("mod6", mod6_tag)
        expect_tag("A"   , A_tag)
        expect_tag("C"   , C_tag)

    reload_clear()
    liveimport.sync(observer=reload_observe)
    reload_expect("C","A","mod6")

    expect_tag("mod6", next_tag(mod6_tag))
    expect_tag("A"   , next_tag(A_tag))
    expect_tag("C"   , next_tag(C_tag))


def test_delete_before_register():
    """
    Registering a module with a source file deleted between being imported
    should be allowed, and if the source file is restored, a sync should reload
    it immediately.
    """
    with deleted_module("mod1"):

        liveimport.register(globals(),"""
        import mod1
        from mod2 import mod2_public1
        """)

        assert is_registered("mod1")
        assert is_registered("mod2","mod2_public1")

        mod1_tag = get_tag("mod1")
        mod2_tag = get_tag("mod2")

        touch_module("mod2")

        reload_clear()
        liveimport.sync(observer=reload_observe)
        reload_expect("mod2")

        expect_tag("mod1",mod1_tag)
        expect_tag("mod2",next_tag(mod2_tag))

    reload_clear()
    liveimport.sync(observer=reload_observe)
    reload_expect("mod1")

    # Remember that tags are bumped on reload, not by touch.
    expect_tag("mod1",next_tag(mod1_tag))

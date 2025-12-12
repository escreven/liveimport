#
# Workspace tests.
#

import liveimport
from setup import *
from setup_imports import *


is_registered = is_registered_fn(globals())


#
# _test() is used to test how workspace configurations affect which indirectly
# imported modules cause reloads.  _test() registers "import mod6" and nothing
# else.  Module mod6 imports A, pkg.smod1 and altpkg.amod1.  The public tests
# then choose a worksapce configuration and specify which of A, smod1, and
# amod1 are in the workspace.
#

def _test(directories:list[str],
          includes_A=True,
          includes_smod1=True,
          includes_amod1=True):

    liveimport.workspace(*directories)
    liveimport.register(globals(),"import mod6")

    assert is_registered("mod6")
    assert includes_A     == is_tracked("A")
    assert includes_smod1 == is_tracked("pkg.smod1")
    assert includes_amod1 == is_tracked("altpkg.amod1")

    A_tag     = get_tag("A")
    smod1_tag = get_tag("pkg.smod1")
    amod1_tag = get_tag("altpkg.amod1")

    touch_module("A")
    touch_module("pkg.smod1")
    touch_module("altpkg.amod1")

    expected_list = []
    if includes_A    : expected_list.append('A')
    if includes_smod1: expected_list.append('pkg.smod1')
    if includes_amod1: expected_list.append('altpkg.amod1')
    if len(expected_list) > 0: expected_list.append('mod6')

    reload_clear()
    liveimport.sync(observer=reload_observe)
    reload_expect(*expected_list)

    next_A_tag     = next_tag(A_tag    ) if includes_A     else A_tag
    next_smod1_tag = next_tag(smod1_tag) if includes_smod1 else smod1_tag
    next_amod1_tag = next_tag(amod1_tag) if includes_amod1 else amod1_tag

    expect_tag("A",            next_A_tag    )
    expect_tag("pkg.smod1",    next_smod1_tag)
    expect_tag("altpkg.amod1", next_amod1_tag)


def test_baseline():
    """
    The default workspace includes the test file hierarchy, so touching all
    indirectly imported modules should be tracked.
    """
    _test([root()],
          includes_A=True,
          includes_smod1=True,
          includes_amod1=True)


def test_two_subdirs():
    """
    A workspace consisting of the pkg and altpkg dirs should exclude module A.
    """
    _test([root()+"/pkg",root()+"/altpkg"],
          includes_A=False,
          includes_smod1=True,
          includes_amod1=True)


def test_one_subdir():
    """
    A workspace consisting of the pkg dir only should exclude module A and
    altpkg.amod1.
    """
    _test([root()+"/pkg"],
          includes_A=False,
          includes_smod1=True,
          includes_amod1=False)

def test_no_dirs():
    """
    An empty workspace should exclude module A, pkg.smod1, and altpkg.amod1.
    """
    _test([],
          includes_A=False,
          includes_smod1=False,
          includes_amod1=False)


def test_dir_does_not_exist():
    """
    Workspace directories must exist.
    """
    try:
        liveimport.workspace(root()+"/dir_does_not_exist")
        error = None
    except ValueError as ex:
        error = ex

    assert error is not None


def test_dir_is_not_a_dir():
    """
    Workspace directories must actually be directories.
    """
    try:
        liveimport.workspace(root()+"/mod1.py")
        error = None
    except ValueError as ex:
        error = ex

    assert error is not None


def test_direct_imports_unaffected():
    """
    Even with an empty workspace, direct imports should work as always.
    """
    liveimport.workspace()
    liveimport.register(globals(),"import mod6")
    liveimport.register(globals(),"import A")
    liveimport.register(globals(),"import pkg.smod1")

    assert is_registered("mod6")
    assert is_registered("A")
    assert is_registered("pkg.smod1")

    A_tag     = get_tag("A")
    smod1_tag = get_tag("pkg.smod1")

    touch_module("A")
    touch_module("pkg.smod1")

    expected_list = []
    expected_list.append('A')
    expected_list.append('pkg.smod1')
    expected_list.append('mod6')

    reload_clear()
    liveimport.sync(observer=reload_observe)
    reload_expect(*expected_list)

    next_A_tag     = next_tag(A_tag    )
    next_smod1_tag = next_tag(smod1_tag)

    expect_tag("A",            next_A_tag    )
    expect_tag("pkg.smod1",    next_smod1_tag)
#
# Workspace tests.
#

from os import PathLike
import os
from pathlib import Path

import liveimport
from setup import *
from setup_imports import *


is_registered = is_registered_fn(globals())


#
# _test() is used to test how workspace configurations affect which indirectly
# imported modules cause reloads.  _test() registers "import mod6" and nothing
# else.  Module mod6 imports A, pkg.smod1 and altpkg.amod1.  The public tests
# then choose a workspace configuration and specify which of A, smod1, and
# amod1 are in the workspace.  _verify() is the verification part of _test()
# used by some tests which don't use the _test() preamble.
#

def _test(directories:list[str|PathLike],
          includes_A=True,
          includes_smod1=True,
          includes_amod1=True,
          extend=False):

    liveimport.workspace(*directories,extend=extend)
    liveimport.register(globals(),"import mod6", clear=True)

    assert is_registered("mod6")
    assert includes_A     == is_tracked("A")
    assert includes_smod1 == is_tracked("pkg.smod1")
    assert includes_amod1 == is_tracked("altpkg.amod1")

    _verify(includes_A, includes_smod1, includes_amod1)

def _verify(includes_A=True,
            includes_smod1=True,
            includes_amod1=True,
            touch_mod6=False):

    A_tag     = get_tag("A")
    smod1_tag = get_tag("pkg.smod1")
    amod1_tag = get_tag("altpkg.amod1")

    touch_module("A")
    touch_module("pkg.smod1")
    touch_module("altpkg.amod1")
    if touch_mod6: touch_module("mod6")

    expected_list = []
    if includes_A    : expected_list.append('A')
    if includes_smod1: expected_list.append('pkg.smod1')
    if includes_amod1: expected_list.append('altpkg.amod1')
    if len(expected_list) > 0 or touch_mod6:
        expected_list.append('mod6')

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


def test_extend():
    """
    The extend option should incrementally augment the workspace.
    """
    _test([],
          includes_A=False,
          includes_smod1=False,
          includes_amod1=False)

    workspace_expect()

    _test([root()+"/pkg"],extend=True,
          includes_A=False,
          includes_smod1=True,
          includes_amod1=False)

    workspace_expect(root()+"/pkg")

    _test([root()+"/altpkg"],extend=True,
          includes_A=False,
          includes_smod1=True,
          includes_amod1=True)

    workspace_expect(root()+"/pkg", root()+"/altpkg")

    _test([],extend=True,
          includes_A=False,
          includes_smod1=True,
          includes_amod1=True)

    workspace_expect(root()+"/pkg", root()+"/altpkg")


def test_unique():
    """
    Workspace entries should be unique.
    """
    dot = os.getcwd()
    pkg = root() + "/pkg"
    altpkg = root() + "/altpkg"
    subdir1 = root() + "/subdir1"
    subdir2 = root() + "/subdir2"

    liveimport.workspace(dot,pkg,pkg,altpkg,altpkg,altpkg)

    workspace_expect(dot,pkg,altpkg)

    liveimport.workspace(dot,subdir1,subdir1,subdir2,subdir2,subdir2,
                         extend=True)

    workspace_expect(dot,pkg,altpkg,subdir1,subdir2)


def test_dir_does_not_exist():
    """
    Workspace directories must exist.  workspace() exceptions should leave the
    workspace unchanged.
    """
    snapshot = workspace_snapshot()
    try:
        liveimport.workspace(
            root()+"/pkg",
            root()+"/dir_does_not_exist",
            root()+"/altpkg")
        error = None
    except ValueError as ex:
        error = ex

    assert error is not None
    workspace_expect(*snapshot)

    snapshot = workspace_snapshot()
    try:
        liveimport.workspace(
            root()+"/pkg",
            root()+"/dir_does_not_exist",
            root()+"/altpkg", extend=True)
        error = None
    except ValueError as ex:
        error = ex

    assert error is not None
    workspace_expect(*snapshot)


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

    _verify(includes_A=True,
            includes_smod1=True,
            includes_amod1=False)


def test_no_longer_tracked():
    """
    If a module tracked as a dependency falls out of the workspace after a
    redefinition, it should no longer reload.
    """

    liveimport.register(globals(),"import mod6", clear=True)

    assert is_registered("mod6")
    assert is_tracked("A")
    assert is_tracked("pkg.smod1")
    assert is_tracked("altpkg.amod1")

    #
    # With the entire hierarchy under test as the workspace.
    #

    _verify(includes_A=True,
            includes_smod1=True,
            includes_amod1=True)

    #
    # Now shrinking the workspace to root()/pkg.
    #

    liveimport.workspace(root()+"/pkg")

    _verify(includes_A=False,
            includes_smod1=True,
            includes_amod1=False)

    #
    # Now with an empty workspace.
    #

    liveimport.workspace()

    _verify(includes_A=False,
            includes_smod1=False,
            includes_amod1=False,
            touch_mod6=True)

    #
    # Back to the full hierarchy under test.
    #

    liveimport.workspace(root())

    _verify(includes_A=True,
            includes_smod1=True,
            includes_amod1=True)


def test_mid_dotdot():
    """
    Workspace directory "<name>/.." segments should be collapsed in the middle
    of a path.
    """
    _test([root()+"/pkg/../altpkg"],
          includes_A=False,
          includes_smod1=False,
          includes_amod1=True)


def test_end_dotdot():
    """
    Workspace directory "<name>/.." segments should be collapsed at end of a
    path.
    """
    _test([root()+"/pkg/.."],
          includes_A=True,
          includes_smod1=True,
          includes_amod1=True)


def test_path_subdirs():
    """
    Workspace directories can be specified as Path objects.
    """
    _test([Path(root()+"/pkg"),Path(root()+"/altpkg")],
          includes_A=False,
          includes_smod1=True,
          includes_amod1=True)
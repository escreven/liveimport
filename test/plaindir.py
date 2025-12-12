#
# Test namespace package support.
#

import liveimport
from setup import *
from setup_imports import *


is_registered = is_registered_fn(globals())


def test_single_dir():
    """
    Importing a standalone directory lacking an __init__.py is allowed.
    """
    liveimport.register(globals(),"import subdir1")
    assert is_registered("subdir1")


def test_from_single_dir():
    """
    Importing from a standalone directory lacking an __init__.py is allowed.
    """
    liveimport.register(globals(),"""
    from subdir1 import mod7
    from subdir2.mod9 import mod9_public1
    """)

    assert is_registered("subdir1","mod7")
    assert is_registered("subdir2.mod9","mod9_public1")

    mod7_tag = get_tag("subdir1.mod7")
    mod9_tag = get_tag("subdir2.mod9")

    touch_module("subdir1.mod7")
    touch_module("subdir2.mod9")

    liveimport.sync()

    expect_tag("subdir1.mod7",next_tag(mod7_tag))
    expect_tag("subdir2.mod9",next_tag(mod9_tag))


def test_multi_dir():
    """
    Importing a multi-directory namespace package is allowed.
    """
    liveimport.register(globals(),"import nspkg")
    assert is_registered("nspkg")


def test_from_multi_dir():
    """
    Importing from a a multi-directory namespace package is allowed.
    """
    liveimport.register(globals(),"""
    from nspkg import mod8
    from nspkg.mod10 import mod10_public1
    """)

    assert is_registered("nspkg","mod8")
    assert is_registered("nspkg.mod10","mod10_public1")

    mod8_tag = get_tag("nspkg.mod8")
    mod10_tag = get_tag("nspkg.mod10")

    touch_module("nspkg.mod8")
    touch_module("nspkg.mod10")

    liveimport.sync()

    expect_tag("nspkg.mod8",next_tag(mod8_tag))
    expect_tag("nspkg.mod10",next_tag(mod10_tag))

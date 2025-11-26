#
# Tests of register() requirements that detect non-executed import statements.
#

import liveimport
import re
from common import *


def expect_register_fail(importstmt:str, pattern:str):

    try:
        liveimport.register(globals(),importstmt)
        error = None
    except Exception as ex:
        error = ex

    if error is None:
        raise RuntimeError("FAILED: expected register() to raise exception")

    pattern += ".*" + importstmt
    if re.match(pattern,str(error)) is None:
        raise RuntimeError("FAILED: register() raised exception as " +
                           "expected, but with wrong message: " + str(error))


def test_not_loaded():
    """
    Imports of an unloaded (not imported) module.
    """
    expect_register_fail("import modX",
                         "Module modX not loaded")

    expect_register_fail("import modX as notexists",
                         "Module modX not loaded")

    expect_register_fail("from modX import notexists",
                         "Module modX not loaded")


def test_no_name():
    """
    Imports referencing undefined names.
    """
    expect_register_fail("import mod5",
                         "No name mod5 in namespace")

    expect_register_fail("import mod5 as notexists",
                         "No name notexists in namespace")

    expect_register_fail("from mod5 import notexists",
                         "No name notexists in mod5")

    expect_register_fail("from mod5 import notexists as x",
                         "No name notexists in mod5")

    expect_register_fail("from mod5 import mod5_public1 as notexists",
                         "No name notexists in namespace")


def test_not_loaded_in_package():
    """
    Imports of unloaded (not imported) module in a package.
    """
    expect_register_fail("import pkg.submodX",
                         "Module pkg.submodX not loaded")

    expect_register_fail("import pkg.submodX as notexists",
                         "Module pkg.submodX not loaded")

    expect_register_fail("from pkg.submodX import notexists",
                         "Module pkg.submodX not loaded")


def test_no_name_in_package():
    """
    Imports referencing undefined names.
    """
    expect_register_fail("import altpkg.amod1",
                         "No name altpkg in namespace")

    expect_register_fail("import pkg.smod4 as notexists",
                         "No name notexists in namespace")

    expect_register_fail("from pkg.smod4 import notexists",
                         "No name notexists in pkg.smod4")

    expect_register_fail("from pkg.smod4 import notexists as x",
                         "No name notexists in pkg.smod4")

    expect_register_fail("from pkg.smod4 import smod4_public1 as notexists",
                         "No name notexists in namespace")

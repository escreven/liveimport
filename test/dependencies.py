#
# Tests of dependency detection and reload ordering.
#

import re
import time
import liveimport
from setup import *
from setup_imports import *

#
# The tests depend on the following dependency graph created in setup.
#
#     A -> C
#     B -> C, D, G
#     C -> E, F
#     D -> F
#     E -> A
#     F -> [none]
#     G -> [none]
#
# There are two modes of testing: direct=True, which registers an import of all
# modules in alphabetical order, and direct=False, which only registers "import
# B".
#
# There is a cycle A->C->E->A.  With direct mode, because imports from E are
# registered after those from A and C, arc E->A should be effectively ignored.
# With indirect mode (we register only "import B"), the arc from A->C should be
# ignored.
#
# The primary thing we test in this module are which modules are reloaded and
# reload order, as reported through the recorder option of sync().  That is
# implemented by test functions dynamically created as lambdas calling _test()
# by _define().  _define() argument touch is whitespace separated list of
# modules to modify.  Argument expect is whitespace separated list of modules
# for which reload is expected in the order given.
#


def _test(direct:bool, touch_list:list[str], expect_list:list[str]):

    liveimport.register(globals(),
        "import A, B, C, D, E, F, G" if direct else
        "import B")

    for modulename in touch_list:
        touch_module(modulename,0)

    time.sleep(0.1)

    reload_clear()
    liveimport.sync(observer=reload_observe)
    reload_expect(*expect_list)

    for event in reload_list:
        name = event.module
        message = str(event)
        if event.module in touch_list:
            assert re.match(rf'Reloaded {name} modified .* ago',message)
        else:
            assert re.match(rf'Reloaded {name} because .* reloaded',message)


def _define(direct:bool, touch:str, expect:str):

    touch_list = touch.split()
    expect_list = expect.split()

    name = 'test_' + ('d_' if direct else 'i_') + '_'.join(touch_list)

    doc = "    Touching {}, expecting reloads of {}".format(
        ", ".join(touch_list),
        ", ".join(expect_list))

    fn = lambda: _test(direct,touch_list,expect_list)
    fn.__name__ = name
    fn.__doc__ = doc

    globals()[name] = fn


_define(True,"A","A")
_define(True,"B","B")
_define(True,"C","C A B")
_define(True,"D","D B")
_define(True,"E","E C A B")
_define(True,"F","F C A D B")
_define(True,"G","G B")
_define(True,"B G","G B")
_define(True,"D F G","F C A D G B")
_define(True,"A B F","F C A D B")

_define(False,"A","A E C B")
_define(False,"B","B")
_define(False,"C","C B")
_define(False,"D","D B")
_define(False,"E","E C B")
_define(False,"F","F C D B")
_define(False,"G","G B")
_define(False,"D F","F C D B")


def test_add_dependency():
    """
    Making E depend on G after registration.
    """
    liveimport.register(globals(),"import A, B, C, D, E, F, G")

    time.sleep(0.05)
    with revised_module("E",postscript="import G"):
        touch_module("G")
        reload_clear()
        liveimport.sync(observer=reload_observe)
        reload_expect("G","E","C","A","B") #type:ignore


def test_remove_dependency():
    """
    Making A not depend on C after registration.
    """
    liveimport.register(globals(),"import A, B, C, D, E, F, G")

    time.sleep(0.05)
    with revised_module("A",imports=[]):
        # No touch needed since we just wrote A.
        reload_clear()
        liveimport.sync(observer=reload_observe)
        reload_expect("A","E","C","B") #type:ignore

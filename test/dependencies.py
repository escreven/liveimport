#
# Tests of dependency detection and reload ordering.
#

import re
import liveimport
from common import *

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
# There is a cycle A->C->E->A.  Because imports from E are registered after
# those from A and C, arc E->A should be effectively ignored.
#
# The primary thing we test in this module are which modules are reloaded and
# reload order, as reported through the recorder option of sync().  That is
# implemented by test functions dynamically created as lambdas calling _test()
# by _define().  _define() argument touch is whitespace separated list of
# modules to modify.  Argument expect is whitespace separated list of modules
# for which reload is expected in the order given.
#


def _test(touch_list:list[str], expect_list:list[str]):

    liveimport.register(globals(),"import A, B, C, D, E, F, G")

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


def _define(touch:str, expect:str):

    touch_list = touch.split()
    expect_list = expect.split()

    name = 'test_' + '_'.join(touch_list)

    doc = "    Touching {}, expecting reloads of {}".format(
        ", ".join(touch_list),
        ", ".join(expect_list))

    fn = lambda: _test(touch_list,expect_list)
    fn.__name__ = name
    fn.__doc__ = doc

    globals()[name] = fn


_define("A","A")
_define("B","B")
_define("C","C A B")
_define("D","D B")
_define("E","E C A B")
_define("F","F C A D B")
_define("G","G B")
_define("B G","G B")
_define("D F G","F C A D G B")
_define("A B F","F C A D B")


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

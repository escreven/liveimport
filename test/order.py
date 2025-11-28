#
# Test statement order guarantees.
#

import liveimport
from common import *

# globals() access means this can't be defined in setup
def is_registered(modulename:str, name:str|None=None, asname:str|None=None,
                  namespace:dict[str,Any]|None=None):
    if namespace is None: namespace = globals()
    return liveimport._is_registered(namespace,modulename,name,asname)


def test_from_name():
    """
    Given two statements of the form "from <module> import x", the second
    registered should dominate with respect to the value of x.
    """
    ns:dict[str,Any] = { 'x': 'mod2' }

    liveimport.register(ns,"""
    from mod1 import x
    from mod2 import x
    """)

    mod1_tag = get_tag("mod1")
    mod2_tag = get_tag("mod2")

    touch_module("mod1")
    liveimport.sync()
    expect_tag("mod1",next_tag(mod1_tag))
    expect_tag("mod2",mod2_tag)
    assert ns['x'] == 'mod2'

    ns['x'] = 42
    touch_module("mod2")
    liveimport.sync()
    assert ns['x'] == 'mod2'

    liveimport.register(ns,"from mod1 import x")
    touch_module("mod1")
    liveimport.sync()
    assert ns['x'] == 'mod1'


def test_from_name_as():
    """
    Given two statements of the form "from <module> import x as y", the second
    registered should dominate with respect to the value of y.
    """
    ns:dict[str,Any] = { 'y': 'mod2' }

    liveimport.register(ns,"""
    from mod1 import x as y
    from mod2 import x as y
    """)

    mod1_tag = get_tag("mod1")
    mod2_tag = get_tag("mod2")

    touch_module("mod1")
    liveimport.sync()
    expect_tag("mod1",next_tag(mod1_tag))
    expect_tag("mod2",mod2_tag)
    assert ns['y'] == 'mod2'

    ns['y'] = 42
    touch_module("mod2")
    liveimport.sync()
    assert ns['y'] == 'mod2'

    liveimport.register(ns,"from mod1 import x as y")
    touch_module("mod1")
    liveimport.sync()
    assert ns['y'] == 'mod1'


def test_from_star():
    """
    Given two statements of the form "from <module> import *", the second
    registered should dominate with respect to any variables with the same
    name.
    """
    ns:dict[str,Any] = { 'x': 'mod2' }

    liveimport.register(ns,"""
    from mod1 import *
    from mod2 import *
    """)

    mod1_tag = get_tag("mod1")
    mod2_tag = get_tag("mod2")

    touch_module("mod1")
    liveimport.sync()
    expect_tag("mod1",next_tag(mod1_tag))
    expect_tag("mod2",mod2_tag)
    assert ns['x'] == 'mod2'

    ns['x'] = 42
    touch_module("mod2")
    liveimport.sync()
    assert ns['x'] == 'mod2'

    liveimport.register(ns,"from mod1 import *")
    touch_module("mod1")
    liveimport.sync()
    assert ns['x'] == 'mod1'


def test_import_as():
    """
    Given two statements of the form "import <module> as u", the second
    registered should dominate with respect to the binding of u.
    """
    mod1 = sys.modules['mod1']
    mod2 = sys.modules['mod2']
    ns:dict[str,Any] = { 'u': mod2 }

    liveimport.register(ns,"""
    import mod1 as u
    import mod2 as u
    """)

    mod1_tag = get_tag("mod1")
    mod2_tag = get_tag("mod2")

    touch_module("mod1")
    liveimport.sync()
    expect_tag("mod1",next_tag(mod1_tag))
    expect_tag("mod2",mod2_tag)
    assert ns['u'] == mod2

    ns['u'] = 42
    touch_module("mod2")
    liveimport.sync()
    assert ns['u'] == mod2

    liveimport.register(ns,"import mod1 as u")
    touch_module("mod1")
    liveimport.sync()
    assert ns['u'] == mod1


def test_repeated():
    """
    Repeatedly re-registering to rotate statement order should always have a
    defined state, the state after an even number of flips should match the
    state before any flips.
    """
    ns:dict[str,Any] = { 'x': 'mod2' }

    liveimport.register(ns,"""
    from mod1 import x
    from mod2 import x
    """)

    hashcode = hash_state()

    for _ in range(3):

        touch_module("mod1")
        liveimport.sync()
        assert ns['x'] == 'mod2'

        liveimport.register(ns,"from mod1 import x")
        touch_module("mod2")
        liveimport.sync()
        assert ns['x'] == 'mod1'

        liveimport.register(ns,"from mod2 import x")

    assert hashcode == hash_state()

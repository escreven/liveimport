#
# A variety of import statements referencing the modules created in setup.py.
# Test modules include "from setup_imports import *" to define names on which
# test tests depend.
#
# IMPORTANT: The import from setup_imports must be after setup is imported.
#
# We need "#type: ignore" the imports because while the test files will exist
# when the imports execute, static code analyzers don't know that.
#

import mod1 #type:ignore
from mod2 import mod2_public1, mod2_public2 as mod2_public2_alias #type:ignore
from mod3 import * #type:ignore
from mod4 import * #type:ignore
import mod5 as hide_mod5 #type:ignore
import mod6 #type:ignore
import pkg.smod1 #type:ignore
from pkg.smod2 import smod2_public1 #type:ignore
from pkg import smod3 #type:ignore
import pkg.smod4 as hide_smod4 #type:ignore
import pkg.subpkg.ssmod1 #type:ignore
import pkg.subpkg.ssmod2 #type:ignore
from pkg.subpkg.ssmod1 import ssmod1_public1 #type:ignore
import pkg.subpkg #type:ignore
import A, B, C, D, E, F, G #type:ignore
from altpkg import amod1 #type:ignore
import subdir1 #type:ignore
from subdir1 import mod7 #type:ignore
from subdir2.mod9 import mod9_public1 #type:ignore
import nspkg #type:ignore
from nspkg import mod8 #type: ignore
from nspkg.mod10 import mod10_public1 #type: ignore

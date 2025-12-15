#
# Verify README.md is a deployable state.
#
# PyPI incorporates the README into the pypi.org liveimport package description
# page as-is.  It doesn't correct relative GitHub links, so links in README.md
# must be absolute.
#
# op.sh runs this script before declaring a release or deploying to [Test]PyPI.
#

import re
import sys

link_re = re.compile(r"]\(\s*([^\s]+)\s*\)")

for link in link_re.findall(open("README.md").read()):
    if not link.startswith("https://"):
        print(f"README.md may contain link {link}",file=sys.stderr)
        print("Only absolute https:// links should be used")
        sys.exit(1)
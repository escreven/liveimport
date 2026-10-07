## Organization

| File | Name |
| - | - |
| test-autoload.yml | Autoload Test |
| test.yml | Integration Test |
| verify-pypi.yml | Verify Deployment |
| watch.yml | Dependency Watch |


## Overview

### Tests

Every workflow except Dependency Watch runs tests over the following matrix:

| Dimension | Values |
| - | - |
| OS | Ubuntu, Windows, macOS |
| Python | 3.10, 3.11, ..., 3.15 |
| Dependencies | oldest, latest |

The `oldest` dependency presently means pip should install `ipython==7.23.1`
and `notebook==5.7.0`.  The `latest` dependency means pip should install
`ipython` and `notebook` unpinned.

Since the goal of Dependency Watch is to catch issues with just released
versions of `notebook` or `ipython`, it only tests dependency `latest`.

Integration Test, Verify Deployment, and Dependency Watch all run the
LiveImport [test
suite](https://github.com/escreven/liveimport/blob/main/test/README.md),
followed by an autoload extra test implemented by the custom [check-autoload](
https://github.com/escreven/liveimport/blob/main/.github/actions/check-autoload/action.yml)
action.  Autoload Test only tests the `autoload` extra (not using the custom
action.)


### Canaries

The Integration Test and Dependency Watch workflows include "canary" jobs that
test Python 3.12 on Ubuntu with the oldest and latest dependencies before
testing the full matrix.  Almost certainly a large number of those other tests
will fail if either canary job fails; waiting for them avoids wasting GitHub
resources.

### `setup-python` Cache Key

In addition to the OS, processor, Python version elements always present the
`setup-python` action's pip cache key, the workflows make the cache key depend
on `.pip-cache-key` written by

```sh
    date -u +'%G-%V' > .pip-cache-key
    echo "${{ matrix.dependencies }}" >> .pip-cache-key
```

The date string includes the year and a week number, rotating the setup-python
pip cache key weekly.  Rotation makes sense because caches are write once
&mdash; newer versions of packages will not be cached until the key changes.
Making `oldest` or `newest` part of the key means very different collections of
package versions will be cached separately.

Someday it might make sense to have to specific versions of `ipython` and
`notebook` used be part of the cache key instead of `oldest` or `newest`; not
worth the complexity for now.

## Workflows

### Integration Test

The Integration Test workflow is run on pull requests and manually.  It
installs LiveImport from the repo main branch, and succeeds if any only if
every test suite run succeeds with 100% code coverage.

### Verify Deployment

Verify Deployment confirms that a LiveImport release is successfully deployed.
The workflow is run manually with two parameters: a repository (PyPI or
TestPyPI) and an expected release number.  It installs unpinned version of
`liveimport` from the specified repository, verifies the installed package has
the expected version, then runs the test suite.

### Dependency Watch

The goal of Dependency Watch is to quickly detect new releases of `ipython` or
`notebook` that break LiveImport.  It runs every twelve hours, polling PyPI for
the lastest `ipython` and `notebook` version numbers.  If those numbers don't
match versions Dependency Watch knows to have been tested, the workflow runs
the test suite across all platforms and Python versions in the matrix using the
last released version of LiveImport.

If there is a failure, Dependency Watch creates a GitHub issue.

### Autoload Test

Autoload Test is run manually to test the `liveimport-autoload` during
development.  It tests the `autoload` extra, but does not use the custom
action, instead installing `liveimport-autoload` from the repo.


## Summary

| Workflow | When | LiveImport From[^1] | Tests |
| - | - | - | - |
| Autoload Test | Manual | GitHub | `autoload` |
| Integration Test | PR, Manual | GitHub | `test/main.py`[^2] + `autoload`|
| Verify Deployment | Manual | [Test]PyPI | `test/main.py` + `autoload` |
| Dependency Watch | Every 12h | PyPI | `test/main.py` + `autoload` |

[^1]: The `liveimport` package only.  The `liveimport-autoload` package is
    installed from PyPI or TestPyPI by all workflows except Autoload Test,
    which installs it from GitHub.

[^2]: The Integration Test workflow requires the test suite to pass with 100%
    code coverage.

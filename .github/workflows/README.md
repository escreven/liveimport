## Organization

| File | Name |
| - | - |
| [test-autoload.yml](https://github.com/escreven/liveimport/blob/main/.github/workflows/test-autoload.yml) | Autoload Test |
| [test.yml](https://github.com/escreven/liveimport/blob/main/.github/workflows/test.yml) | Integration Test |
| [verify-pypi.yml](https://github.com/escreven/liveimport/blob/main/.github/workflows/verify-pypi.yml) | Verify PyPI |
| [watch.yml](https://github.com/escreven/liveimport/blob/main/.github/workflows/watch.yml) | Dependency Watch |


## Overview

### Tests

Every workflow except Dependency Watch runs tests over the following matrix:

| Dimension | Values |
| - | - |
| OS | Ubuntu, Windows, macOS |
| Python | 3.10, 3.11, ..., 3.15 |
| Dependencies | oldest, latest |

The `oldest` dependency presently means pip should install `ipython==7.23.1`
and `notebook==5.7.0`.  The `latest` dependency means pip should install the
latest versions of `ipython` and `notebook`.

Since the goal of Dependency Watch is to catch issues with just released
versions of `notebook` or `ipython`, it only tests dependency `latest`.
Furthermore, because the latest versions of `ipython` require Python >=3.12,
Dependency Watch tests Python versions 3.12 through 3.15.

Integration Test, Verify PyPI, and Dependency Watch all run the LiveImport
[test suite](https://github.com/escreven/liveimport/blob/main/test/README.md),
followed by an `autoload` extra test implemented by the custom
[check-autoload](
https://github.com/escreven/liveimport/blob/main/.github/actions/check-autoload/action.yml)
action.  Autoload Test tests the `liveimport-autoload` package directly and
does not run the test suite.

### Canaries

The Integration Test, Verify PyPI, and Dependency Watch workflows include
"canary" jobs that test with Python 3.12 on Ubuntu before testing the full
matrix.  Almost certainly a large number of the remaining tests will fail if
any canary job fails; requiring the canaries to succeed avoids wasting GitHub
resources.  This is especially helpful for Verify PyPI since there is a lag
between when a release is uploaded to PyPI and it becomes available to install
in a GitHub runner.

### `setup-python` Cache Key

In addition to the OS, processor, and Python version elements always present in
the `setup-python` action's pip cache key, the workflows make the cache key
depend on `.pip-cache-key` written by

```sh
date -u +'%G-%V' > .pip-cache-key
echo "${{ matrix.dependencies }}" >> .pip-cache-key
```

The date string includes the year and a week number, rotating the setup-python
pip cache key weekly.  Rotation makes sense because caches are write once
&mdash; newer versions of packages will not be cached until the key changes.
Making `oldest` or `latest` part of the key means very different collections of
package versions will be cached separately.

Someday it might make sense to have the specific versions of `ipython` and
`notebook` used be part of the cache key instead of `oldest` or `latest`.

## Workflows

### Integration Test

The Integration Test workflow is run on pull requests and manually.  It
installs LiveImport from the repo, and succeeds only if every test suite run
succeeds with 100% code coverage.

### Verify PyPI

Verify PyPI confirms that a LiveImport release is successfully deployed.  The
workflow is run manually with two parameters: a repository (PyPI or TestPyPI)
and an expected release number.  It requires the corresponding release tag to
exist, installs an unpinned version of `liveimport` from the specified
repository, verifies the installed package has the expected version, then runs
the test suite.

### Dependency Watch

The goal of Dependency Watch is to quickly detect new releases of `ipython` or
`notebook` that break LiveImport.  It runs every twelve hours, polling PyPI for
the lastest `ipython` and `notebook` version numbers.  If those numbers don't
match versions Dependency Watch knows to have been tested, the workflow runs
the test suite across all platforms and Python versions in the matrix using the
last released version of LiveImport.

If there is a failure during a scheduled run, Dependency Watch creates a GitHub
issue.

### Autoload Test

Autoload Test is run manually to test the `liveimport-autoload` package during
development.  It verifies startup behavior after installation and
uninstallation.  It does not use the custom action, instead installing
`liveimport-autoload` from the repo.

## Summary

| Workflow | Matrix | When | LiveImport From[^1] | Tests |
| - | - | - | - | - |
| Autoload Test | Full | Manual | GitHub | `liveimport-autoload` package |
| Integration Test | Full | PR, Manual | GitHub | `test/main.py`[^2] + `autoload` extra|
| Verify PyPI | Full | Manual | [Test]PyPI | `test/main.py` + `autoload` extra |
| Dependency Watch | subset[^3] | Every 12h | PyPI | `test/main.py` + `autoload` extra |

[^1]: The `liveimport` package only.  The `liveimport-autoload` package is
    installed from PyPI or TestPyPI by all workflows except Autoload Test,
    which installs it from GitHub.

[^2]: The Integration Test workflow requires the test suite to pass with 100%
    code and branch coverage.

[^3]: All combinations of OS and Python versions 3.12 through 3.15 with the
    `latest` dependencies.

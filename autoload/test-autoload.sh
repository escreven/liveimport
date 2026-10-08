#!/bin/bash

#
# test-autoload.sh - Test LiveImport autoload installation and removal.
#
# This script is both used from the command line and and invoked by the
# test-autoload.yml workflow.
#

set -euo pipefail

#
# Report fatal error to stderr and exit.
#

function fail {
    echo "FAILED: $@" >&2
    exit 1
}

#
# Remove the temporary environment on both success and failure.
#

function cleanup {
    local status=$?
    trap - EXIT
    if ! rm -rf "$tempdir"; then
        echo "FAILED: Could not remove temporary directory $tempdir" >&2
        status=1
    fi
    exit "$status"
}

#
# Direct execution must succeed without writing to either output stream.
# Use a file so that even output consisting only of newlines is detected.
#

function require_silent_startup {
    local stage=$1
    "$PYTHON" "$startup" > "$tempdir/startup.log" 2>&1 \
        || fail "Startup file failed $stage; output: $(cat "$tempdir/startup.log")"
    [[ ! -s $tempdir/startup.log ]] \
        || fail "Startup file produced output $stage: $(cat "$tempdir/startup.log")"
}

#
# Feed the probe to an interactive IPython session.  IPython catches
# SystemExit, so use os._exit to propagate a failed probe to the shell.
# Require a marker as well, in case IPython exits without running the probe.
#

function require_autoload {
    local expected=$1
    local stage=$2
    "$PYTHON" -m IPython --simple-prompt --no-confirm-exit \
            > "$tempdir/ipython.log" 2>&1 <<EOF \
        || fail "IPython failed $stage; output: $(cat "$tempdir/ipython.log")"
import sys, os
loaded = 'liveimport' in sys.modules
print('liveimport present:', loaded)
print('AUTOLOAD-PROBE-PASSED' if loaded == $expected else 'AUTOLOAD-PROBE-FAILED', flush=True)
os._exit(0 if loaded == $expected else 1)
EOF
    grep -q 'AUTOLOAD-PROBE-PASSED' "$tempdir/ipython.log" \
        || fail "IPython did not complete the probe $stage; output: $(cat "$tempdir/ipython.log")"
}

#
# ================================ MAIN ======================================
#

# --no_venv requires an environment without IPython or LiveImport and leaves
# both installed after testing.  --venv requires python3.<n> on PATH.

mode=
version=
ipython_package=IPython
ipython_version=

for argument in "$@"; do
    case "$argument" in
        --venv=*)
            [[ -z $mode ]] || fail "Specify exactly one of --venv and --no_venv"
            mode=venv
            version=${argument#--venv=}
            [[ $version =~ ^3\.[0-9]+$ ]] \
                || fail "Python version must have the form 3.<n> (Example: 3.15)"
            ;;
        --no_venv)
            [[ -z $mode ]] || fail "Specify exactly one of --venv and --no_venv"
            mode=no_venv
            ;;
        --ipython=*)
            [[ -z $ipython_version ]] || fail "Specify --ipython only once"
            ipython_version=${argument#--ipython=}
            [[ -n $ipython_version ]] || fail "IPython version must not be empty"
            [[ $ipython_version =~ ^[0-9][a-zA-Z0-9.+!]*$ ]] \
                || fail "IPython version must be a specific version"
            ipython_package="IPython==$ipython_version"
            ;;
        *)
            fail "Unknown argument: $argument"
            ;;
    esac
done

[[ -n $mode ]] \
    || fail "Usage: $0 (--venv=3.<n> | --no_venv) [--ipython=VERSION]"

if [[ $mode == venv ]]; then
    PYTHON="python$version"
else
    PYTHON=python
fi

command -v "$PYTHON" > /dev/null \
    || fail "Could not find $PYTHON on PATH"

# Resolve the interpreter before changing directories.
PYTHON=$("$PYTHON" -c 'import sys; from pathlib import Path; print(Path(sys.executable).as_posix())') \
    || fail "Could not determine Python executable path"

cd "$(dirname "$BASH_SOURCE")/.." || fail "Could not find repository root"
repo=$PWD

tempdir=$("$PYTHON" -c 'import tempfile; from pathlib import Path; print(Path(tempfile.mkdtemp(prefix="liveimport-autoload.")).as_posix())') \
    || fail "Could not create temporary directory"

trap cleanup EXIT
trap 'fail "Interrupted"' HUP INT TERM

#
# Keep user configuration and source-tree imports out of the test.
# Build local copies because pip can write build and egg-info directories.
#

unset PYTHONPATH PYTHONHOME LIVEIMPORT_NO_AUTOLOAD

export IPYTHONDIR="$tempdir/ipython"
export PYTHONNOUSERSITE=1

mkdir -p "$tempdir/source/autoload" "$IPYTHONDIR" \
    || fail "Could not create temporary source and configuration directories"

cp "$repo/pyproject.toml" "$repo/README.md" "$tempdir/source/" \
    || fail "Could not copy LiveImport package metadata"

cp -R "$repo/src" "$tempdir/source/" \
    || fail "Could not copy LiveImport source"

cp "$repo/autoload/pyproject.toml" "$repo/autoload/README.md" \
        "$tempdir/source/autoload/" \
    || fail "Could not copy autoload package metadata"

cp -R "$repo/autoload/startup" "$tempdir/source/autoload/" \
    || fail "Could not copy autoload startup file"

cd "$tempdir" || fail "Could not enter temporary directory"

#
# Create a virtual environment for the specified Python version, or use
# the current environment selected by setup-python.
#

if [[ $mode == venv ]]; then
    venv="$tempdir/venv"
    "$PYTHON" -m venv "$venv" \
        || fail "Could not create Python $version virtual environment"
    if [[ -f $venv/Scripts/python.exe ]]; then
        PYTHON="$venv/Scripts/python.exe"
    else
        PYTHON="$venv/bin/python"
    fi
fi

#
# Ensure IPython and LiveImport are not installed in the Python environment.
#

for package in IPython liveimport; do
    "$PYTHON" -c 'import importlib.util, sys; sys.exit(importlib.util.find_spec(sys.argv[1]) is not None)' "$package" \
        || fail "$package must be absent before testing installation"
done

#
# Get the startup file path.
#

startup=$("$PYTHON" -c 'import sysconfig; from pathlib import Path; print((Path(sysconfig.get_path("data")) / "etc/ipython/startup/00-liveimport.py").as_posix())') \
    || fail "Could not determine autoload startup file path"

#
# Install liveimport-autoload.  This should copy 00-liveimport.py to
# etc/ipython/startup/.
#

"$PYTHON" -m pip install "$tempdir/source/autoload" \
    || fail "Could not install liveimport-autoload"

[[ -f $startup ]] || fail "Autoload startup file was not installed at $startup"

#
# Executing the startup file when IPython and LiveImport are not installed
# should be a no-op.
#

require_silent_startup "before installing IPython"

#
# Now install IPython.  Executing the startup file directly should still be a
# no-op since there is no IPython shell, and running an IPython kernel should
# do nothing since LiveImport isn't installed.
#

"$PYTHON" -m pip install --upgrade "$ipython_package" \
    || fail "Could not install $ipython_package"

require_silent_startup "after installing IPython"
require_autoload False "before installing LiveImport"

#
# Install LiveImport.  Running IPython should now automatically load
# LiveImport.
#

"$PYTHON" -m pip install "$tempdir/source" \
    || fail "Could not install LiveImport"

require_autoload True "after installing LiveImport"

#
# Automatically loading LiveImport should be suppressed when
# LIVEIMPORT_NO_AUTOLOAD is present in the environment, unless its value is
# either 0 or false (by case-insensitive comparison.)
#

LIVEIMPORT_NO_AUTOLOAD=1 \
    require_autoload False "with LIVEIMPORT_NO_AUTOLOAD=1"

LIVEIMPORT_NO_AUTOLOAD= \
    require_autoload False "with LIVEIMPORT_NO_AUTOLOAD empty"

LIVEIMPORT_NO_AUTOLOAD=0 \
    require_autoload True "with LIVEIMPORT_NO_AUTOLOAD=0"

LIVEIMPORT_NO_AUTOLOAD=FaLsE \
    require_autoload True "with LIVEIMPORT_NO_AUTOLOAD=FaLsE"

#
# Uninstall liveimport-autoload.  Running IPython should no longer
# automatically load LiveImport.
#

"$PYTHON" -m pip uninstall -y liveimport-autoload \
    || fail "Could not uninstall liveimport-autoload"

require_autoload False "after uninstalling liveimport-autoload"

echo "Done."

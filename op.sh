#!/bin/sh

#
# op.sh - A build and deployment script for LiveImport
#

set -euo pipefail

if [[ $(uname -s) == CYGWIN* ]]; then
    PYTHON=py
else
    PYTHON=python3
fi


#
# Report fatal error to stderr and exit.
#

function fail {
    echo "FAILED: $@" >&2
    exit 1
}

#
# Succeed iff all version markers in project are identical (currently in
# pyproject.toml and liveimport.py.)  Output is the consistent version.
#

function require_consistent_version {

    local pyproject_version
    pyproject_version=$(\
        sed -n 's/^version = "\([^"][^"]*\)"/\1/p' pyproject.toml)

    [[ -z $pyproject_version ]] \
        && fail "Could not find version in pyproject.toml"

    local python_version
    python_version=$(\
        sed -n 's/^__version__ = "\([^"][^"]*\)"/\1/p' src/liveimport.py)

    [[ -z $python_version ]] \
        && fail "Could not find version in liveimport.py"
        
    [[ $pyproject_version == "$python_version" ]] \
        || fail "Version mismatch: pyproject.toml ($pyproject_version)" \
                "!= src/liveimport.py ($python_version)"

    echo $python_version
}

#
# Succeed iff there is no release tag for version.
#

function require_not_released {
    local version=$1

    if git tag -l | grep -q "v${version}"; then
        fail "Source version $version already released"
    fi
}

#
# Make sure the current version has a <major>.<minor>.<patch> form.
#

function require_releasable_version {
    local version=$1
    [[ $version =~ \d+.\d+.\d+ ]] \
        || fail "Release versions must be <major>.<minor>.<patch>;" \
                "have version $version"
}

#
# Succeed iff there is exactly built version, which we determine by counting
# wheel files in dist/.
#

function require_one_built_version {

    [[ -d dist ]] || fail "Distribution directory dist/ does not exist"

    local count
    count=$(ls dist/*.whl 2>/dev/null | wc -l)

	[[ $count -eq 1 ]] || fail "Expected one built version; found" "$count"
}

#
# Succeed iff twine check succeeds for the built distribution files.
#
# NOTE: There is currently a bug in twine or setuptools that causes this to
# spuriously fail on Mac with an error message related to license_file.
#

function require_good_build {
    $PYTHON -m twine check dist/* || fail "Twine check failed"
}

#
# Succeed iff the local repo is on branch main, is synced with remote (neither
# ahead nor behind), and has no unstaged or uncommitted changes.
#

function require_git_tip {

    local current_branch
    current_branch=$(git rev-parse --abbrev-ref HEAD)

    [[ $current_branch == main ]] \
        || fail "On branch $current_branch, not main"

    git fetch origin

    (git status -uno | grep -q "Your branch is up to date") \
        || fail "Local is not synced with remote"

    git diff --quiet || fail "There are unstaged changes"

    git diff --cached --quiet || fail "There are uncommitted changes"
}

#
# Build the wheel and sdist files.  build_dist removes the left-over egg-info
# directory.  Hopefully build will stop leaving behind one day.
#

function build_dist {

    local version 
    version=$(require_consistent_version)

    require_not_released "$version"

    echo "Building version $version"
    $PYTHON -m build

    if [[ -d src/liveimport.egg-info ]]; then
        echo "Deleting egg-info"
        /bin/rm -r -f src/liveimport.egg-info
    fi
}

#
# Update to TestPyPI or PyPI.  
#
# We only allow uploads if the repo is in sync with the tip of main.  In some
# ways this is the wrong place to check, since the build could have been
# performed in a branch.  But for testing, we want to allow building in a
# branch, so we check here.
#
# Because uploading to [Test]PyPI cannot be undone, upload_dist requires user
# confirmation.
#

upload_dist() {

    local version
    version=$(require_consistent_version)
    require_releasable_version "$version"
    require_one_built_version
    require_good_build
    require_git_tip
    local name=$1
    local repo=$2
    local confirm
    echo
    echo ">>>> Uploading to $name cannot be undone."
    read -p ">>>> Type $name to confirm: " confirm
    echo
    if [[ $confirm != "$name" ]]; then
        echo "Upload canceled."
        exit 1
    fi
    $PYTHON -m twine upload --repository "$repo" dist/*
}

#
# Print usage and exit.
#

usage() {
    echo "Usage: $0 ACTION"
    echo
    echo "Where ACTION is one of"
    echo 
    echo "    build-doc           Build the documentation"
    echo "    build-dist          Build wheel and sdist files in dist/"
    echo "    check-dist          Verify the distribution files"
    echo "    check-tip           Verify local repo is at tip"
    echo "    deploy-to-testpypi  Upload distribution files to TestPyPI"
    echo "    deploy-to-pypi      Upload distribution files to PyPI"
    echo "    clean-doc           Delete documentation"
    echo "    clean-dist          Delete distribution files"
    echo "    clean               Delete both doc and distribution files"
    echo 
    echo "The deployment actions require user confirmation."
    echo
    exit 1
}


#
# This script should be at the root of the project directory -- go there.  The
# project must have a prproject.toml file, and the project name must be
# liveimport.
#

cd "$(dirname "$BASH_SOURCE")"

[[ -f pyproject.toml ]] || fail "No pyproject.toml"

grep -qE 'name\s*=\s*"liveimport"' pyproject.toml \
    || fail "Project name is not liveimport."

#
# Dispatch
#

if [[ $# -lt 1 ]]; then
    usage
fi

case "$1" in
    build-doc)
        make -C doc html
        ;;
    build-dist)
        build_dist
        ;;
    check-dist)
        require_one_built_version
        require_good_build
        ;;
    check-tip)
        require_git_tip
        ;;
    deploy-to-testpypi)
        upload_dist TestPyPI testpypi
        ;;
    deploy-to-pypi)
        upload_dist PyPI pypi
        ;;
    clean-doc)
        make -C doc clean
        ;;
    clean-dist)
        rm -rf dist/*
        ;;
    clean)
        make -C doc clean >/dev/null
        rm -rf dist/*
        ;;
    *)
        usage
        ;;
esac

echo "Done."

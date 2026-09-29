#!/bin/bash

#
# op-autoload.sh - A build and deployment script for liveimport-autoload
#

set -euo pipefail

if [[ $(uname -s) == CYGWIN* ]]; then
    PYTHON=py
else
    PYTHON=python3
fi

#
# The name of the LiveImport public remote.
#

PUBLIC=public

#
# Report fatal error to stderr and exit.
#

function fail {
    echo "FAILED: $@" >&2
    exit 1
}

#
# Several operations depend on git state.  Bring it up to date.
#

did_fetch_all=False
function fetch_all {
    if [[ $did_fetch_all == False ]]; then
        git fetch --all --prune --no-tags \
            || fail "Could not fetch state from git."
        did_fetch_all=True
    fi
}

#
# Wheel and sdist filenames given a version.
#

function wheel_file {
    echo "dist/liveimport_autoload-$1-py3-none-any.whl"
}

function sdist_file {
    echo "dist/liveimport_autoload-$1.tar.gz"
}

#
# Read the project version.
#

function require_version {

    local version
    version=$(\
        sed -n 's/^version = "\([^"][^"]*\)"/\1/p' pyproject.toml)

    [[ -z $version ]] \
        && fail "Could not find version in pyproject.toml"

    echo "$version"
}

#
# Succeed iff the given version has a <major>.<minor>.<patch> form.
#

function require_releasable_version {
    local version=$1
    [[ $version =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] \
        || fail "Release versions must be <major>.<minor>.<patch>;" \
                "have version $version"
}

#
# Succeed iff the given version and no other is built, and twine check
# succeeds for that build.
#

function require_good_build {
    local version=$1

    [[ -d dist ]] || fail "Distribution directory dist/ does not exist"

    [[ -f $(wheel_file $version) && -f $(sdist_file $version) ]] \
        || fail "Version $version not built"

    #
    # We don't need to worry about ls dist/*.whl failing because we know there
    # is at least one .whl file there.
    #

    local count
    count=$(ls dist/*.whl 2>/dev/null | wc -l)

    [[ $count -eq 1 ]] || fail "Expected one built version; found" "$count"

    $PYTHON -m twine check \
            "$(wheel_file "$version")" \
            "$(sdist_file "$version")" \
        || fail "Twine check failed"
}

#
#  Succeed iff the local repo is on branch main with a clean tree synchronized
#  with the given branch (which should be $PUBLIC/main).
#

function require_git_clean {
    local branch=$1

    fetch_all

    local current_branch
    current_branch="$(git rev-parse --abbrev-ref HEAD)"

    [[ $current_branch == main ]] \
        || fail "On branch $current_branch, not main"

    git diff --quiet || fail "There are unstaged changes"

    git diff --cached --quiet || fail "There are uncommitted changes"

    git status --porcelain | grep -q '^??' \
        && fail "There are untracked files"

    [[ $(git rev-parse HEAD) == "$(git rev-parse "$branch")" ]] \
        || fail "Local repo not synced with $branch"
}

#
# Require the autoload README.md to be in a deployable state.  For now that
# just means it contains no relative links.
#

function require_deployable_README {
    $PYTHON ../README-check.py || fail "README.md is not deployable"
}

#
# Build the wheel and sdist files.  build_dist removes the left-over egg-info
# directory.  Hopefully build will stop leaving it behind one day.
#

function build_dist {

    mkdir -p dist

    local version
    version=$(require_version)

    /bin/rm -f dist/*.whl dist/*.tar.gz

    echo "Building version $version"
    $PYTHON -m build

    if [[ -d liveimport_autoload.egg-info ]]; then
        echo "Deleting egg-info"
        /bin/rm -r -f liveimport_autoload.egg-info
    fi
}

#
# Check the wheel and sdist files.
#

function check_dist {

    local version
    version=$(require_version)
    require_good_build $version
}

#
# Upload to TestPyPI or PyPI.
#
# The project version must have a good build.  The local repo must be a clean
# tree synchronized with public main.  Because uploading to [Test]PyPI cannot
# be undone, the user must confirm the operation and the package being uploaded.
#

upload_dist() {

    local name=$1
    local repo=$2

    local version
    version=$(require_version)

    require_releasable_version "$version"
    require_good_build "$version"
    require_git_clean $PUBLIC/main
    require_deployable_README

    local confirm

    echo
    echo ">>>> The package being uploaded is liveimport-autoload."
    read -p ">>>> Type Autoload to confirm: " confirm
    echo
    if [[ $confirm != Autoload ]]; then
        echo "Upload canceled."
        exit 1
    fi

    echo
    echo ">>>> About to upload release $version to $name."
    echo ">>>> Uploading to $name cannot be undone."
    read -p ">>>> Type $name to confirm: " confirm
    echo
    if [[ $confirm != "$name" ]]; then
        echo "Upload canceled."
        exit 1
    fi

    $PYTHON -m twine upload --repository "$repo" \
        "$(wheel_file $version)" "$(sdist_file $version)"
}

#
# Print usage and exit.
#

usage() {
    echo "Usage: $0 ACTION"
    echo
    echo "Where ACTION is one of"
    echo
    echo "    build-dist          Build wheel and sdist files in dist/"
    echo "    check-dist          Verify the distribution files"
    echo "    check-clean-main    Verify local repo is on clean main branch"
    echo "    check-README        Verify README.md is deployable"
    echo "    deploy-to-testpypi  Upload distribution files to TestPyPI"
    echo "    deploy-to-pypi      Upload distribution files to PyPI"
    echo "    clean-dist          Delete distribution files"
    echo
    echo "The deployment actions require user confirmation."
    echo
    exit 1
}

#
# ================================ MAIN ======================================
#
# This script should be at the root of the project directory -- go there.  The
# project must have a pyproject.toml file, and the project name must be
# liveimport-autoload.
#

cd "$(dirname "$BASH_SOURCE")"

[[ -f pyproject.toml ]] || fail "No pyproject.toml"

grep -qE 'name\s*=\s*"liveimport-autoload"' pyproject.toml \
    || fail "Project name is not liveimport-autoload."

#
# Dispatch
#

if [[ $# != 1 ]]; then
    usage
fi

function act {
    case "$1" in
        build-dist)
            build_dist
            ;;
        check-dist)
            check_dist
            ;;
        check-clean-main)
            require_git_clean $PUBLIC/main
            ;;
        check-README)
            require_deployable_README
            ;;
        deploy-to-testpypi)
            upload_dist TestPyPI testpypi
            ;;
        deploy-to-pypi)
            upload_dist PyPI pypi
            ;;
        clean-dist)
            rm -rf dist/*
            ;;
        *)
            usage
            ;;
    esac
}

act $1

echo "Done."

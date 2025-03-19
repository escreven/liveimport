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
# Wheel and sdist filenames given a version.
#

function wheel_file {
    echo "dist/liveimport-$1-py3-none-any.whl"
}

function sdist_file {
    echo "dist/liveimport-$1.tar.gz"
}

#
# Succeed iff all version markers in the project are identical (currently in
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

    echo "$python_version"
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
# Succeed iff there is a release tag for version.
#

function require_released {
    local version=$1
    git tag -l | grep -q "v${version}" \
        || fail "Source version $version not released"
}

#
# Succeed iff the given version has a <major>.<minor>.<patch> form.
#

function require_releasable_version {
    local version=$1
    [[ $version =~ [0-9]+.[0-9]+.[0-9]+ ]] \
        || fail "Release versions must be <major>.<minor>.<patch>;" \
                "have version $version"
}

#
# Succeed iff the given version and not other is built, and twine check
# succeeds for that build.
#
# NOTE: There is currently a bug in twine or setuptools that causes this to
# spuriously fail on Mac with an error message related to license_file.
#

function require_good_build {
    local version=$1

    [[ -d dist ]] || fail "Distribution directory dist/ does not exist"  

    local count
    count=$(ls dist/*.whl 2>/dev/null | wc -l)

	[[ $count -eq 1 ]] || fail "Expected one built version; found" "$count"

    [[ -f $(wheel_file $version) && -f $(sdist_file $version) ]] \
        || fail "Version $version not built"
        
    local version=$1
    $PYTHON -m twine check \
            "$(wheel_file "$version")" \
            "$(sdist_file "$version")" \
        || fail "Twine check failed"
}

#
#  Succeed iff the local repo is on branch main with a clean tree synchronized
#  with the given branch or tag (which should be either remotes/origin/main or
#  the release tag).
#

function require_git_clean {
    local branch_or_tag=$1

    local current_branch
    current_branch="$(git rev-parse --abbrev-ref HEAD)"

    [[ $current_branch == main ]] \
        || fail "On branch $current_branch, not main"
    
    git diff --quiet || fail "There are unstaged changes"

    git diff --cached --quiet || fail "There are uncommitted changes"

    [[ -z "$(git ls-files --others --exclude-standard)" ]] \
        || fail "There are untracked files"

    #
    # Using "rev-list -1" on the right because rev-parse of an annotated tag is
    # the hash of the annotation object, not the commit id.  "rev-list -1"
    # works for branches and annotated tags.
    #

    [[ $(git rev-parse HEAD) == "$(git rev-list -1 "$branch_or_tag")" ]] \
        || fail "Local repo not synced with $branch_or_tag"
}

#
# Build the wheel and sdist files.  The current project version must be
# different than any released version.  build_dist removes the left-over
# egg-info directory.  Hopefully build will stop leaving behind one day.
#

function build_dist {

    [[ -d dist ]] || fail "Distribution directory dist/ does not exist"  

    local version 
    version=$(require_consistent_version)
    require_not_released "$version"

    /bin/rm -f dist/*.whl dist/*.tar.gz

    echo "Building version $version"
    $PYTHON -m build

    if [[ -d src/liveimport.egg-info ]]; then
        echo "Deleting egg-info"
        /bin/rm -r -f src/liveimport.egg-info
    fi
}

#
# Check the wheel and sdist files.  
#

function check_dist {

    local version 
    version=$(require_consistent_version)
    require_good_build $version
}

#
# Create and push a release tag.  The user is prompted for the release version.
# The response must match the version number embedded in the project, cannot
# have already been released, and must be the built version.  Also, the local
# repository must have a clean tree on branch main in sync with remote.
#

function declare_release {

    local version
    echo
    echo ">>>> About to declare a release."
    read -p ">>>> Enter release version number: " version
    echo

    local found_version
    found_version=$(require_consistent_version)

    [[ $version == "$found_version" ]] \
        || fail "Entered version $version " \
                "does not match project version $found_version"

    require_releasable_version "$version"
    require_not_released "$version"
    require_good_build "$version"
    require_git_clean remotes/origin/main

    tag="v$version"
    git tag -a "$tag" -m "Release $version"
    git push origin "$tag"
}

#
# Upload to TestPyPI or PyPI.  
#
# The project version must have a good build and must be released.  The local
# repo must be a clean tree synchronized with the release tag.  Because
# uploading to [Test]PyPI cannot be undone, the user must confirm the
# operation.
#

upload_dist() {

    local name=$1
    local repo=$2

    local version
    version=$(require_consistent_version)

    require_releasable_version "$version"
    require_good_build "$version"
    require_released "$version"
    require_git_clean "v$version"    

    local confirm
    echo
    echo ">>>> About to upload release $version to $name."
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
    echo "    check-clean-main    Verify local repo is on clean main branch"
    echo "    declare-release     Tag current clean main branch as a release"
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
# ================================ MAIN ======================================
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
# Several operations depend on git state.  Bring it up to date.
#

git fetch --all --prune --tags \
    || fail "Could not fetch state from git."

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
        check_dist
        ;;
    check-clean-main)
        require_git_clean remotes/origin/main
        ;;
    declare-release)
        declare_release
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

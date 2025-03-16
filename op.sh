#!/bin/sh

#
# op.sh - A build and deployment script for LiveImport
#

set -e

PYTHON=python3
if uname -s | grep -q CYGWIN; then
    PYTHON=py
fi

fail() {
    echo "FAILED: $@" >&2
    exit 1
}

require_consistent_version() {

    pyproject_version=$(\
        sed -n 's/^version = "\([^"][^"]*\)"/\1/p' pyproject.toml)

    [ -z "$pyproject_version" ] \
        && fail "Could not find version in pyproject.toml"

    python_version=$(\
        sed -n 's/^__version__ = "\([^"][^"]*\)"/\1/p' src/liveimport.py)

    [ -z "$python_version" ] \
        && fail "Could not find version in liveimport.py"
        
    [ "$pyproject_version" = "$python_version" ] \
        || fail "Version mismatch: pyproject.toml ($pyproject_version)" \
                " != src/liveimport.py ($python_version)"

    echo $python_version
}

require_one_built_version() {
    [ -d dist ] || fail "Distribution directory dist/ does not exist"
    count=$(ls dist/*.whl 2>/dev/null | wc -l)
	[ $count -eq 1 ] || fail "Expected one built version; found" $count
}

require_good_build() {
    $PYTHON -m twine check dist/* || fail "Twine check failed"
}

require_git_tip() {

    current_branch=$(git rev-parse --abbrev-ref HEAD)
    [ "$current_branch" = "main" ] \
        || fail "On branch $current_branch, not main"

    git fetch origin
    local_status=$(git status -uno | grep "Your branch is up to date")
    [ -n "$local_status" ] || fail "Local is not up to date with remote"

    git diff --quiet || fail "There are unstaged changes"

    git diff --cached --quiet || fail "There are uncommitted changes"
}

upload_dist() {
    require_one_built_version
    require_good_build
    require_git_tip
    name="$1"
    repo="$2"
    echo
    echo ">>>> Uploading to $name cannot be undone."
    read -p ">>>> Type $name to confirm: " confirm
    echo
    if [ "$confirm" != "$name" ]; then
        echo "Upload canceled."
        exit 1
    fi
    # $PYTHON -m twine upload --repository "$repo" dist/*
}

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

action="$1"

case "$action" in
    build-doc)
        make -C doc html
        ;;
    build-dist)
        version=$(require_consistent_version)
        echo "Building version $version"
        $PYTHON -m build
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
        make -C doc clean
        rm -rf dist/*
        ;;
    *)
        usage
        ;;
esac

echo "Done."

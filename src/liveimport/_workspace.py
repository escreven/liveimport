import os
from os import PathLike
from pathlib import Path


#
# Path.absolute() doesn't collapse /../ components (but does collapse /./
# components -- strange.)
#

def _absolute(path:str|PathLike) -> Path:
    return Path(os.path.abspath(path))


#
# The workspace is a possibly empty list of directory paths.  We use Path
# objects so we can use is_relative_to(), and we normalize using _absolute()
# instead of resolve() because we don't want to follow symbolic links -- most
# likely what a user expects.
#

if "_WORKSPACE" not in globals():
    _WORKSPACE:list[Path] = [ _absolute(".") ]

#
# Return true iff the named file is in the workspace.
#

def _in_workspace(file:str) -> bool:

    filepath = _absolute(file)

    for dirpath in _WORKSPACE:
        if filepath.is_relative_to(dirpath):
            return True

    return False


def workspace(*directories:str|PathLike) -> None:
    """
    Define the workspace, a set of directories.

    LiveImport tracks modules that either are imported by a registered import
    statement, or are imported by a tracked module and have a source file in
    the workspace.  A source file is in the workspace if and only if it's under
    a workspace directory.

    The default workspace is the current working directory when the LiveImport
    module is imported.  Thus, when LiveImport is used in a notebook, the
    workspace is the directory containing the notebook.

    :param directories: Zero or more path strings or path-like objects.  Each
        path must identify an existing directory.

    :raises ValueError: One of the specified paths does not exist or
        exists but is not a directory.

    Example: After calling

      .. code:: python

        liveimport.workspace("src", "/opt/notebook-utils")

    the workspace is the directory ``src`` in the current working directory and
    the directory ``/opt/notebook-utils``.

    If you call

      .. code:: python

        liveimport.workspace()  # No paths given

    the workspace is empty, so only modules referenced by registered imports
    will be tracked.

    .. note::
        Changing the workspace does not alter tracking decisions LiveImport has
        already made.  It only affects future decisions.  If you want a
        non-default workspace, its best to change it before registering any
        imports.
    """
    global _WORKSPACE

    workspace:list[Path] = []

    for dir in directories:

        path = _absolute(dir)

        if not path.exists():
            raise ValueError(f"Path {path} does not exist")

        if not path.is_dir():
            raise ValueError(f"Path {path} is not a directory")

        workspace.append(path)

    _WORKSPACE[:] = workspace

    # Local import to break circular import dependency
    from ._core import _track_new_indirects
    _track_new_indirects()

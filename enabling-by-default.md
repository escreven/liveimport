## Enabling by Default

LiveImport is enabled in a notebook session when it is first imported.  That
means by default the first cell of a notebook cannot usefully be a
`%%liveimport` or `#_%%liveimport` cell.  However, you can change that by
using IPython profiles to enable LiveImport at startup.

First, use the `ipython` command to [create a profile](https://ipython.readthedocs.io/en/stable/config/intro.html)
if you don't have one.  You can create a default profile with

```sh
$ ipython profile create
```

On Linux and macOS, this normally creates a profile directory

    ~/.ipython/profile_default/

and on Windows

    ``%USERPROFILE%\.ipython\profile_default\``

Your profile directory should contain a file `ipython_config.py`.  Add to that
file these lines:

```python
    import importlib.util as _liveimport_importlib_util
    if _liveimport_importlib_util.find_spec("liveimport") is not None:
        c.InteractiveShellApp.exec_lines.append("import liveimport")
    del _liveimport_importlib_util
```

This code causes IPython to import `liveimport` when a notebook session
starts before any cell is run, as long as `liveimport` is installed in the
environment in which the notebook is running.  The first cell of a notebook can
then be a `%%liveimport` cell, and notebooks using LiveImport need not
include a `import liveimport` statement at all.

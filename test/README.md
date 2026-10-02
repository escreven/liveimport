## Organization

### Test support

| File | Description
| - | -
| [main.py](main.py) | Command line test runner
| [setup.py](setup.py) | Creates a module hierarchy used by tests; enables tests to modify modules and determine reload outcomes
| [setup_imports.py](setup_imports.py) | A variety of import statements referencing the module hierarchy created by `setup.py`; every module defining tests includes a `from setup_imports import *` line so that each has the same palette of import statements and names to use

Tests are run by executing `main.py` from the command line.

```console
python3 test/main.py
```

Use option `-h` to see usage.


### Test definition

| File | Functional Area
| - | -
| [bootstrap.py](bootstrap.py) | Bootstrap cell handling
| [coreapi.py](coreapi.py) | Registration and syncing fundamentals
| [deleted.py](deleted.py) | Graceful handling of deleted modules
| [dependencies.py](dependencies.py) | Inter-module dependencies
| [integration.py](integration.py) | Notebook integration
| [lazy.py](lazy.py) | Lazy imports
| [notimported.py](notimported.py) | Detecting unexecuted import statements
| [obscurities.py](obscurities.py) | Hard to create conditions
| [order.py](order.py) | Statement order guarantees
| [plaindir.py](plaindir.py) | Namespace packages
| [relative.py](relative.py) | Relative imports
| [workspace.py](workspace.py) | Workspaces

Test definition modules include one or more functions

```
def test_<name>():
    ...
```

The test runner (`main.py`) executes these functions.

Special cases:

* There are no functions of the above form in `dependencies.py`.  Instead,
  there are top-level invocations of `_define()` creating `test_...` names in
  the `dependencies` module dictionary.  This elides what would otherwise be
  repetitive code.

* When run by Python 3.15 or greater, `integration.py` has two test functions,
  `test_notebook()` and `test_notebook_lazy()`.  These functions run cells of
  [notebook.ipynb](notebook.ipynb) and
  [notebook-lazy.ipynb](notebook-lazy.ipynb) to test notebook integration
  features.  The tests are defined in the notebook's code cells, which contain
  both normal Python code and special declarations such as `#@ reload mod2`
  indicating the cell output should include a `mod2` reload notification.  When
  run by Python <3.15, only function `test_notebook()` is present.


### Other

| File | Description
| - | -
| [notebook.ipynb](notebook.ipynb) | Notebook run by `integration.py` with general notebook integration tests
| [notebook-lazy.ipynb](notebook.ipynb) | Notebook run by `integration.py` with lazy import specific tests
| [dependencies.gv](dependencies.gv) | Graphviz model of module dependencies used by `dependencies.py`

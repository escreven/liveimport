Automatically reload modified Python modules in notebooks and scripts.

## Overview

LiveImport eliminates the need to restart a notebook's Python server to
reimport code under development in external files.  Suppose you are maintaining
symbolic math code in ``symcode.py``, LaTeX formatting utilities in
``printmath.py``, and a simulator in ``simulator.py``.  In the first cell of a
notebook, you might write

```python
import liveimport
import numpy as np
import matplotlib.pyplot as plot
```
and in the second
```python
%%liveimport --clear
import symcode
from printmath import print_math, print_equations as print_eq
from simulator import *
```

When the ``%%liveimport`` cell is run, LiveImport executes and registers the
import statements.  Thereafter, whenever you run cells, LiveImport will reload
any of ``symcode``, ``printmath``, and ``simulator`` that have changed since
registration or their last reload.  LiveImport deems a module changed when its
source file modification time changes.

LiveImport also updates imported module symbols.  For example, if you modify
``printmath.py``, LiveImport will reload ``printmath`` and bind ``print_math``
and ``print_eq`` in the global namespace to the new definitions.  Similarly, if
you update ``simulator.py``, LiveImport will create or update bindings for
every public symbol in ``simulator`` — that is, every symbol defined in the
module that does not start with ``_``, unless there is an ``__all__`` property
defined for the module, in which case it acts on only those symbols, just like
``from simulator import *``.

Modules referenced by registered import statements are called tracked modules.
LiveImport analyzes top-level import dependencies between tracked modules to
ensure reloading is consistent with those dependencies.  Suppose ``simulator``
imports ``symcode``.  Then, if you modify ``symcode.py``, LiveImport reloads
``simulator`` after it reloads ``symcode`` even if ``simulator.py`` has not
changed.  If you do modify both, LiveImport takes care to reload ``symcode``
first.

## Hidden Cell Magic

Unfortunately, Visual Studio Code and possibly other environments do not
analyze magic cell content, making ``%%liveimport`` use awkward.  However,
LiveImport includes a workaround: calling `hidden_cell_magic(True)` causes
``#_%%liveimport`` lines at the beginning of cells to act just like
``%%liveimport`` when the cell is run, and since ``#_%%liveimport`` is a Python
comment, Visual Studio Code and other environments do analyze the content.

A complete hidden cell magic example equivalent to the first begins with cell

```python
import liveimport
import numpy as np
import matplotlib.pyplot as plot
liveimport.hidden_cell_magic(True)
```
followed by cell
```python
#_%%liveimport --clear
import symcode
from printmath import print_math, print_equations as print_eq
from simulator import *
```

## Programmatic Interface

The LiveImport API includes programmatic registration, explicit syncing, and
configuration of LiveImport's notification and automatic syncing behavior.  In
addition to offering fine control within a notebook, the API enables
applications to use LiveImport outside of notebook environment.

## Documentation

For more details including an API reference see
[liveimport.readthedocs.io](https://liveimport.readthedocs.io).

## Installation

You can install LiveImport from PyPI with

```sh
$ pip install liveimport
```

You can also clone the repository and install it directly.

```sh
$ git clone https://github.com/escreven/liveimport.git
$ cd liveimport
$ pip install .
```

LiveImport requires Python 3.10 or greater and IPython 7.23.1 or greater.

## Reliability

LiveImport includes automated tests with 100% code coverage, which are run on
MacOS, Linux, and Windows with Python 3.10, 3.11, 3.12, 3.13, and 3.14 using
both the oldest supported and latest versions of IPython.  Notebook integration
features are tested using notebook 5.7.0 and notebook latest.  See [the GitHub
workflow](https://github.com/escreven/liveimport/blob/main/.github/workflows/test.yml)
for details.

If you have a copy of the source, you can run the tests yourself with

```sh
$ python test/main.py
```

## Questions or Issues

If you have any questions or encounter any issues, please submit them
[on GitHub](https://github.com/escreven/liveimport/issues).

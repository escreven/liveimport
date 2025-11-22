## Overview

LiveImport reliably and automatically reloads Python modules in Jupyter
notebooks.  Unlike IPython's autoreload extension, LiveImport reloads are
well-defined, deterministic operations that follow the semantics of a
developer's import statements exactly.  It maintains consistency between
modules by automatically reloading dependent modules as needed, ensuring
up-to-date references across a notebook and its modules.

LiveImport is designed for developers who interactively build Jupyter notebooks
together with external Python code, and who want predictable reloading with
minimal mystery.

Given a cell like

```python
%%liveimport
from common import *
from nets import ConvNet, ResidualNet as ResNet
import hyperparam as hp
```

LiveImport will execute the import statements, then automatically reload
``common``, ``nets``, or ``hyperparam`` whenever their source files change.
When LiveImport reloads, it will rebind symbols in the notebook as described by
the import statements.  If ``nets`` imports from ``hyperparam``, then when
``hyperparam`` is modified, LiveImport will automatically reload ``nets`` after
``hyperparam``.

To make the cell above transparent to IDEs like Visual Studio Code, you can
hide the cell magic:

```python
#_%%liveimport
from common import *
from nets import ConvNet, ResidualNet as ResNet
import hyperparam as hp
```

Hidden cell magic is a user experience feature tailored for modern notebook
development.  Others include protection against reloading in the middle of
multi-cell runs and optional reload notification.

If you currently use autoreload, you might consider [comparing LiveImport
to autoreload](https://github.com/escreven/liveimport/blob/main/comparison/Comparison.md).

## Documentation

See [liveimport.readthedocs.io](https://liveimport.readthedocs.io) for a user
guide and an API reference.

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

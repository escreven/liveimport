LiveImport
==========

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

.. code-block:: python

    %%liveimport
    from common import *
    from nets import ConvNet, ResidualNet as ResNet
    import hyperparam as hp

LiveImport will execute the import statements, then automatically reload
``common``, ``nets``, or ``hyperparam`` whenever their source files change.
When LiveImport reloads, it will rebind symbols in the notebook as described by
the import statements.  If ``nets`` imports from ``hyperparam``, then when
``hyperparam`` is modified, LiveImport will automatically reload ``nets`` after
``hyperparam``.

To make the cell above transparent to IDEs like Visual Studio Code, you can
hide the cell magic:

.. code-block:: python

    #_%%liveimport
    from common import *
    from nets import ConvNet, ResidualNet as ResNet
    import hyperparam as hp

Hidden cell magic is a user experience feature tailored for modern notebook
development.  Others include protection against reloading in the middle of
multi-cell runs and optional reload notification.

The :doc:`User Guide <userguide>` describes how to use LiveImport in notebooks,
and the :doc:`API Reference <api>` provides more details.  If you currently use
autoreload, you might consider the :doc:`Comparison with Autoreload
<comparison>`.

See :doc:`Installation <installation>` to get started.


.. toctree::
    :maxdepth: 2
    :hidden:
    :caption: Contents:

    userguide
    api
    comparison
    installation
    issues
    tips

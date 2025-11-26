.. currentmodule:: liveimport

Tips
----

.. _managing_state:

Managing State
~~~~~~~~~~~~~~

LiveImport manages dependencies between tracked modules, but not between
tracked modules and individual code cells.  Suppose in your notebook you have
cell

  .. code:: python

      #_%%liveimport --clear
      import models
      import hyperparam
      import orchestrate

and another cell

  .. code:: python

      # Build the network
      hp = hyperparam.HyperParam(blocks=6, label_smoothing=0.05)
      net = models.PreActResidualNet(hp)

Then, as it does with any cell, whenever you run the "Build the network" cell,
LiveImport reloads ``models`` and ``hyperparam`` if they've changed before the
cell executes.

Now suppose you have a third cell:

  .. code:: python

      # Train the network
      orchestrate.train(hp,net)

When you run this third cell without also running the "Build the network" cell,
``models`` and ``hyperparam`` will reload if they have changed, but ``hp`` and
``net`` will not be updated.  That may be what you wish; notebook users are
generally used to managing state in a notebook explicitly.  But if you would
like LiveImport to manage that reconstruction for you, move the "Build the
network" cell code to a Python file, perhaps ``managed_state.py`` with content

  .. code:: python

      import models
      import hyperparam
      hp = hyperparam.HyperParam(blocks=6, label_smoothing=0.05)
      net = models.PreActResidualNet(hp)

and change your ``%%liveimport`` cell to

  .. code:: python

      #_%%liveimport --clear
      import models
      import hyperparam
      import orchestrate
      from managed_state import hp, net

Then, when you run the "Train the network" cell, LiveImport will reload (if
needed) ``hyperparam``, ``models``, and ``managed_state`` in that order,
resulting in up-to-date ``hp`` and ``net`` references.

If you don't require ``models`` or ``hyperparam`` elsewhere in your notebook,
you can safely remove them from the ``%%liveimport`` cell.  Liveimport will
still :ref:`track <tracked_modules>` them because they are imported by
``managed_state``.

Statements and Registrations
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

While the LiveImport API does not require executed and registered import
statements to be strictly identical, the results of reloading may be surprising
if they are not.  Since ``%%liveimport`` cell magic both executes and registers
import statements, it naturally ensures that identity.

If you choose to use :func:`register()` in a notebook instead of relying on
cell magic or you are using LiveImport outside a notebook, the recommended
practice is to place all imports for modules to be tracked together followed
immediately by a :func:`register()` call with the same import statement text
written as a multiline string.  That way maintaining identical executed and
registered import statements is easy.  Something like

  .. code:: python

      import torch
      import torch.nn as nn
      import torch.nn.functional as F
      import liveimport

      from netplot import plot_training
      import orchestration

      liveimport.register(globals(),"""
      from netplot import plot_training
      import orchestration
      """, clear=True)

Tailoring Reloads
~~~~~~~~~~~~~~~~~

Modules sometimes take action when they load that should be performed
differently or not at all when they reload.  Here is one approach:

    .. code:: python

        if "_did_initial_load" not in globals():
            _did_initial_load = True
            print("First load of module")
        else:
            print("Reloading module")

The code above should be at the top level of your module.  Because
``_did_initial_load`` is undefined on the first load, the ``if`` condition is
true, so the ``if`` body statements run.  On reloads, the ``if`` condition is
false, so the ``else`` body runs.

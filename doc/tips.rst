.. currentmodule:: liveimport

Tips
----

Indirect Dependees
~~~~~~~~~~~~~~~~~~

The :ref:`Dependency Analysis <dependency_analysis>` section of the user guide
describes LiveImport's managagement of dependencies between tracked modules.
However, a module is only tracked if there is a registered import for it.
Consider these imports.

  .. code:: python

      #_%%liveimport --clear
      import symcode
      from printmath import print_math, print_equations as print_eq
      from simulator import *

If there were a fourth module, ``trace``, imported by ``simulator``, and you
edited ``trace.py``, neither ``trace`` nor ``simulator`` would reload because
``trace`` is not tracked.  The solution is simple: add ``trace`` to the
``%%liveimport`` cell even though you don't use it in the notebook.

  .. code:: python

      #_%%liveimport --clear
      import symcode
      from printmath import print_math, print_equations as print_eq
      from simulator import *
      import trace

If ``trace`` conflicts with an existing notebook symbol name, use the ``import
trace as ...`` import form.

.. _managing_state:

Managing State
~~~~~~~~~~~~~~

LiveImport manages dependencies between tracked modules, but not between
tracked modules and individual code cells.  Suppose in your notebook you have
cell

  .. code:: python

      #_%%liveimport --clear
      from models import PreActResidualNet
      import hyperparam
      import orchestrate

and another cell

  .. code:: python

      # Build the network
      hp = hyperparam.HyperParam(blocks=6, label_smoothing=0.05)
      net = PreActResidualNet(hp)

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
like LiveImport to manage that reconstruction for you, put the "Build the
network" cell content in a separate file, perhaps ``managed_state.py`` with the
content

  .. code:: python

      from models import PreActResidualNet
      import hyperparam
      hp = hyperparam.HyperParam(blocks=6, label_smoothing=0.05)
      net = PreActResidualNet(hp)

And change your ``%%liveimport`` cell to

  .. code:: python

      #_%%liveimport --clear
      from models import PreActResidualNet
      import hyperparam
      import orchestrate
      from managed_state import hp, net

Then, when you run the "Train the network" cell, LiveImport will reload (if
needed) ``hyperparam``, ``models``, and ``managed_state`` in that order,
resulting in up-to-date ``hp`` and ``net`` references.

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

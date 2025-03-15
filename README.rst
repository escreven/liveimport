Automatically reload modified Python modules in notebooks and scripts.

Overview
--------

LiveImport eliminates the need to restart a notebook's Python server to
reimport code under development in external files.  Suppose you are maintaining
symbolic math code in ``symcode.py``, LaTex formatting utilities in
``printmath.py``, and a simulator in ``simulator.py``.  In the first cell of a
notebook, you might write

  .. code:: python

      import liveimport
      import numpy as np
      import matplotlib.plot as plot

      import symcode
      from printmath import print_math, print_equations as print_eq
      from simulator import *

      liveimport.register(globals(),\"\"\"
      import symcode
      from printmath import print_math, print_equations as print_eq
      from simulator import *
      \"\"\", clear=True)

Then, whenever you run cells, LiveImport will reload any of ``symcode``,
``printmath``, and ``simulator`` that have changed since they were registered
or last reloaded.  LiveImport deems a module changed when its source file
modification time changes.

LiveImport also updates imported module symbols.  For example, if you modify
``printmath.py``, LiveImport will reload ``printmath`` and bind ``print_math``
and ``print_eq`` in the global namespace to the new definitions.  Similarly, if
you update ``simulator.py``, LiveImport will create or update bindings for
every public symbol in ``simulator`` — that is, every symbol defined in the
module that does not start with ``_``, unless there is an ``__all__`` property
defined for the module, in which case it acts on only those symbols, just like
``from simulator import *``.

Modules referenced by registered import statements are called tracked modules.
The process of bringing registered imports up to date by reloading tracked
modules and updating symbols is called syncing.

LiveImport analyzes top-level import [#f1]_ dependencies between tracked
modules to ensure reloading is consistent with those dependencies.  Suppose
``simulator`` imports ``symcode``.  Then, if you modify ``symcode.py``,
LiveImport reloads ``simulator`` after it reloads ``symcode`` even if
``simulator.py`` has not changed.  If you do modify both, LiveImport takes care
to reload ``symcode`` first.

Recommended Practice
--------------------

While LiveImport does not require executed and registered import statements to
be identical, the results of reloading may be surprising if they are not.

The ``clear=True`` option shown in the example above causes `register()`:func:
to discard all prior import registrations targeting the given namespace.  So,
if you wanted to stop tracking modifications to ``symcode.py``, you could
simply delete ``import symcode`` from the `register()`:func: `importstmts`
argument and rerun the cell.

Considering the previous two paragraphs, the recommended practice is to place
all imports for modules to be tracked together in an initial cell followed
immediately by a `register()`:func: call with ``clear=True`` and the same
import statement text written as a multiline string.  That way maintaining
identical executed and registered import statements is simple, and rerunning
the notebook makes registrations consistent with what appears in the notebook.
The example follows this form.

Cell Magic
----------

As an alternative, LiveImport defines a cell magic ``%%liveimport`` which both
executes the cell content and registers every top-level import statement.
Option ``--clear`` of ``%%liveimport`` has the same effect as ``clear=True``
with `register()`:func:.  So, you could split the example cell above into two,
making the second

  .. code:: python

      %%liveimport --clear
      import symcode
      from printmath import print_math, print_equations as print_eq
      from simulator import *

No `register()`:func: call is required.  Unfortunately, Visual Studio Code and
possibly other environments do not analyze magic cell content, making
``%%liveimport`` use awkward.  However, there is a workaround: calling
`hidden_cell_magic(enabled=True)<hidden_cell_magic>`:func: causes
``#_%%liveimport`` lines at the beginning of cells to act just like
``%%liveimport`` when the cell is run, and since ``#_%%liveimport`` is a Python
comment, Visual Studio Code and other environments do analyze the content.

A complete cell magic example equivalent to the first begins with cell

  .. code:: python

      import liveimport
      import numpy as np
      import matplotlib.plot as plot
      liveimport.hidden_cell_magic(enabled=True)

which is followed by cell

  .. code:: python

      #_%%liveimport --clear
      import symcode
      from printmath import print_math, print_equations as print_eq
      from simulator import *

Additional Information
----------------------

You can use LiveImport outside of notebook environments, but in that case,
there is no automatic syncing, so you must call `sync()`:func: explicitly.  You
can also disable automatic syncing in a notebook by calling
`auto_sync(enabled=False) <auto_sync>`:func: and rely on explicit syncing
instead.

Modules sometimes take action when they load that should be performed
differently or not at all when they reload.  Here is one approach:

  .. code:: python

      try:
          _did_initial_load    #type:ignore
          print("Reloading module")
      except NameError:
          _did_initial_load = True
          print("First load of module")

.. [#f1] A "top-level import" is any ``import ...`` or ``from ... import ...``
   statement in Python source that is not nested within another Python
   construct such as an ``if`` or ``try`` statement.

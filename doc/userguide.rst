.. currentmodule:: liveimport

User Guide
==========

Overview
--------

LiveImport eliminates the need to restart a notebook's Python kernel to
reimport code under development in external files.  Suppose you are maintaining
symbolic math code in ``symcode.py``, LaTeX formatting utilities in
``printmath.py``, and a simulator in ``simulator.py``.  In the first cell of a
notebook, you might write

  .. code:: python

      import liveimport
      import numpy as np
      import matplotlib.pyplot as plot

and in the second

  .. code:: python

      %%liveimport
      import symcode
      from printmath import print_math, print_equations as print_eq
      from simulator import *

When the ``%%liveimport`` cell is run, LiveImport executes and registers the
import statements.  Thereafter, whenever you run cells, LiveImport will reload
any of ``symcode``, ``printmath``, and ``simulator`` that have changed since
registration or their last reload.  LiveImport deems a module changed when its
source file modification time changes.

LiveImport also updates imported module names.  For example, if you modify
``printmath.py``, LiveImport will reload ``printmath`` and bind ``print_math``
and ``print_eq`` in the global namespace to the new definitions.  Similarly, if
you modify ``simulator.py``, LiveImport will create or update bindings for
every public name in ``simulator`` (where public means in ``__all__`` if
present, and not starting with ``_`` otherwise.)

Importantly, LiveImport *only* updates names in the same way the original
import statements would.  If your notebook and ``symcode`` both happened to
define a variable ``gamma``, reloading ``symcode`` would not overwrite your
notebook's value of ``gamma``.  Though it isn't implemented this way, you can
think of LiveImport as re-executing the registered import statements when a
module reloads.

Hidden Cell Magic
-----------------

As it turns out, Visual Studio Code and possibly other environments do not
analyze magic cell content, making ``%%liveimport`` use awkward.  However,
LiveImport has a simple solution: ``#_%%liveimport`` lines at the beginning of
cells act just like ``%%liveimport`` when the cell is run, and since
``#_%%liveimport`` is a Python comment, Visual Studio Code and other
environments do analyze the content.

To use hidden cell magic with the example above, replace the second cell with

  .. code:: python

      #_%%liveimport
      import symcode
      from printmath import print_math, print_equations as print_eq
      from simulator import *

If you prefer, you can disable hidden cell magic by calling
:func:`hidden_cell_magic(enabled=False) <hidden_cell_magic>`.

.. _tracked_modules:

Tracked Modules
---------------

Modules that are monitored by LiveImport for modification are called tracked
modules.  The process of bringing registered imports up to date by reloading
tracked modules and updating names is called syncing.

There are two ways a module becomes tracked.  First, it can be referenced by a
registered import statement.  In the **Overview** example, ``symcode``,
``printmath``, and ``simulator`` are all tracked modules.  Second, a module in
LiveImport's workspace (described below) that is referenced by a top-level
import in a tracked module is itself tracked.

For example, suppose there is a module ``timeutils`` in the workspace that is
imported by ``simulator``.  Then, even if ``timeutils`` is not mentioned in any
way in the notebook, LiveImport will track ``timeutils``.  If you edit
``timeutils.py``, LiveImport will reload ``timeutils``, then reload
``simulator``, then rebind the names imported from ``simulator`` in the
notebook.

The second tracked module determination rule (being referenced by a tracked
module's top-level import statement) is transitive.  If ``timeutils`` imports
``units``, and ``units`` is also in the workspace, then LiveImport will track
``units``.

.. _workspace:

LiveImport's workspace is a set of directories.  A module is in the workspace
if its Python source file is under any of those directories.  The default
workspace is a single directory, the current working directory when LiveImport
is first imported. Unless you change it, that is the directory containing your
notebook.  So, by default, any Python source files alongside your notebook are
in LiveImport's workspace.  You can change the workspace by calling
:func:`workspace()`.

The workspace determines only which modules are candidates for tracking because
of top-level imports from other tracked modules.  Modules referenced by
registered import statements are always tracked, regardless of the workspace.

Dependency Analysis
-------------------

LiveImport analyzes top-level import dependencies between tracked modules to
ensure reloading is consistent with those dependencies and to prevent stale
references between modules.

Suppose ``simulator`` imports ``x`` from ``symcode`` where ``x`` is defined in
``symcode.py`` as

  .. code:: python

     x = sympy.Symbol("x", positive=True)

If you realize the assumption about symbolic variable ``x`` being positive is
unwarranted and change the line to

  .. code:: python

     x = sympy.Symbol("x")

``simulator`` must be reloaded — and reloaded after ``symcode`` — otherwise it
would still refer to the old definition of ``x`` with the assumption of
positivity.  ``simulator``'s evaluations involving ``x`` would be incorrect.

Fortunately, LiveImport's dependency aware reloading does exactly that.  When
you modify ``symcode.py``, LiveImport reloads ``simulator`` after it reloads
``symcode`` even if ``simulator.py`` has not changed.  If you do modify both,
LiveImport takes care to reload ``symcode`` first.  No stale references are
created.

Registration Details
--------------------

While ``%%liveimport`` cells often contain only import statements, they can
actually contain any valid Python code.  For example,

  .. code:: python

      #_%%liveimport
      from models import ConvNet
      from orchestrate import *  # Includes default_learning_rate
      print(f"Default learning rate is {default_learning_rate}")

When a ``%%liveimport`` cell is run, LiveImport first executes the Python
source.  If execution completes without an exception, LiveImport extracts from
the cell the top-level import statements.  It then registers those statements
and begins tracking the related modules, if they are not already tracked.

LiveImport imposes no restrictions on the registered import statements: the
statements can overlap, they can repeat, they can be any kind of import
statement that is legal to use in a notebook.  For example, the following cell
is perfectly fine.

  .. code:: python

      #_%%liveimport
      from symcode import x, hermite_poly
      from symcode import x, lagrange_poly as lp
      from symcode import *
      import symcode as sc, simulator
      from utils.latex_support import (QUAD,
          REAL_NUMBERS as R)

Normally, ``%%liveimport`` cells are additive and idempotent.  Top-level import
statements are registered by merging them with prior registrations.  The
``%%liveimport`` cell magic's one optional argument ``--clear`` (or the short
form, ``-c``) changes that — it causes LiveImport to discard all prior import
registrations when the cell is run.

Best Practice
-------------

The recommended practice is for notebooks to have one ``%%liveimport`` cell,
and that cell should include option ``--clear``.  In the case of the
**Overview** example, if you are hiding cell magic, that one cell would be

  .. code:: python

      #_%%liveimport --clear
      import symcode
      from printmath import print_math, print_equations as print_eq
      from simulator import *

This way, if you want to stop tracking modifications to ``symcode.py``, you can
simply delete ``import symcode`` and rerun the containing cell.  If you do have
multiple ``%%liveimport`` cells, then it's best if the first (and only the
first) uses option ``--clear``.

Reload Reports
--------------

By default, LiveImport displays Markdown console blocks to report when it
automatically reloads modules in a notebook, something like

  .. code:: console

      Reloaded symcode modified 18 seconds ago
      Reloaded simulator because symcode reloaded

You can disable these reports by calling
:func:`auto_sync(report=False)<auto_sync>`.

Import Statement Order
----------------------

LiveImport name rebinding is consistent with import statement execution order.  Consider a notebook with cell

  .. code:: python

      #_%%liveimport --clear
      from highlight import *
      from formatutil import *

where both ``highlight`` and ``formatutil`` both define a name ``red``.
Whenever that cell runs, the ``from formatutil import *`` statement executes
second, so Python binds ``red`` in the global namespace to ``formatutil.red``.
To match that behavior, if you modify ``highlight.py``, LiveImport reloads
``highlight``, but does *not* rebind ``red`` to ``highlight.red`` — it remains
bound to ``formatutil.red``.  If you modify ``formatutil.py``, LiveImport
reloads ``formatutil`` and rebinds ``red`` to ``formatutil``'s possibly new
value.

Overall execution order is what counts.  Suppose the cell above is split into
two and the ``--clear`` option is removed:

  .. code:: python

      #_%%liveimport
      from highlight import *

and

  .. code:: python

      #_%%liveimport
      from formatutil import *

If you run the notebook top down, LiveImport will again preserve
``formatutil``'s value for ``red`` when it reloads ``highlight``.  But if you
re-run just the first cell, Python binds ``red`` to ``highlight.red``, and
LiveImport will now rebind ``red`` to ``highlight.red`` when it reloads
``highlight``.

Top-Level Imports
-----------------

A top-level import is any ``import ...`` or ``from ... import ...`` statement
in Python source that is not nested within another Python construct such as an
``if`` or ``try`` statement.

  .. code:: python

      import colors
      if _need_debug:
          from debug import *
      def report(data):
          from formatutil import layout
          generate_table(layout,data)
      from common import epilogue

In the code above, ``import colors`` and ``from common import epilogue`` are
the only two top-level import statements.  LiveImport only processes top-level
imports in Python source.  That affects both registration through
``%%liveimport`` cells and module dependency tracking.

If it's essential for your application, you can use the API to implement
conditional imports that are registered.  There is an example in the next
section.

Programmatic Registration
-------------------------

As an alternative to ``%%liveimport`` cell magic, you can register import
statements by calling :func:`register()<register>`.  Unlike ``%%liveimport``
cell magic, :func:`register()` does not execute the import statements it
registers, so you must do so before calling :func:`register()`.  The cell below
is equivalent to the **Overview** example.

  .. code:: python

      import liveimport
      import numpy as np
      import matplotlib.pyplot as plot

      import symcode
      from printmath import print_math, print_equations as print_eq
      from simulator import *

      liveimport.register(globals(),"""
      import symcode
      from printmath import print_math, print_equations as print_eq
      from simulator import *
      """, clear=True)

While cell magic is far more convenient, programmatic registration might be
useful if your notebook conditionally imports modules you wish to automatically
reload, something like

  .. code:: python

      from packaging.version import Version

      if Version(sympy.__version__) < Version("1.13"):
          from sympyshim import groups_count
          liveimport.register(globals(),"from sympyshim import groups_count")
      else:
          from sympy.combinatorics.group_numbers import groups_count

Managing Synchronization
------------------------

In order to avoid reloading modules between cell executions of a multi-cell run
(such as when running all cells), LiveImport suppresses module modification
checks for a grace period after each cell execution. The default grace period
is one second.  You can change the grace period by calling
:func:`auto_sync(grace=...) <auto_sync>`.

You can also disable automatic syncing altogether by calling
:func:`auto_sync(enabled=False) <auto_sync>` and rely on explicit syncing
through calls to :func:`sync()` instead.

Outside of Notebooks
--------------------

You can use LiveImport outside of notebook environments, but in that case, you
must use programmatic registration and explicitly sync via
:func:`register()` and :func:`sync()` respectively.

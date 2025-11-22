
Tips
----

While the LiveImport API does not require executed and registered import
statements to be strictly identical, the results of reloading may be surprising
if they are not.  Since the ``%%liveimport`` cell magic both executes and
registers import statements, it naturally ensures that identity.

If you choose to use `register()`:func: in a notebook instead of relying on
cell magic or you are using LiveImport outside a notbook, the recommended
practice is to place all imports for modules to be tracked together followed
immediately by a `register()`:func: call with the same import statement text
written as a multiline string.  That way maintaining identical executed and
registered import statements is simple.

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

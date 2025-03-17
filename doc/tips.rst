
Tips
----

While LiveImport does not require executed and registered import statements to
be identical, the results of reloading may be surprising if they are not.
Since the ``%%liveimport`` cell magic both executes and registers import
statements, it naturally ensures that identity.  

If you choose to use `register()`:func: in a notebook instead of relying on
cell magic or you are using LiveImport outside a notbook, the recommended
practice is to place all imports for modules to be tracked together followed
immediately by a `register()`:func: call with the same import statement text
written as a multiline string.  That way maintaining identical executed and
registered import statements is simple.

When using either ``%%liveimport`` magic or `register()`:func: calls in a
notebook, it's best if the first use in the notebook includes option
``--clear`` or ``clear=True`` respectively.  If it does, rerunning the notebook
makes LiveImport registrations consistent with what appears in the notebook.  

Modules sometimes take action when they load that should be performed
differently or not at all when they reload.  Here is one approach:

    .. code:: python
    
        try:
            _did_initial_load    #type:ignore
            print("Reloading module")
        except NameError:
            _did_initial_load = True
            print("First load of module")
    
The code above should be at the top level of your module.  Because
``_did_initial_load`` is undefined on the first load, the exception handling
code runs.  On reloads, the ``try`` primary path runs normally.

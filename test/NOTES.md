
Need to verify the minimum Python version required.  Probably 3.10.

Need to determing the range of IPython versions supported.

Somethings that are still not tested.

* Calling auto_sync() and hidden_cell_magic() outside of notebook.  They have
  trivial code paths so very unlikely to have issues, but should add it for completeness.

* Operating with multiple namespaces.

* Reloading liveimport itself, especially in a notebook environment.
  Specifically make sure that assumption about register_magics() being reload
  safe is correct.

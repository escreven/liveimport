# liveimport-autoload

This package consists solely of an IPython startup file that imports
[LiveImport](https://github.com/escreven/liveimport) when IPython or Jupyter
kernels start in the Python environment.  That enables notebooks to use
`%%liveimport` or `#_%%liveimport` in their very first cell without a bootstrap
import.

Install it through LiveImport's `autoload` extra:

```console
$ pip install "liveimport[autoload]"
```

To turn autoloading off, uninstall the package:

```console
$ pip uninstall liveimport-autoload
```

By default, `liveimport-autoload` causes LiveImport to be imported into every
IPython or Jupyter kernel.  To disable that import for a kernel without
uninstalling, set `LIVEIMPORT_NO_AUTOLOAD=1` in the kernel's environment before
it starts.

See [liveimport.readthedocs.io](https://liveimport.readthedocs.io) for
details.

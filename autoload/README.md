# liveimport-autoload

This package installs an IPython startup file that imports [LiveImport](https://github.com/escreven/liveimport)
whenever an IPython or Jupyter kernel starts in the environment. With it,
notebooks can use `%%liveimport` in their very first cell without a bootstrap
import.

Install it through LiveImport's `autoload` extra:

```console
$ pip install "liveimport[autoload]"
```

To turn autoloading off, uninstall this package:

```console
$ pip uninstall liveimport-autoload
```

To disable it for a single kernel without uninstalling, set
`LIVEIMPORT_NO_AUTOLOAD=1` in the kernel's environment.

The startup file is placed in `etc/ipython/startup` under the environment's
prefix, so it applies to every kernel using that environment.

See [liveimport.readthedocs.io](https://liveimport.readthedocs.io) for
details.

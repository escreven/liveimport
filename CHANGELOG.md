## Unreleased

#### Changed
- [Coverage](https://coverage.readthedocs.io/en/7.16.1/) option ``--branch`` is
  now used for the `op.sh` coverage reports and GitHub workflows, strengthening
  code coverage assurance.
- IPython kernel warnings during testing are suppressed.
- Replaced rebind journal with an import record journal as part of preparing
  for Python 3.15 lazy imports.
- Check to determine if a registered import statement has already executed is
  now slightly stricter: all modules in a hierarchy must be loaded.  For
  example, "from a.b.c import x" requires "a", "a.b", and "a.b.c" to be loaded.

#### Fixed
- Manually reloading LiveImport consistently resets all state.  (This is only
  useful for testing since reloading LiveImport requires reloading the
  implementation modules as well as the public module, all in the correct
  order.)
- Extraneous op.sh command line arguments are disallowed.
- The decision to track module "a.b.c.x" when "from a.b.c import x" is
  registered is now based on whether or not attribute "x" of module "a.b.c" is
  the loaded module "a.b.c.x".  Previously, it was determined by whether or not
  attribute "x" of module "a.b.c" was any module.

## [1.2.6] - 2026-09-04

#### Added
- ``%%liveimport`` cell magic now permits ``#``-delimited comments on the cell
  magic line.  Contributed by [@lukas-lang](https://github.com/lukas-lang) ([#41](https://github.com/escreven/liveimport/pull/41)).
- LiveImport now recognizes ``#WS_%%liveimport`` as hidden cell magic, where
  ``WS`` is any sequence of spaces and tabs.  Example: ``# _%%liveimport``.
  Contributed by [@lukas-lang](https://github.com/lukas-lang) ([#42](https://github.com/escreven/liveimport/pull/42)).
- Guidance on enabling LiveImport by default using IPython profiles.  Based on
  feedback from [@lukas-lang](https://github.com/lukas-lang).


## [1.2.5] - 2026-03-02

#### Added
- `workspace()` now accepts path-like objects as well as strings.

#### Fixed
- `workspace()` now normalizes `/..` directory components enabling relative
  workspace directory paths.


## [1.2.4] - 2026-01-23

#### Fixed
- `register()` parameter `allow_other_statements` documented.
- Avoid recording multiple dependencies between a given pair of modules.


## [1.2.3] - 2025-12-09

#### Changed
- Defer displaying reload reports when executing what are likely frontend
  bootstrap cells until executing a user cell in the same run.  This lets
  VSCode users see reload reports when debugging.


## [1.2.2] - 2025-12-02

#### Changed
- Permit module origin files to have any extension (but only `.py` files are
  tracked).

#### Fixed
- Support for namespace packages.
- Graceful handling of source files deleted between import and registration.


## [1.2.1] - 2025-12-01

#### Fixed
- Correct message for exception when evidence of import execution is missing
  during statement registration.


## [1.2.0] - 2025-11-28

#### Added
- Workspaces.
- Tracking indirectly import modules.
- Name rebinding following import statement order
- Rebind module names as well as names defined by modules.

#### Changed
- Refactored source, converting from a single to multi-file module.
- Handle file deletions gracefully.  `sync()` now bypasses missing source files
  instead of raising an exception.  This avoids forcing a notebook user to
  restart the kernel as they refactor their modules.
- Use terminology "name" instead of "symbol".


## [1.1.0] - 2025-11-22

#### Changed
- Cell magic now hidden by default.
- Module docstring content mostly moved to `doc/index.rst`.


## [1.0.3] - 2025-11-21

#### Added
- Expanded documentation.
- A `comparison/` directory comparing LiveImport and the IPython autoreload
  extension.

#### Changed
- The `enabled` parameter of `auto_sync()` and `hidden_cell_magic()` are no
  longer keyword-only.

## [1.0.2] - 2025-06-07

#### Fixed

- `register(...,clear=True)` or `%%liveimport --clear` now clear only
  registrations for the target namespace.


## [1.0.1] - 2025-03-29

#### Fixed
- Handle missing `_IPYTHON_SHELL`.

## [1.0.0] - 2025-03-29

First stable release.

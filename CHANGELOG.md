## Unreleased

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

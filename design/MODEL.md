## LiveImport Data Model

### Roots

* `_NAMESPACE_TABLE: dict[int, _NamespaceInfo]` &mdash; keyed by id(namespace)
* `_MODULE_TABLE: dict[str, _ModuleInfo]` &mdash; by module name
* `_REIFY_WATCH: set[str]` &mdash; module names

### Types
![LiveImport state fields, object containment, and indirect namespace and
module relationships.](model-diagram.svg)

### Key

| Diagram Element | Meaning |
| --------------- | ------- |
| Solid arrow | Direct object reference |
| Dashed arrow | Lookup through IDs or names, rather than direct reference |
| Filled diamond tail | Referring object owns referenced object |
| `1` on arrow label | Exactly one reference |
| `0..*` on arrow label | Zero or more references |
| `*..*` on arrow label | Many to many relationship |

### Notes

`_ModuleInfo.attachedto` stores namespace dictionary IDs, not `_NamespaceInfo`
object references. Those IDs resolve through `_NAMESPACE_TABLE`.

`_ModuleInfo.dependencies` stores candidate module names, not `_ModuleInfo`
object references.

* A dependency becomes tracked (the named module has a `_MODULE_TABLE`
entry) only if and when the module is loaded and has a source file in the
workspace.  Some modules listed in `dependencies` might not even exist: `from A
import B` in tracked module `M` adds `A.B` to `M`'s dependency list because
`A.B` might exist in the future even if it doesn't exist now.

* A dependency on a lazily imported module has an entry in `_REIFY_WATCH`

`_ImportRecord.modulename` identifies a Python module via `sys.modules`.

`_NamespaceInfo.namespace` is the target for rebind actions when the associated
import journal is applied.  When using LiveImport in a notebook, this is the
notebook's `globals()`.  When using the API directly, it can be any dictionary.

There is a difference between the internal notion of a tracked module (a module
has a _ModuleInfo entry in _MODULE_TABLE) and a user's view.  A module is
tracked from a user's perspective if and only if it has a _ModuleInfo entry in
_MODULE_TABLE *and* the module is attached to a namespace.  The second
condition means removing all registrations referencing a module prevents it
from reloading.

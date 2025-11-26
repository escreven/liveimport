## Comparison to Autoreload

While the IPython autoreload extension is useful and widely known, LiveImport
is different from autoreload in ways that may make it a better fit for many
notebook workflows.

### Consistency

The overriding philosophy of LiveImport is that reloading must be a
well-defined, deterministic operation that follows the semantics of a
developer's import statements exactly.  It uses dependency awareness to
maintain consistency and makes no guesses.  It does not mutate existing
objects, and instead rebinds names to fresh definitions.

Autoreload attempts to preserve existing object references by patching function
and class definitions in place, and uses name-based heuristics for rebinding.
It does not provide import statement equivalent semantics, and it accepts that
partial updates and inconsistencies will occur.

Given the notebook import

```python
from netplot import baseline_color, learning_rate_color as lrc, plot_training
```

LiveImport will rebind ``baseline_color``, ``lrc`` and ``plot_training`` and
nothing else when it reloads ``netplot``.  If ``plot_training`` is a function
and the colors are values (perhaps strings), autoreload patches
``plot_training``, does not rebind ``baseline_color`` in its explicit mode, and
never rebinds ``lrc`` in any mode.

Moreover, if both ``netplot`` and your notebook define ``trace_mode``
variables, autoreload in complete mode will overwrite your notebook's
``trace_mode`` variable when it reloads ``netplot``, even though you haven't
imported ``trace_mode`` from ``netplot``.

Autoreload's approach can also lead to stale references between modules.  For
example, if ``orchestrate.py`` imports from ``netplot`` in the same way as
above, plots created by ``orchestrate.train()`` would not use updated colors.
In contrast, LiveImport would reload ``orchestrate`` after ``netplot`` changed
in order to update ``orchestrate``'s references to ``netplot``.

One advantage of autoreload's patching approach is that an existing class
instance immediately reflects changes made to its methods.  While that can be
useful, it's hard to always get right as a user, since new versions of methods
must be made to work correctly with existing instance state.  LiveImport
doesn't patch; existing instances keep their old method definitions.  (But see
[Managing State](
https://liveimport.readthedocs.io/en/latest/tips.html#managing-state).)

### User Experience

LiveImport avoids reloading between cell executions of multi-cell runs.  That
way, your running notebook codebase is frozen, even if you happen to modify a
file during a run.  Autoreload checks for modified files before every cell
execution, meaning function and class definitions can change in the middle of a
run.

LiveImport's hidden cell magic allows you to take full advantage of your IDE in
code cells.  With autoreload, unless your IDE has special support for
``%aimport`` line magic (Visual Studio Code does not), using autoreload's
explicit mode makes your coding less productive.

By default, LiveImport notifies you when it reloads modules by displaying
Markdown blocks such as

```console
    Reloaded symcode modified 36 seconds ago
    Reloaded simulator because symcode reloaded
```

While you can disable notifications, they help avoid wasting time when
unexpected reloads happen, or expected reloads do not.  Autoreload is
silent.

### Explore

[This directory](.) contains small notebooks and modules
along with a step-by-step README if you would like to investigate
the differences between LiveImport and autoreload yourself.


### Introduction

The files in this directory are used to compare the behaviors of LiveImport and
the IPython autoreload extension.

Notebooks `using-liveimport.ipynb` and `using-autoreload.ipynb` are similar,
differing only in which mechanism is used to automatically reload.

Files `alpha.py`, `beta.py`, `gamma.py`, `delta.py`, and `epsilon.py` are
modules to be imported and automatically reloaded into the notebooks.  They
each include a `<module>_tag` global variable to be manually updated to
generate reloads (incrementing is recommended).  Those tags plus other
variables, functions, and classes in the modules are used to observe the
outcome of reloads.

The notebooks have four sections

1. **Setup** — Configuring automatic imports and other initialization

2. **Print** — A cell that prints the module tags and other values, used
   to see the effect of reloading.

3. **Existing Instance** — Cells for experimenting with an existing class
   instance.

4. **Multi-cell Run** — A pair of cells meant to be run together.

### Preparation

The autoreload extension has four operating modes: `off`, `explicit`, `all`,
and `complete`.  We will begin the comparison with autoreload in `explicit`
mode, then discuss `all` and `complete` further down.

Open `using-autoreload.ipynb` and make sure you see

```python
%autoreload explicit
```

If instead you see

```python
%autoreload complete  # ... or off, or all
```

change it to `explicit`.

Also, open `epsilon.py` and make sure the lines of the `__init__()` and
`__str__()` methods of class `Epsilon` referencing field `self.another` or
including the word "CHANGED" are commented out.

Ensuring all tag values in `alpha.py`, `beta.py`, etc. are `1` is recommended,
but not required.  (It makes reloading effects easier to follow.)

### Recommended Comparison Steps

#### Step 1:

Open both `using-liveimport.ipynb` and `using-autoreload.ipynb`.  If they are
already open, and you've already run cells, restart the kernels.

If you are using VSCode or a similar IDE, see if the IDE understands that
module `alpha` is imported.  VSCode understands `alpha` is imported in the
LiveImport notebook; when you mouse over a reference to `alpha_tag`, VSCode
indicates it's a variable defined in `alpha` with type `int`.  VSCode doesn't
understand that `alpha` is imported in the autoreload notebook.  That's because
the LiveImport magic is hidden (see the `#_%%liveimport --clear` line), while
autoreload magic is not.  Other IDEs may differ.

#### Step 2:

Run all cells in both notebooks.  (It will take about 10 seconds because the
**Multi-cell Run** section includes a `sleep()` call used later.)  You should
see the initial tag values in the **Print** section of both notebooks.

#### Step 3:

Increment `alpha_tag` in `alpha.py`. Remember to save!  Rerun the **Print**
cell in both notebooks.  While the new `alpha_tag` values are now shown
in the cell output of both notebooks, there are important differences.

First, LiveImport notified you that it reloaded modules, displaying a Markdown
block like

```console
Reloaded alpha modified 22 seconds ago
Reloaded beta because alpha reloaded
```

The autoreload notebook included no such notification.  When you are working on
a notebook, being suprised by a reload — or being surprised by a *non*-reload —
can waste time.  If you don't like LiveImport's notification blocks, you can
turn them off by calling `liveimport.auto_sync(report=False)`.

Second, LiveImport didn't just reload `alpha`, it reloaded `beta`.  Why?
Because `beta` imports `alpha_tag`, `alpha_fn()`, and `Alpha` from `alpha`.
LiveImport tracks top-level dependencies between modules it imports,
automatically reloading dependent modules as well as modified modules.

Reloading `beta` refreshes the references from `beta` to `alpha`.  You can see
evidence of this in LiveImport's **Print** output: the `beta.alpha_tag`, and
the output of `alpha_fn()`, and `Alpha()` called and constructed from `beta`
all show `alpha`'s new tag value.

Autoreload takes a different approach.  When it reloads, it patches the old
in-memory definitions of functions and classes to make them look like the new
definition.  That way existing references to those functions and classes remain
valid.  However, this strategy is incomplete.

Examine the autoreload notebook **Print** cell output. While the output of
`alpha_fn()`, and `Alpha()` called and constructed from `beta` show `alpha`'s
new tag value, `beta.alpha_tag` does not.  There is now an inconsistency
between the in-memory versions of `alpha` and `beta` that could lead to hard to
understand behavior.

#### Step 4:

Examine the **Setup** section of the LiveImport notebook.  It's divided into
two cells, the second starting with the comment `#_%%liveimport --clear`.  That
marks the cell as a LiveImport hidden magic cell, enabling both LiveImport and
your IDE to process the cell contents correctly.  You don't have to use hidden
cell magic; normal cell magic `%%liveimport --clear` works too.

Now examine the **Setup** section of the autoreload notebook.  Only one cell is
needed because autoreload uses line magic.  While that's nice, there are two
issues

1. The line magic isn't hidden, and (as discussed in Step 1), some
IDEs don't understand what `%aimport` means.

2. `%aimport` arguments are module names, not general Python import statements.
`%aimport` does not, for example, support `from <module> import ...`.

We try to work around issue (2) by having both the import statement we want and
an `%aimport` mentioning that same module.  In the LiveImport notebook we don't
have to do that: LiveImport supports every legal Python import statement.

Let's test the autoreload workaround.  Increment `gamma_tag` in `gamma.py`.
That will also update a variable `gamma_second` in `gamma.py`.  The
relevant import statement is

```python
from gamma import gamma_tag, gamma_second as gs, gamma_fn, Gamma
```

What we hope is that on reload the notebooks see updated `gamma_tag` and `gs`
values, and `gamma_fn()` and `Gamma` called and constructed from the notebook
show the new values.  Run the **Print** cell in both notebooks to see what
happens.

LiveImport correctly updates `gamma_tag`, `gs`, `gamma_fn`, and `Gamma`.

Autoload does not update `gamma_tag` or `gs`.  That's because in `explicit`
mode, autoreload does not rebind imported variables. Mode `complete` does
update bindings, but inexactly.  In this case, it would change the binding of
`gamma_tag` but not the binding of `gs`.  More on this inexactness later.

Autoreload does patch the definitions of `gamma_fn()` and `Gamma`, but does
so incorrectly.  The relevant output is

```console
Notebook calls gamma_fn()=gamma_fn: tag=2; second=1
Notebook constructs Gamma<tag=2; second=1>
[gamma.gamma_second=1]
```

The tag value is correct, but the second value, which should be a copy of the
tag, is not.  The bracketed output shows the value of `gamma_second` in
`gamma`'s module dictionary.  The autoreload patching machinery has discarded
the change to gamma_second.  (However, the change is kept in `complete` mode.)

#### Step 5:

One advantage of autoreload's patching approach is that updates can change the
definition of existing class instances.  Examine the output of the second
**Existing Instance** cell in both notebooks.  You should see something like

```console
an_epsilon=Epsilon<tag=1>
```

Notice the second cell prints an existing instance of `Epsilon`.  Now increment
`epsilon_tag` in `epsilon.py` and uncomment the "CHANGED" line in the `__str__`
method.  Rerun the second (and only the second) cell in the **Existing
Instance** section.

The LiveImport notebook output is unchanged.  While it reloaded module
`epsilon` and rebound `Epsilon` to the new class definition, the existing
instance was unaffected.

In the autoreload notebook we have something different.

```console
an_epsilon=Epsilon<tag=1; CHANGED>
```

The `__str__` method of the existing instance was patched by `autoreload`.
That could be good in many cases, but here it is mixed.  While the code
changed, the state of the instance remained the same, so the result of
converting an instance to a string does not reflect the new tag value.
Furthermore, try uncommenting the lines referencing `self.another` and
rerunning again.  Now the cell fails because the code references a field which
is not defined in the instance.

Patching classes with existing instances can be helpful, but existing instance
state limits its utility and predictability.

#### Step 6:

This step is timing critical.  We are going to see what happens when a module
is modified while a notebook is running multiple cells.  Get ready to edit
`alpha.py`.  Before making any change, start running in the LiveImport notebook
from the first **Multi-cell Run** cell down ("Run Selected Cell and All Below"
in the standard Jupyter notebook menu).  The first cell will run for 10
seconds.  During that 10 seconds, before the cell finishes, change `alpha_tag`
in `alpha.py`.  Repeat this process for the autoreload notebook.

Now compare the output.  In the LiveImport notebook, the `alpha_tag` values
displayed by the first and second cells in the **Multi-cell Run** section are
the same.  This happens because LiveImport suppresses automatic reloading
during multi-cell runs using a grace period.  (See `liveimport.auto_sync()` in
the API documentation.)

The autoreload notebook output shows two different values for `alpha_tag`
because the autoreload extension reloads before every cell execution.  While
there may be cases where that's desirable, a frozen codebase during a run
is generally best.

### Other Modes

Above we tested using autoreload's `explicit` mode.  What happens with `all`
or `complete`?  The documentation for `all` says

> Reload all modules (except those excluded by %aimport) every time before executing the Python code typed.

That means we could have written the **Setup** cell as

```python
import sys
import time
common_name = "Value from notebook"

%load_ext autoreload
%autoreload all
import alpha
import beta
from gamma import gamma_tag, gamma_second as gs
import delta
import epsilon
```

The nice thing is VSCode would now be happy.  The cost is we need negative
`%aimport -<module>` lines for modules we don't want to automatically reload.
All the other autoreload behavior described so far remains the same.

LiveImport does not have a "automatically reload all" mode.  For one thing,
organizing notebook code with the relevant imports placed in cells with hidden
or non-hidden magic is not inconvenient.  For another, LiveImport tracks
modules reached by chains of imports, meaning fewer import statements are
required in the notebook.  But most importantly, placing those imports in
designated cells means LiveImport sees the actual Python import statements, and
so can fully process them on reload.

Mode `complete` is

> Same as 2/all, but also adds any new objects in the module.

That means autoreload attempts to rebind relevant notebook variables when
reloading modules.  We mentioned that in **Step 4**, and also described it as
inexact.  Let's explore further.

#### Step 7:

First, change the **Setup** section line of the autoreload notebook from

```python
%autoreload explicit
```
to
```python
%autoreload complete
```

Next, restart the LiveImport and autoreload notebook kernels.  Run all cells in
both.

Consider the **Setup** section in the notebooks and also `delta.py`.  They all
define variables, functions, and classes called `common_int` `common_str`,
`common_fn`, and `Common`.  The notebook definitions assign 0 to `common_int`
and use the phrase "in notebook" in the others.  The `delta.py` definitions
assign 99 to `common_int` and use the phrase "in delta.py" for the others.

The notebooks do not import any names from `delta`, so naturally the lines we
see in the **Print** output of both notebooks for these names are

```console
Notebook sees common_int=0
Notebook sees common_str=string in notebook
Notebook calls common_fn: in notebook
Notebook constructs Common<class in notebook>
```

Now, increment `delta_tag` in `delta.py`, then rerun the **Print** cell
in both notebooks.

The LiveImport notebook output remains unchanged, as desired.  But
surprisingly, we see in the autoreload notebook

```console
Notebook sees common_int=99
Notebook sees common_str=Common string in delta.py
Notebook calls common_fn: in notebook
Notebook constructs Common<class in notebook>
```
In its attempt to rebind names in the notebook that are possibly imported
from `delta`, autoreload overwrote `common_int` and `common_str` in the
notebook just because they have the same name as variables in `delta`.

LiveImport doesn't make this mistake because it parses the Python import
statements for the modules it is to manage, and uses those statements to
determine which names to rebind (and which to leave alone.)

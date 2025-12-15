from __future__ import annotations
from argparse import ArgumentParser
import sys
import time
from nbconvert.preprocessors import ExecutePreprocessor
from nbformat import NotebookNode
from traitlets.config import Config
import nbformat
import os
import re
import coverage

#
# This module tests LiveImport's notebook integration.  It runs the cells of
# notebook.ipynb which must be in the same directory as this and the other test
# modules, including setup.py and setup_imports.py.
#
# Function test_notebook uses this module's __file__ attribute (which it must
# have) to locate the test notebook, and set the notebook's working directory.
#
# NOTE: Someday we will use nbclient instead of nbconvert.  But for now, we
# want to be able to test with older versions of libraries.
#

#
# Declarations extracted from the source of one code cell.
#

_PRESLEEP_DECL_RE  = re.compile(r"#@\s*presleep\s+([0-9.]+)\s*")
_RELOAD_DECL_RE    = re.compile(r"#@\s*reload\s+(\w+)\s*")
_ERROR_DECL_RE     = re.compile(r"#@\s*error\s+(\w+)\s*")
_MISSINGOK_DECL_RE = re.compile(r"#@\s*missingok\s*")

class _Declarations:

    __slots__ = "reloads", "errors", "missingok", "presleep"

    reloads   : list[str]
    errors    : list[str]
    missingok : bool
    presleep  : float

    def __init__(self, cell:NotebookNode):
        self.reloads   = []
        self.errors    = []
        self.missingok = False
        self.presleep  = 0.0

        for line in cell.source.split('\n'):
            if line.startswith("#@"):
                if (match := _RELOAD_DECL_RE.fullmatch(line)):
                    self.reloads.append(match[1])
                elif (match := _ERROR_DECL_RE.fullmatch(line)):
                    self.errors.append(match[1])
                elif (match := _MISSINGOK_DECL_RE.fullmatch(line)):
                    self.missingok = True
                elif (match := _PRESLEEP_DECL_RE.fullmatch(line)):
                    try:
                        self.presleep = float(match[1])
                    except ValueError:
                        raise RuntimeError(
                            "Bad presleep declaration: " + line)
                else:
                    raise ValueError(
                        "Bad declaration in notebook code cell: " + line)

    def permits(self, found:_Found):
        return (self.reloads   == found.reloads and
                self.errors    == found.errors and
                self.missingok == (not found.ok))


#
# Portions of the output of one executed code cell relevant to the tester.
#

_RELOADED_LINE_RE = re.compile(r"^Reloaded (\w+) ")

class _Found:

    __slots__ = "reloads", "errors", "ok"

    reloads : list[str]
    errors  : list[str]
    ok      : bool

    def __init__(self, cell:NotebookNode):
        self.reloads = []
        self.errors  = []
        self.ok      = False

        for output in cell.outputs:
            otype = output.output_type
            if otype == 'display_data':
                if (text := output.data.get('text/markdown')) is not None:
                    if text == "OK":
                        self.ok = True
                    else:
                        for line in text.split('\n'):
                            if (match := _RELOADED_LINE_RE.match(line)):
                                self.reloads.append(match[1])
            elif otype == 'error':
                self.errors.append(output.ename)

#
# textwrap.indent() doesn't handle blank lines the way we want.
#

def _indent(s:str):
    lines = s.rstrip().split('\n')
    return '\n'.join("    " + line for line in lines)


#
# Execute a notebook under test, verifying what is declared in the notebook to
# be expected.
#

class _TestbenchPreprocessor(ExecutePreprocessor):

    __slots__ = "verbose"

    def __init__(self, config:Config, verbose:bool):
        super().__init__(kernel_name="python3",config=config)
        self.verbose = verbose

    def preprocess_cell(self, cell:NotebookNode, resources, index):

        if cell.cell_type != 'code':
            return super().preprocess_cell(cell,resources,index)

        decls = _Declarations(cell)

        if decls.presleep > 0:
            time.sleep(decls.presleep)

        try:
            cell, resources = super().preprocess_cell(cell,resources,index)
            error = None
        except BaseException as ex:
            error = ex

        found = _Found(cell)
        good  = error is None and decls.permits(found)

        if self.verbose or not good:
            print()
            print(f"--------------CELL {index}--------------")
            print()
            print("Source:")
            print()
            print(_indent(cell.source))
            print()
            print("Declarations:")
            print(f"    reloads={decls.reloads}")
            print(f"     errors={decls.errors}")
            print(f"  missingok={decls.missingok}")
            print(f"   presleep={decls.presleep}")
            print()
            print("Found:")
            print(f"    reloads={found.reloads}")
            print(f"     errors={found.errors}")
            print(f"         ok={found.ok}")

        if not good:
            print()
            sys.stdout.flush()
            if error is not None:
                raise RuntimeError("Unexpected notebook cell error") from error
            else:
                raise RuntimeError("Unexpected notebook output")

        return cell, resources


#
# We modify the notebook under test in up to three ways after reading it.
#
#   1. Remove all output.  The notebook as stored in the repository should have
#      no output, but we clear it just in case.
#
#   2. Append "SCRIPTED_TEST = True" to the setup cell of the notebook.  The
#      setup cell must be the second cell in the notebook, must be a code cell,
#      and must include the line "SCRIPTED_TEST = False".  The appended line
#      means tests in the notebook can differentiate between manual execution
#      and scripted execution.
#
#   3. If and only if code coverage is being measured, prepend code in the
#      setup cell to start measurement within the notebook, and append a cell
#      to save the result.  Remember that the notebook runs in a different
#      process, so coverage must be initiated separately.
#

_SCRIPTED_FALSE_RE = re.compile(
    r'^SCRIPTED_TEST\s*=\s*False\s*$',
    re.MULTILINE)

_COVERAGE_START = """
import coverage
coverage_object = coverage.Coverage(
    data_file="../.coverage.notebook",
    include="../src/liveimport/*.py")
coverage_object.start()
"""

_COVERAGE_END = """
coverage_object.stop()
coverage_object.save()
ok()
"""

def _prepare(nb:NotebookNode):

    for cell in nb.cells:
        if hasattr(cell,'outputs'):
            cell.outputs.clear()

    if (len(nb.cells) < 2 or
        (setup_cell := nb.cells[1]).cell_type != 'code' or
        not _SCRIPTED_FALSE_RE.search(setup_cell.source)):
            raise RuntimeError("Did not find setup cell")

    coverage_active = coverage.Coverage.current() is not None

    source = _COVERAGE_START if coverage_active else ''
    source += setup_cell.source
    source += '\nSCRIPTED_TEST = True\n'
    setup_cell.source = source

    if coverage_active:
        nb.cells.append(nbformat.v4.new_code_cell(_COVERAGE_END))


def test_notebook(verbose:bool=False):
    """
    Verify notebook integration.
    """
    if '__file__' not in globals():
        raise RuntimeError("Notebook integration test requires __file__")

    dir = os.path.dirname(__file__)
    if not dir: dir = '.'
    filename = dir + '/notebook.ipynb'

    config = Config()
    config.InteractiveShell.colors = 'NoColor'

    nb = nbformat.read(filename,as_version=4)
    _prepare(nb)

    _TestbenchPreprocessor(config, verbose).preprocess(
        nb, resources={ "metadata": { "path": dir } })

    return nb


#
# One can run this module directly, if desired.  This is useful to debug
# integration.py itself.
#

if __name__ == '__main__':

    from argparse import ArgumentParser

    parser = ArgumentParser(
        description="Verbosely test liveimport notebook integration")

    parser.add_argument("-verbose",action="store_true",
        help="Print detailed information for every cell")

    args = parser.parse_args()

    test_notebook(args.verbose)

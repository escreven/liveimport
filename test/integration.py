from argparse import ArgumentParser
import time
from nbconvert.preprocessors import ExecutePreprocessor
from nbformat import NotebookNode
from traitlets.config import Config
import nbformat
import os
import re

#
# TODO: Verify all declarations work
# TODO: Consider restructuring so all test activity happens preprocess_cell.
#

#
# This module tests LiveImport's notebook integration.  It runs the cells of
# notebook.ipynb which be in the same directory as this and the other test
# modules, including common.py. 
#
# Function uses this module's __file__ attribute (which it must have) to locate
# the test notebook, and set the notebook's working directory/
#
# NOTE: Someday we will use nbclient instead of nbconvert.  But for now, we
# want to be able to test with older versions of libraries.
#

if os.name == 'nt':
    # Python, be better.
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


_PRESLEEP_DECL_RE  = re.compile(r"#@\s*presleep\s+([0-9.]+)\s*")
_RELOAD_DECL_RE    = re.compile(r"#@\s*reload\s+(\w+)\s*")
_ERROR_DECL_RE     = re.compile(r"#@\s*error\s+(\w+)\s*")
_MISSINGOK_DECL_RE = re.compile(r"#@\s*missingok\s*")


class SleepableExecutePreprocessor(ExecutePreprocessor):
    def preprocess_cell(self, cell:NotebookNode, resources, index):
        if cell.cell_type == 'code':
            sleep = 0.0
            for line in cell.source.split('\n'):
                if (match := _PRESLEEP_DECL_RE.fullmatch(line)):
                    try:
                        sleep = max(sleep,float(match[1]))
                    except ValueError:
                        raise RuntimeError(
                            "Bad presleep declaration: " + line)
            if sleep > 0:
                time.sleep(sleep)
        cell, resources = super().preprocess_cell(cell,resources,index)
        return cell, resources


def _clear_output(nb:NotebookNode):
    for cell in nb.cells:
        if hasattr(cell,'outputs'):
            cell.outputs.clear()


def _run_notebook(filename:str, dir:str):

    config = Config()
    config.InteractiveShell.colors = 'NoColor'

    nb = nbformat.read(filename,as_version=4)
    _clear_output(nb)

    if (len(nb.cells) < 2 or
    (setup_cell := nb.cells[1]).cell_type != 'code' or 
    not re.search(r'^SCRIPTED_TEST\s*=\s*False\s*$',
                    setup_cell.source, re.MULTILINE)):
        raise RuntimeError("Did not find setup cell")
    
    setup_cell.source += '\nSCRIPTED_TEST = True\n'

    SleepableExecutePreprocessor(kernel_name="python3", 
                                 config=config).preprocess(
        nb, resources={ "metadata": { "path": dir } })
    return nb


def _indent(s:str):
    # textwrap.indent() doesn't handle blank lines the way we want.
    lines = s.rstrip().split('\n')
    return '\n'.join("    " + line for line in lines)


class _Expect:
    reloads   : list[str]
    errors    : list[str]
    missingok : bool

    def __init__(self, source:str):
        self.reloads = []
        self.errors  = []
        self.ok      = True

        for line in source.split('\n'):
            if line.startswith("#@"):
                if (match := _RELOAD_DECL_RE.fullmatch(line)):
                    self.reloads.append(match[1])
                elif (match := _ERROR_DECL_RE.fullmatch(line)):
                    self.errors.append(match[1])
                elif (match := _MISSINGOK_DECL_RE.fullmatch(line)):
                    self.ok = False
                elif _PRESLEEP_DECL_RE.fullmatch(line):
                    # Already processed
                    pass
                else:
                    raise ValueError(
                        "Bad declaration in notebook code cell: " + line)
                

_RELOADED_LINE_RE = re.compile(r"^Reloaded (\w+) ")

class _Actual:
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


def test_notebook(verbose:bool=False):
    """
    Verify notebook integration.
    """
    if '__file__' not in globals():
        raise RuntimeError("Notebook integration test requires __file__")
    
    dir = os.path.dirname(__file__)
    if not dir: dir = '.'
    filename = os.path.dirname(__file__) + '/notebook.ipynb'

    nb = _run_notebook(filename,dir)

    for i, cell in enumerate(nb.cells):
        if cell.cell_type == 'code':
            expect = _Expect(cell.source)
            actual = _Actual(cell)
            good = (expect.reloads == actual.reloads and 
                    expect.errors  == actual.errors and
                    expect.ok == actual.ok)
            if verbose or not good:
                print()
                print(f"--------------CELL {i}--------------")
                print()
                print("Source:")
                print()
                print(_indent(cell.source))
                print()
                print("Expected:")
                print(f"    reloads={expect.reloads}")
                print(f"     errors={expect.errors}")
                print(f"         ok={expect.ok}")
                print()
                print("Actual:")
                print(f"    reloads={actual.reloads}")
                print(f"     errors={actual.errors}")
                print(f"         ok={actual.ok}")
            if not good:
                print()
                raise RuntimeError("Notebook integration test failed")


#
# One can run this module directly, if desired.  This is mostly used to debug
# notebook interaction.
#

if __name__ == '__main__':
    
    from argparse import ArgumentParser

    parser = ArgumentParser(
        description="Verbosely test liveimport notebook integration")

    parser.add_argument("-verbose",action="store_true",
        help="Print detailed information for every cell")
    
    args = parser.parse_args()    

    test_notebook(args.verbose)

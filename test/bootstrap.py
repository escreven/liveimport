from __future__ import annotations
import os
import textwrap
import time
import coverage
from jupyter_client import KernelManager  #type:ignore

#
# This module tests LiveImport's handling of bootstrap cells.  A bootstrap cell
# is non-user cell frontends run in the kernel for its own purposes, usually
# related to configuring the environment in some way.  VSCode, for example,
# imports a debugger module in a bootstrap cell before running a user cell in
# debug mode.
#
# LiveImport judges a cell to be bootstrap its store_history option is False.
# Note a frontend can, and probably should, use the silent=True option when
# running bootstrap cells because that bypasses run_cell event handlers
# altogether -- unfortunately VSCode at least does not in its debugging
# support.
#
# While it would be simpler to use an in-process IPython shell here, we start a
# headless kernel instead to avoid any potential contamination of other tests
# from IPython state.
#

_TIMEOUT = 5.0

#
# Tracing is enabled when this module is run from the command line.
#

_trace_enable = False

def _trace(*s:str):
    if _trace_enable:
        print(" ".join(s))

def _trace_multiline(text:str):
    if _trace_enable:
        lines = text.splitlines()
        for line in lines:
            print(".... | " + line)

#
# Encapsulate an IPython kernel connection.
#

class _Kernel:

    __slots__ = "manager", "client", "counter"

    def __init__(self):
        """
        Create an IPython kernel having this module's source directory as its
        current working directory.
        """
        if '__file__' not in globals():
            raise RuntimeError("Bootstrap test requires __file__")

        dir = os.path.dirname(__file__)
        if not dir: dir = '.'

        self.manager = KernelManager(kernel_name='python3')
        self.manager.start_kernel(cwd=dir)

        self.client = self.manager.client()
        self.client.start_channels()
        self.client.wait_for_ready(timeout=_TIMEOUT)

        self.counter = 0

    def run_cell(self, code:str, store_history=True):
        """
        Send code to the kernel, setting the store_history option as specified.
        `run_cell()` returns the tuple (markdown,stdout), where both are lists
        of strings.  Other content is discarded.  If running the cell raises an
        exception in the kernel (including if code in the call raises an
        exception), `run_cell()` raises a `RuntimeError`.
        """
        code = textwrap.dedent(code)

        #
        # Send the request.
        #

        _trace("-------------------------------------------------")
        _trace(f"Send {repr(code)} sh={store_history}")

        client = self.client
        self.client.execute(code, silent=False,
                            store_history=store_history,
                            allow_stdin=False, stop_on_error=True)

        #
        # The kernel sends many messages in response
        #

        markdown:list[str] = []
        stdout:list[str]   = []

        while True:
            #
            # Wait for the next reply message.  Unfortunately, jupyter_client
            # fails with a non-public exception on timeout.
            #
            try:
                msg = client.get_iopub_msg(timeout=_TIMEOUT)
            except:
                raise RuntimeError(
                    "Message wait from kernel failed (timeout likely)")

            #
            # Dispatch the message.  There are only three things we care about:
            # receiving stdout (the cell printed something) or stderr text,
            # receiving markdown text (reloads are markdown), and when the
            # kernel becomes idle meaning it is done running the cell.
            #

            mtype   = msg['msg_type']
            content = msg['content']

            _trace(f"Recv mtype={mtype}")

            if mtype == 'stream':
                #
                # We have stream data that might be stdout.  Raise an exception
                # if it's anything else (like stderr).
                #
                name = msg['content']['name']
                text = msg['content']['text']
                _trace(f".... stream name={name}")
                if name == 'stdout':
                    _trace_multiline(text)
                    stdout.append(text)
                else:
                    raise RuntimeError(f"Unexpected stream: {name}")

            elif mtype == 'display_data':
                #
                # We have display data that might be markdown.
                #
                data = msg['content']['data']
                if 'text/markdown' in data:
                    text = data['text/markdown']
                    _trace(f".... markdown")
                    _trace_multiline(text)
                    markdown.append(text)

            elif mtype == 'status':
                state = content['execution_state']
                _trace(f".... state={state}")
                if state == 'idle':
                    #
                    # The kernel is done.  It also sends a reply message on a
                    # different queue when finished; get that message and raise
                    # a RuntimeError if running the cell failed with an
                    # exception.
                    #
                    reply = client.get_shell_msg(timeout=5.0)
                    content = reply['content']
                    if content['status'] == 'error':
                        _trace(f".... error")
                        for record in content['traceback']:
                            _trace_multiline(record)
                        raise RuntimeError(
                            "Exception raised in IPython kernel cell run: " +
                            content['ename'] + ": " + content['evalue'])
                    break

        return markdown, stdout

    def close(self):
        """
        Shutdown the kernel.
        """
        #
        # We ignore failures here for two reasons.
        #    1. Anything that goes wrong here is not a LiveImport issue, so
        #       the test should not fail.
        #    2. I have observed spurious jupyter_client errors during shutdown
        #       related to __del__ methods and GC.
        #
        try:
            self.client.stop_channels()
        except:
            pass
        try:
            self.manager.shutdown_kernel(now=True)
        except:
            pass

#
# Code coverage support.  Each test creates a new IPython kernel running
# in its own process.  Thus, each kernel must start coverage and save the
# resulting data to generate coverage reports.  Each kernel must
# write the data to a file specific to each test.
#

_COVERAGE_START = """
import coverage
coverage_object = coverage.Coverage(
    data_file="../.coverage.bootstrap-{name}",
    include="../src/liveimport/*.py")
coverage_object.start()
"""

_COVERAGE_END = """
coverage_object.stop()
coverage_object.save()
"""

def _coverage_start(kernel:_Kernel, name:str):
    """
    Inject a cell to start collecting coverage data if required.  Argument
    `name` must be specific to each test.
    """
    if coverage.Coverage.current():
        kernel.run_cell(_COVERAGE_START.format(name=name))

def _coverage_end(kernel:_Kernel):
    """
    Inject a cell to save coverage data if required.
    """
    if coverage.Coverage.current():
        kernel.run_cell(_COVERAGE_END)


def _preamble(kernel:_Kernel):
    """
    Common prefix of all tests.
    """
    kernel.run_cell("""
        import liveimport
        from setup import *
        from setup_imports import *
    """)
    kernel.run_cell("liveimport.auto_sync(grace=0.25)\n")
    kernel.run_cell("%%liveimport\nimport mod1\n")
    kernel.run_cell("mod1_tag = get_tag('mod1')\n")


def _touch(kernel:_Kernel):
    """
    Modify module mod1.
    """
    #
    # There is no point to sleeping on the kernel side.  Delays
    # between calls to run_cell are what matter.
    #
    kernel.run_cell("touch_module('mod1',sleep=0)\n")


def _bootstrap(kernel:_Kernel, expect_next_tag=False):
    """
    Run a simulated bootstrap cell.  Iff `expect_next_tag` is True, expect
    mod1's tag to have advanced, indicating mod1 reloaded.  In no case should
    there be reload notifications when the bootstrap cell runs.
    """
    code = "print('bootstrap')\n"
    if expect_next_tag:
        code += "expect_tag('mod1',next_tag(mod1_tag))\n"
    markdown, stdout = kernel.run_cell(code, store_history=False)
    assert 'bootstrap' in "".join(stdout)
    assert len(markdown) == 0


def _normal(kernel:_Kernel, expect_reload:bool):
    """
    Run a simulated normal user cell.
    """
    markdown, stdout = kernel.run_cell("print('normal')")
    assert 'normal' in "".join(stdout)
    if expect_reload:
        assert len(markdown) == 1
        assert "Reloaded mod1" in markdown[0]
    else:
        assert len(markdown) == 0


def test_deferred_report():
    """
    Reload reports should be deferred past bootstrap cells to the next normal
    cell that runs before the grace period expires.
    """
    kernel = _Kernel()
    try:
        _coverage_start(kernel,"defer")
        _preamble(kernel)
        _touch(kernel)
        time.sleep(0.5)
        _bootstrap(kernel, expect_next_tag=True)
        _normal(kernel, expect_reload=True)
        _coverage_end(kernel)
    finally:
        kernel.close()


def test_discarded_report():
    """
    Deferred reload reports should be discarded if the grace period expires
    before the next normal cell runs.
    """
    kernel = _Kernel()
    try:
        _coverage_start(kernel,"discard")
        _preamble(kernel)
        _touch(kernel)
        time.sleep(0.5)
        _bootstrap(kernel, expect_next_tag=True)
        time.sleep(0.5)
        _normal(kernel, expect_reload=False)
        _coverage_end(kernel)
    finally:
        kernel.close()

#
# bootstrap.py can be run from the command line.  That is useful for debugging
# bootstrap.py, and also tracing interaction with IPython kernels.
#
if __name__ == '__main__':
    _trace_enable = True
    test_deferred_report()
    test_discarded_report()

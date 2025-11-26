from argparse import ArgumentParser
import traceback
from types import FunctionType, ModuleType
import textwrap
import inspect
import sys
import re
import io
import liveimport
import common

# Modules defining tests:
import coreapi
import relative
import dependencies
import notimported
import obscurities
import integration
import workspace
import deleted


_Case = tuple[str,FunctionType]


def _get_cases(module:ModuleType) -> list[_Case]:
    mname = module.__name__
    result = []
    for name in dir(module):
        if name.startswith("test_"):
            value = getattr(module,name)
            if isinstance(value,FunctionType):
                if getattr(value,'__module__',None) == mname:
                    tname = name.removeprefix("test_")
                    result.append((mname + ':' + tname,value))
    return result


class _CapturedOutput():
    __slots__ = "buffer", "save_stdout", "save_stderr"

    def __init__(self):
        self.buffer = io.StringIO()

    def __enter__(self):
        sys.stdout.flush()
        sys.stderr.flush()
        self.save_stdout = sys.stdout
        self.save_stderr = sys.stderr
        buffer = self.buffer
        buffer.seek(0)
        buffer.truncate()
        sys.stdout = buffer
        sys.stderr = buffer

    def __exit__(self, exc_type, exc_value, traceback):
        sys.stdout = self.save_stdout
        sys.stderr = self.save_stderr

    def value(self):
        return self.buffer.getvalue()


def _test_always_fail():
    print("I am printed to stdout.")
    print("I am printed to stderr.",file=sys.stderr)
    def g(): raise RuntimeError("Intentional failure")
    def f(): g()
    f()


def main():

    parser = ArgumentParser(
        description="Test LiveImport")

    parser.add_argument("pattern", nargs='?', default=None,
        help="Only run tests containing this regex")

    parser.add_argument("-keeptemp", action="store_true",
        help="Keep the temporary directory created for testing")

    parser.add_argument("-reverse", action="store_true",
        help="Run tests in reverse order")

    parser.add_argument("-check-python", metavar="VERSION",
        help="Abort if not running specified Python version (Example: 3.10)")

    parser.add_argument("-check-ipython", metavar="VERSION",
        help="Abort if not using specified IPython version (Example: 7.23.1)")

    parser.add_argument("-failstop", action="store_true",
        help="Stop immediately on failure")

    parser.add_argument("-forcefail", action="store_true",
        help="Include a test that always fails")

    args = parser.parse_args()

    cases = [] if not args.forcefail else [
        ('main:always_fail', _test_always_fail) ]

    cases.extend(_get_cases(coreapi))
    cases.extend(_get_cases(relative))
    cases.extend(_get_cases(dependencies))
    cases.extend(_get_cases(notimported))
    cases.extend(_get_cases(obscurities))
    cases.extend(_get_cases(integration))
    cases.extend(_get_cases(workspace))
    cases.extend(_get_cases(deleted))

    if (pattern := args.pattern) is not None:
        cases = [ case for case in cases
                  if re.search(pattern,case[0]) ]

    if args.reverse:
        cases = list(reversed(cases))

    if args.keeptemp:
        common.keep_tempdir()

    env = common.describe_environment()

    if args.check_python and env['python'] != args.check_python:
        raise RuntimeError("Unexpected Python version")

    if args.check_ipython and env['ipython'] != args.check_ipython:
        raise RuntimeError("Unexpected IPython version")

    if len(cases) == 0:
        print()
        print("No tests match pattern")
        print()
        sys.exit(1)

    print()
    print(f"Running {len(cases)} tests")
    print()

    namewd = 2 + max(len(case[0]) for case in cases)
    correct = 0
    captured_output = _CapturedOutput()

    for name, fn in cases:
        liveimport._clear_all_module_info()
        liveimport.workspace(common.TEMPDIR)
        print("    " + name.ljust(namewd,'.'),end='',flush=True)
        try:
            with captured_output: fn()
            print("OK")
            correct += 1
        except BaseException as failure:
            print("FAILED")
            print()
            if (docstr := inspect.getdoc(fn)):
                print("Test Description:")
                print()
                print(textwrap.indent(docstr.rstrip(),"    "))
                print()
            if (output := captured_output.value()):
                print("Test Output:")
                print()
                print(textwrap.indent(output.rstrip(),"    "))
                print()
            print("Test Exception:")
            print()
            print(f"    {repr(failure)}")
            print()
            for frame in traceback.format_tb(failure.__traceback__)[1:]:
                print(textwrap.indent(frame.rstrip(),"    "))
            print()
            if args.failstop:
                sys.exit(1)

    print()
    print(f"{correct} out of {len(cases)} tests succeeded")
    print()

    if correct < len(cases):
        sys.exit(1)


if __name__ == '__main__':
    main()

#
# Setup
#

from argparse import ArgumentParser
import re
from types import FunctionType, ModuleType
import liveimport
import common

# Modules defining tests:
import coreapi
import relative
import dependencies
import notimported
import obscurities
import integration


_Case = tuple[str,FunctionType]


def _get_cases(module:ModuleType) -> list[_Case]:
    mname = module.__name__
    result = []
    for symbol in dir(module):
        if symbol.startswith("test_"):
            value = getattr(module,symbol)
            if isinstance(value,FunctionType):
                if getattr(value,'__module__',None) == mname:
                    tname = symbol.removeprefix("test_")
                    result.append((mname + ':' + tname,value))
    return result


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

    args = parser.parse_args()

    cases = []
    cases.extend(_get_cases(coreapi))
    cases.extend(_get_cases(relative))
    cases.extend(_get_cases(dependencies))
    cases.extend(_get_cases(notimported))
    cases.extend(_get_cases(obscurities))
    cases.extend(_get_cases(integration))

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

    print()
    print(f"Running {len(cases)} tests")
    print()

    namewd = 2 + max(len(case[0]) for case in cases)
    for name, fn in cases:
        print("    " + name.ljust(namewd,'.'),end='',flush=True)
        try:
            fn()
        except:
            print("FAILED")
            print()
            if (docstr := getattr(fn,'__doc__',None)) is not None:
                print(docstr)
                print()
            raise
        print("OK")
        liveimport.register(globals(),"",clear=True)

    print()
    print("All tests succeeded")


if __name__ == '__main__':
    main()

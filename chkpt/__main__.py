import sys
import os
from pathlib import Path

from . import Checkpoint


if __name__ == "__main__":
    import argparse
    import importlib.machinery
    import importlib.util
    import io

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--min-obj-size",
        "-z",
        type=int,
        default=1024 * 1024,
        help="Minimum size of object to capture. Pass 0 to capture all objects, and -1 to capture only tracked objects.",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        default=Path("./checkpoints"),
        help="Directory to place snapshots in.",
    )
    parser.add_argument(
        "--frequency",
        "-f",
        type=int,
        default=0,
        help="Frequency of checkpoints in ms. Pass 0 to capture once per executed line, and -1 to only capture when explicitly requested.",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="count",
        default=0,
        help="Repeat to increase verbosity.",
    )
    args, rest = parser.parse_known_args()

    if rest[0] == "--":
        rest = rest[1:]

    sys.argv = rest
    # import runpy
    # if options.module:
    #     code = "run_module(modname, run_name='__main__')"
    #     globs = {
    #         'run_module': runpy.run_module,
    #         'modname': args[0]
    #     }
    progname = sys.argv[0]
    sys.path.insert(0, os.path.dirname(progname))
    with io.open_code(progname) as fp:
        code = compile(fp.read(), progname, "exec")
    spec = importlib.machinery.ModuleSpec(name="__main__", loader=None, origin=progname)
    glbls = {
        "__spec__": spec,
        "__file__": spec.origin,
        "__name__": spec.name,
        "__package__": None,
        "__cached__": None,
    }
    loader = importlib.machinery.SourceFileLoader("__main__", progname)
    spec.loader = loader
    module = importlib.util.module_from_spec(spec)

    chkpt = Checkpoint(
        progname,
        args.min_obj_size,
        args.output_dir,
        args.frequency,
        args.verbose,
        main_mod=module,
    )
    chkpt.install()

    # Execute the code within it's own __main__ module - this allows libraries
    # like pickle to resolve imports against __main__ in the context of the
    # usercode, and not this shim.
    # Note that sys.modules["__main__"] in the user code will still point to the
    # chkpt main module which could still have some issues.
    spec.loader.exec_module(module)

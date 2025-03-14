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

    chkpt = Checkpoint(
        progname, args.min_obj_size, args.output_dir, args.frequency, args.verbose
    )

    print('chkpt.__main__', sys.modules['__main__'])
    chkpt.set_globals(glbls)
    chkpt.install()

    exec(code, glbls, None)

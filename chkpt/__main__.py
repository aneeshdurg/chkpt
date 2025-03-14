import sys
import os
from pathlib import Path

from . import Checkpoint


if __name__ == "__main__":
    import argparse
    import importlib.machinery
    import io

    parser = argparse.ArgumentParser()
    parser.add_argument("--min-obj-size", "-z", type=int, default=1024 * 1024)
    parser.add_argument("--output-dir", "-o", type=Path, default=Path("./checkpoints"))
    parser.add_argument(
        "--frequency", "-f", type=int, help="frequency of checkpoints in ms", default=0
    )
    parser.add_argument(
        "--verbose", "-v", help="verbosity level", action="count", default=0
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
    globs = {
        "__spec__": spec,
        "__file__": spec.origin,
        "__name__": spec.name,
        "__package__": None,
        "__cached__": None,
    }

    chkpt = Checkpoint(
        progname, args.min_obj_size, args.output_dir, args.frequency, args.verbose
    )
    chkpt.install()

    exec(code, globs, None)

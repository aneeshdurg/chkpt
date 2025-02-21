import sys
import inspect
import atexit
import time
import os
import pickle
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from types import CodeType
from typing import Any


@dataclass
class CheckpointArgs:
    min_obj_size: int
    output_dir: Path
    frequency: int
    verbosity: int


def install_hooks(tracee: str, args: CheckpointArgs):
    tracee = tracee
    min_capture_size = args.min_obj_size
    frequency = args.frequency
    verbosity = args.verbosity

    os.system(f"mkdir -p {args.output_dir}")

    # TODO - custom output dir
    file_prefix = urllib.parse.quote_plus(tracee)

    def log(lvl, *args):
        if verbosity >= lvl:
            # TODO - real logging with controllable verbosity
            print(" ", *args)

    def should_capture(v: Any) -> bool:
        sz = sys.getsizeof(v)
        if sz < min_capture_size:
            return False
        m = inspect.getmodule(type(v))
        if m is None:
            return False
        module_name = m.__name__

        if module_name == "builtins":
            if type(v) in [str, int, list, dict, set]:
                return True
        return module_name.startswith("pandas") or module_name.startswith("numpy")

    last_save = None

    def ready_to_capture():
        if frequency or last_save is None:
            return True
        now = time.time() * 1000
        if (now - last_save) >= frequency:
            return True

    def save(line_number, objs):
        nonlocal last_save
        ts = time.time()
        fname = f"chkpt.{file_prefix}.{line_number}@{ts}.pkl"
        for k in objs:
            log(1, f"  [save] {k} @ {ts} -> {fname}")
        with open(args.output_dir / fname, "wb") as f:
            pickle.dump(objs, f)
        last_save = ts

    def line_handler(code: CodeType, line_number: int) -> Any:
        if code.co_filename != tracee:
            return
        log(1, "[line_handler]", code, line_number)
        try:
            cf = inspect.currentframe()
            assert cf
            assert cf.f_back
            to_save = {}
            for n, v in cf.f_back.f_globals.items():
                if should_capture(v):
                    log(1, "  [global] add", n)
                    to_save[n] = v
                else:
                    log(1, "  [global] skip", n)
            for n, v in cf.f_back.f_locals.items():
                if n in cf.f_back.f_globals:
                    continue
                if should_capture(v):
                    log(2, "  [local] add", n)
                    if n in to_save:
                        log(2, "    overwrite!", n)
                    to_save[n] = v
                else:
                    log(2, "  [local] skip", n)
            save(line_number, to_save)
        except Exception as e:
            raise e

    sys.monitoring.use_tool_id(sys.monitoring.OPTIMIZER_ID, "dbg")
    sys.monitoring.set_events(
        sys.monitoring.OPTIMIZER_ID,
        sys.monitoring.events.PY_START
        | sys.monitoring.events.PY_RETURN
        | sys.monitoring.events.LINE,
    )
    # sys.monitoring.register_callback(
    #     sys.monitoring.OPTIMIZER_ID, sys.monitoring.events.PY_START, handler
    # )
    # sys.monitoring.register_callback(
    #     sys.monitoring.OPTIMIZER_ID, sys.monitoring.events.PY_RETURN, ret_handler
    # )
    sys.monitoring.register_callback(
        sys.monitoring.OPTIMIZER_ID, sys.monitoring.events.LINE, line_handler
    )
    atexit.register(lambda: sys.monitoring.free_tool_id(sys.monitoring.OPTIMIZER_ID))

    log(1, "[install_hooks] hooks installed!")


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

    cargs = CheckpointArgs(
        args.min_obj_size, args.output_dir, args.frequency, args.verbose
    )

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

    install_hooks(progname, cargs)
    exec(code, globs, None)

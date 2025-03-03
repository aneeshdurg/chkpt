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
class Checkpoint:
    tracee: str
    min_obj_size: int
    output_dir: Path
    frequency: int
    verbosity: int

    file_prefix: str = ""
    last_save: float | None = None

    def __post_init__(self):
        self.file_prefix = urllib.parse.quote_plus(self.tracee)

    def install(self):
        os.makedirs(args.output_dir, exist_ok=True)

        sys.monitoring.use_tool_id(sys.monitoring.OPTIMIZER_ID, "dbg")
        sys.monitoring.set_events(
            sys.monitoring.OPTIMIZER_ID,
            sys.monitoring.events.PY_START
            | sys.monitoring.events.PY_RETURN
            | sys.monitoring.events.LINE,
        )
        # TODO capture at the end of execution
        # sys.monitoring.register_callback(
        #     sys.monitoring.OPTIMIZER_ID, sys.monitoring.events.PY_START, handler
        # )
        # sys.monitoring.register_callback(
        #     sys.monitoring.OPTIMIZER_ID, sys.monitoring.events.PY_RETURN, ret_handler
        # )
        sys.monitoring.register_callback(
            sys.monitoring.OPTIMIZER_ID, sys.monitoring.events.LINE, self.line_handler
        )
        atexit.register(
            lambda: sys.monitoring.free_tool_id(sys.monitoring.OPTIMIZER_ID)
        )

        self.log(1, "[install_hooks] hooks installed!")

    def log(self, lvl, *args):
        if self.verbosity >= lvl:
            # TODO use logging module
            print(" ", *args, file=sys.stderr)

    def should_capture(self, v: Any) -> bool:
        sz = sys.getsizeof(v)
        if sz < self.min_obj_size:
            return False
        m = inspect.getmodule(type(v))
        if m is None:
            return False
        module_name = m.__name__

        if module_name == "builtins":
            if type(v) in [str, int, list, dict, set]:
                return True
        return module_name.startswith("pandas") or module_name.startswith("numpy")

    def ready_to_capture(self):
        if not self.frequency or self.last_save is None:
            return True
        now = time.time() * 1000
        if (now - self.last_save * 1000) >= self.frequency:
            return True

    def save(self, line_number, objs):
        ts = time.time()
        fname = f"chkpt.{self.file_prefix}.{line_number}@{ts}.pkl"
        for k in objs:
            self.log(1, f"  [save] {k} @ {ts} -> {fname}")
        with open(self.output_dir / fname, "wb") as f:
            pickle.dump(objs, f)
        self.last_save = ts

    def line_handler(self, code: CodeType, line_number: int) -> Any:
        self.ready_to_capture()
        if code.co_filename != self.tracee or not self.ready_to_capture():
            return
        self.log(1, "[line_handler]", code, line_number)
        try:
            cf = inspect.currentframe()
            assert cf
            assert cf.f_back
            to_save = {}
            for n, v in cf.f_back.f_globals.items():
                if self.should_capture(v):
                    self.log(1, "  [global] add", n)
                    to_save[n] = v
                else:
                    self.log(2, "  [global] skip", n)
            for n, v in cf.f_back.f_locals.items():
                if n in cf.f_back.f_globals:
                    continue
                if self.should_capture(v):
                    self.log(1, "  [local] add", n)
                    if n in to_save:
                        self.log(1, "    overwrite!", n)
                    to_save[n] = v
                else:
                    self.log(2, "  [local] skip", n)
            self.save(line_number, to_save)
        except Exception as e:
            raise e


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

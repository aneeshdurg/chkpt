import sys
import inspect
import atexit
import copy
import time
import os
import pickle
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from types import CodeType, ModuleType
from typing import Any, Union


global_chkpt_instance: Union["Checkpoint", None] = None


class FakeModule:
    _data: dict[str, Any]

    def __init__(self, data):
        self._data = data

    def __getattr__(self, key):
        return self.data[key]


@dataclass
class Checkpoint:
    tracee: str
    min_obj_size: int
    output_dir: Path
    frequency: int
    verbosity: int

    file_prefix: str = ""
    last_save: float | None = None

    tracked_objects: list[Any] = field(default_factory=list)
    tracked_library_prefixes: list[str] = field(
        default_factory=lambda: ["pandas", "numpy"]
    )

    _capture_on_next_line: bool = False

    @classmethod
    def get_global_singleton(cls) -> "Checkpoint":
        global global_chkpt_instance
        assert global_chkpt_instance is not None
        return global_chkpt_instance

    def __post_init__(self):
        self.file_prefix = urllib.parse.quote_plus(self.tracee)

        global global_chkpt_instance
        global_chkpt_instance = self

    def track(self, obj: Any):
        self.tracked_objects.append(obj)

    def untrack(self, obj: Any):
        self.tracked_objects = [
            tracked for tracked in self.tracked_objects if tracked is not obj
        ]

    def track_library(self, prefix: str):
        self.tracked_library_prefixes.append(prefix)

    def install(self):
        os.makedirs(self.output_dir, exist_ok=True)

        sys.monitoring.use_tool_id(sys.monitoring.OPTIMIZER_ID, "dbg")
        sys.monitoring.set_events(
            sys.monitoring.OPTIMIZER_ID,
            sys.monitoring.events.LINE,
        )

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
        if any(x is v for x in self.tracked_objects):
            return True

        # sys.getsizeof is not guaranteed to be the best method for all object
        # types (especially those that allocate via external libraries), but
        # some libraries like numpy implement __sizeof__ to report the number of
        # bytes that the object actually occupies.
        if self.min_obj_size < 0 or (
            self.min_obj_size > 0 and sys.getsizeof(v) < self.min_obj_size
        ):
            return False

        m = inspect.getmodule(type(v))
        if m is None:
            # This path shouldn't be hit by most objects
            return False
        module_name = m.__name__

        if module_name == "builtins":
            # TODO - is this necessary? Can we just save every builtin type?
            if type(v) in [str, int, float, list, dict, set]:
                return True
        return any(
            module_name.startswith(prefix) for prefix in self.tracked_library_prefixes
        )

    def ready_to_capture(self):
        if not self.frequency or self.last_save is None:
            return True

        if self.frequency < 0:
            return False

        now = time.time() * 1000
        if (now - self.last_save * 1000) >= self.frequency:
            return True
        return False

    def save(self, name: str, objs: Any):
        ts = time.time()
        fname = f"chkpt.{self.file_prefix}.{name}@{ts}.pkl"
        for k in objs:
            self.log(1, f"  [save] {k} @ {ts} -> {fname}")
        with open(self.output_dir / fname, "wb") as f:
            pickle.dump(objs, f)
        self.last_save = ts

    def snapshot(self, name: str):
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
            self.save(name, to_save)
        except Exception as e:
            raise e

    def line_handler(self, code: CodeType, line_number: int) -> Any:
        if code.co_filename != self.tracee or not self.ready_to_capture():
            return
        self.log(1, "[line_handler]", code, line_number)
        self.snapshot(str(line_number))


def main():
    import argparse
    import importlib.machinery
    import importlib.util

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
    progname = sys.argv[0]

    sys.path.insert(0, os.path.dirname(progname))
    spec = importlib.machinery.ModuleSpec(name="__main__", loader=None, origin=progname)
    loader = importlib.machinery.SourceFileLoader("__main__", progname)
    spec.loader = loader
    module = importlib.util.module_from_spec(spec)

    chkpt = Checkpoint(
        progname,
        args.min_obj_size,
        args.output_dir,
        args.frequency,
        args.verbose,
    )
    chkpt.install()

    # Execute the code within it's own __main__ module - this allows libraries
    # like pickle to resolve imports against __main__ in the context of the
    # usercode, and not this shim.
    # Note that sys.modules["__main__"] in the user code will still point to the
    # chkpt main module which could still have some issues.
    sys.modules["__main__"] = module
    spec.loader.exec_module(module)


__all__ = ["Checkpoint", "global_chkpt_instance", "main"]

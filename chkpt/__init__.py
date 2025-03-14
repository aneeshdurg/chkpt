import sys
import inspect
import atexit
import time
import os
import pickle
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from types import CodeType
from typing import Any, Union


global_chkpt_instance: Union["Checkpoint", None] = None


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

    def track_library(self, prefix: str):
        self.tracked_library_prefixes.append(prefix)

    def install(self):
        os.makedirs(self.output_dir, exist_ok=True)

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
        if any(x is v for x in self.tracked_objects):
            return True

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


__all__ = ["Checkpoint", "global_chkpt_instance"]

import sys
import inspect
import atexit
import time
from types import CodeType
from typing import Any
import pickle
import urllib.parse


def install_hooks(tracee: str):
    tracee = tracee
    min_capture_size = 100

    # TODO - custom output dir
    file_prefix = urllib.parse.quote_plus(tracee)

    def log(*args):
        # TODO - real logging with controllable verbosity
        print(" ", *args)

    def should_capture(module_name: str) -> bool:
        return module_name.startswith("pandas") or module_name.startswith("numpy")

    def save(line_number, objs):
        ts = time.time()
        fname = f"chkpt.{file_prefix}.{line_number}@{ts}.pkl"
        for k in objs:
            log(f"[save] {k} @ {ts} -> {fname}")
        with open(fname, "wb") as f:
            pickle.dump(objs, f)

    def line_handler(code: CodeType, line_number: int) -> Any:
        if code.co_filename != tracee:
            return
        log("[line_handler]", code, line_number)
        try:
            cf = inspect.currentframe()
            assert cf
            assert cf.f_back
            to_save = {}
            for n, v in cf.f_back.f_globals.items():
                m = inspect.getmodule(type(v))
                sz = sys.getsizeof(v)
                if (
                    sz > min_capture_size
                    and m is not None
                    and should_capture(m.__name__)
                ):
                    if n not in to_save:
                        to_save[n] = v
            for n, v in cf.f_back.f_locals.items():
                if n in cf.f_back.f_globals:
                    continue
                m = inspect.getmodule(type(v))
                sz = sys.getsizeof(v)
                if (
                    sz > min_capture_size
                    and m is not None
                    and should_capture(m.__name__)
                ):
                    to_save[n] = v
                save(line_number, to_save)
        except Exception:
            pass

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

    log("[install_hooks] hooks installed!")


if __name__ == "__main__":
    # import argparse
    import importlib.machinery
    import io
    import os

    # parser = argparse.ArgumentParser()

    sys.argv = sys.argv[1:]
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

    install_hooks(progname)
    exec(code, globs, None)

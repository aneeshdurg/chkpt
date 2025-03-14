import sys
import random
from time import sleep
from dataclasses import dataclass, field

from chkpt import Checkpoint


@dataclass
class State:
    x: list[int] = field(default_factory=list)

print('usr.__main__', sys.modules['__main__'])
print(State.__module__)


state = State()

try:
    chkpt = Checkpoint.get_global_singleton()
    # Prevent automatic snapshotting
    chkpt.frequency = -1
    chkpt.min_obj_size = -1
except AssertionError:
    chkpt = None
if chkpt:
    chkpt.track(state)

for i in range(1000):
    state.x.append(random.randint(1, 1000))
    if (i % 100) == 0:
        if chkpt:
            chkpt.snapshot(f"iter{i}")
    sleep(0.05)

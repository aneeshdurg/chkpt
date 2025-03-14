import random
from time import sleep
import pickle

from chkpt import Checkpoint
from dep import State


state = State()

try:
    chkpt = Checkpoint.get_global_singleton()
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

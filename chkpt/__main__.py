import sys
import os
from pathlib import Path

from . import main


if __name__ == "__main__":
    # We must import the entire main from a different module because we will
    # overwrite the __main__ module with the user code
    main()

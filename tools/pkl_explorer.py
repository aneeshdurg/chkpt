#!/usr/bin/env python
import argparse
import code
import os
import pickle
import sys

sys.path.append(os.getcwd())

parser = argparse.ArgumentParser()
parser.add_argument("pkl")
args = parser.parse_args()

with open(args.pkl, "rb") as f:
    data = pickle.load(f)

code.InteractiveConsole(locals=data).interact()

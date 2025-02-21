#!/usr/bin/env python
import argparse
import code
import pickle

parser = argparse.ArgumentParser()
parser.add_argument("pkl")
args = parser.parse_args()

with open(args.pkl, "rb") as f:
    data = pickle.load(f)

code.InteractiveConsole(locals=data).interact()

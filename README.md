# chkpt - a automatic python checkpointing tool

```
python -m chkpt [args] [--] <script to run + args...>
```

`chkpt` automatically pickles any numpy and pandas instances that are larger
than some configurable size (default 1M). The frequency of checkpoints is also
configurable - by default a checkpoint is taken after every line is executed.

See `python -m chkpt -h` for more info.

See examples for examples of using the `chkpt` API to manually track and manage
snapshots.

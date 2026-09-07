r"""Fetch DIII-D PTDATA signals from anywhere, including inside the notebook kernel.

Why this module exists
----------------------
PTDATA cannot be fetched from inside the Jupyter kernel. A direct
`PtDataSignal` fetch there fails with:

    getservbyname failed for task 'PTSERVER' ... not in /etc/services

and it fails on a virgin kernel with every environment variable correct, so it
is not a configuration problem that can be fixed by setting more variables.

The trap is that this is easy to hit without realising. The agent backend
intercepts any command whose executable is `python` or `python3` and runs it
INSIDE the kernel rather than as a subprocess -- that is what makes interactive
charts work. So `python fetch.py` never leaves the kernel, while
`fdp run python fetch.py` does, because its executable is `fdp`.

Rather than require every caller to remember that, this module always runs the
fetch in a real subprocess. Call it from a notebook cell, from a script the
agent executes, from anywhere -- the fetch escapes the kernel either way.

Usage
-----
    from d3d_ptdata import fetch_ptdata

    sig = fetch_ptdata(169908, ["BESFU32", "BESFU40"])
    t = sig["BESFU32"]["times"]     # ms
    d = sig["BESFU32"]["data"]

MDSplus tree signals (efit01, spectroscopy, electrons, bes) do NOT need this --
they work in-kernel. This is only for PTDATA, which includes every BES channel.
"""
import json
import os
import subprocess
import sys
import tempfile

import numpy as np

__all__ = ["fetch_ptdata"]

_WORKER = r'''
import json, os, sys
import numpy as np
from toksearch import Pipeline
from toksearch_d3d import PtDataSignal

shot, names, out = int(sys.argv[1]), json.loads(sys.argv[2]), sys.argv[3]
pipe = Pipeline([shot])
for n in names:
    pipe.fetch(n, PtDataSignal(n))
rec = pipe.compute_serial()[0]
if rec.errors:
    print("FETCH_ERRORS " + json.dumps({k: str(v)[:300] for k, v in rec.errors.items()}))
    sys.exit(2)
np.savez(out, **{f"{n}__t": np.asarray(rec[n]["times"], float) for n in names},
              **{f"{n}__d": np.asarray(rec[n]["data"], float) for n in names})
print("OK " + json.dumps({n: str(rec[n]["units"]["data"]) for n in names}), flush=True)
# Exit hard: the MDSplus/PTDATA C libraries intermittently abort during
# interpreter teardown ("malloc_consolidate(): unaligned fastbin chunk"),
# AFTER the data is safely written. os._exit skips that teardown entirely.
os._exit(0)
'''


def find_signals(pattern, tree=None, limit=200):
    """Search the DIII-D signal catalogue by name. One query, no MDSplus.

    Answers "does a signal like this exist, and in which tree?" against the
    catalogue of every archived pointname -- before paying to open a tree or
    fetch anything. `pattern` is matched case-insensitively anywhere in the
    name; use `%` for a wildcard inside it.

        find_signals("FS%DA")        -> the D-alpha filterscope channels
        find_signals("D2")           -> anything with D2 in the name
        find_signals("IP", tree="EFIT01")

    Returns {name, tree, full_path}, sorted by name.

    AN EMPTY RESULT IS AN ANSWER. If nothing matches, the archive has no such
    pointname, and an analysis that needs one cannot be done -- say so rather
    than searching again by another route. Check the naming convention before
    concluding: a family often uses a suffix you have not guessed, and listing
    the family (`find_signals("FS00%")`) shows which suffixes exist.
    """
    import os
    import sys as _sys
    _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from d3d_lakehouse import query as _q

    like = pattern if "%" in pattern else "%" + pattern + "%"
    sql = "SELECT name, tree, full_path FROM d3d.signal_names WHERE name ILIKE ?"
    params = [like]
    if tree:
        sql += " AND tree ILIKE ?"
        params.append(tree)
    sql += " ORDER BY name, tree LIMIT ?"
    params.append(int(limit))
    return _q(sql, tuple(params))


def fetch_ptdata(shot, pointnames, timeout=600):
    """Fetch PTDATA pointnames for one shot. Returns {name: {times, data, units}}.

    times are in milliseconds, matching every other DIII-D signal here.
    Raises RuntimeError with the underlying message if the fetch fails.
    """
    if isinstance(pointnames, str):
        pointnames = [pointnames]
    pointnames = list(pointnames)

    with tempfile.TemporaryDirectory() as tmp:
        script = os.path.join(tmp, "_fetch.py")
        npz = os.path.join(tmp, "out.npz")
        with open(script, "w") as f:
            f.write(_WORKER)

        # `fdp run` -- NOT `python` -- so this is a real subprocess and not
        # routed back into the kernel by the agent backend.
        proc = subprocess.run(
            ["fdp", "run", "python", script, str(shot), json.dumps(pointnames), npz],
            capture_output=True, text=True, timeout=timeout,
        )
        tail = "\n".join((proc.stdout + proc.stderr).strip().splitlines()[-6:])
        for line in proc.stdout.splitlines():
            if line.startswith("FETCH_ERRORS "):
                raise RuntimeError(
                    f"PTDATA fetch failed for shot {shot}: {line[len('FETCH_ERRORS '):]}")
        # Judge success by whether the data arrived, NOT by the return code: the
        # worker can abort during teardown after writing a complete file.
        if not os.path.exists(npz):
            raise RuntimeError(f"PTDATA fetch produced no data for shot {shot} "
                               f"{pointnames}:\n{tail}")

        units = {}
        for line in proc.stdout.splitlines():
            if line.startswith("OK "):
                units = json.loads(line[3:])
        z = np.load(npz)
        return {n: {"times": z[f"{n}__t"], "data": z[f"{n}__d"],
                    "units": units.get(n, "")} for n in pointnames}

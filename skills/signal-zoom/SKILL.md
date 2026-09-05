---
name: signal-zoom
description: "Render an INTERACTIVE, zoomable signal chart (Plotly, HighStock-style: drag to box-zoom, double-click to reset, range-slider to pan). Use ONLY when the request explicitly asks for a ZOOMABLE / INTERACTIVE / ZOOM-IN chart, or says zoom in/out, or mentions HighCharts / HighStock. For a normal plot/chart request WITHOUT such a term, do NOT use this skill -- render a static image (matplotlib PNG) as usual. Works for any time-series signal: filterscopes, EFIT scalars, multi-shot overlays."
license: Apache-2.0
compatibility: Designed for deepagents CLI with fdp-d3d
metadata:
  author: DeepTok
  version: "1.0"
---

# signal-zoom -- Interactive, Zoomable Signal Charts

## When to use (routing) -- the trigger term matters

Use this skill ONLY when the user's request contains a zoom/interactive trigger:
`zoomable`, `interactive chart`, `zoom-in chart`, `zoomable view`,
`let me zoom in/out`, `HighCharts-style`, `HighStock-style`.

If the request just says "plot" / "chart" / "show" with NO such term, do NOT use
this skill -- produce a normal static image (matplotlib PNG) as usual. The
interactive chart is opt-in via the trigger term; static image is the default.

## What it renders

An interactive Plotly chart (display-only -- no kernel variables, no cross-cell
state). The user interacts with it directly:
- drag a box on the plot to zoom into that region,
- double-click to zoom back out (autoscale),
- drag the range slider under the plot to pan / set a window.

Full-resolution WebGL (Scattergl), so a ~400k-sample filterscope trace stays
responsive and zooming reveals real detail such as individual ELM spikes.

## CRITICAL: run in-kernel, NOT via fdp

An interactive chart must render in the notebook, so the script MUST run
IN-KERNEL. Write it to a `.py` file and run it with plain:

```
python /path/to/script.py
```

Do NOT use the `fdp` wrapper here -- `fdp run python ...` runs in a subprocess and
cannot render interactive output. The kernel already has the Pelican environment
(bearer token + MDSplus tree paths + LD_PRELOAD), so a plain in-kernel `python`
script fetches data with TokSearch normally. This is the one data task that does
NOT use the fdp wrapper.

**The command must also be BARE -- no `cd`, no `&&`, no pipes.** Use an
ABSOLUTE script path and nothing else on the command line. ARGUS only routes a
command into the kernel if it parses as a simple `python <script>` invocation;
a command containing ANY shell operator (`&&`, `|`, `;`, `>`, ...) is not
intercepted and runs as a genuine subprocess, where the chart can never render.
Verified 2026-08-02 on the Colab port: a plot step written as
`cd "<workspace>" && python plot.py` produced no chart, no error and no
warning, while the agent reported success -- `display()` does not raise in a
subprocess, it just prints a repr. `plot_signal_zoom()` now detects this and
prints a loud `ERROR: ... running in a SUBPROCESS ...`; if you see it, re-run
the same script as a bare `python /abs/path/script.py`.

## Import the helper

```python
import os, sys
sys.path.insert(0, os.path.expanduser("~/.deepagents/agent/skills/signal-zoom"))
from sage_signal_zoom import plot_signal_zoom
```

## API

```python
plot_signal_zoom(times, data, title="Signal", y_label="", x_label="Time (ms)",
                 series=None, height=500, max_points=None)
```
- Single series: pass `times` and `data`.
- Multiple overlaid signals: pass `series=[{"name","times","data"}, ...]`.
- `max_points`: min-max decimation for display (default ~10000 -- keeps the range
  slider responsive while preserving spikes, so ELM peaks stay visible). Pass None
  to plot every raw sample (a ~400k filterscope trace at full resolution makes the
  slider laggy).

Display-only: it renders the chart and returns the figure; it sets NO kernel variable.

## Complete example -- single signal

Request: "Show a **zoomable** chart of `\fs04` for shot 165920."

```python
import os, sys
sys.path.insert(0, os.path.expanduser("~/.deepagents/agent/skills/signal-zoom"))
from sage_signal_zoom import plot_signal_zoom
from toksearch import Pipeline, MdsSignal

p = Pipeline([165920]); p.fetch("fs04", MdsSignal(r"\fs04", "spectroscopy"))
rec = p.compute_serial()[0]
sig = rec["fs04"]
plot_signal_zoom(sig["times"], sig["data"],
                 title="Shot 165920  \\fs04 (D-alpha filterscope)",
                 y_label="ph/cm2/sr/s")
```
Run it in-kernel: `python /home/jovyan/work/.../zoom_fs04.py`

## Complete example -- multi-shot overlay

Request: "**Zoomable** comparison of plasma current for shots 165340 and 188702."

```python
import os, sys
sys.path.insert(0, os.path.expanduser("~/.deepagents/agent/skills/signal-zoom"))
from sage_signal_zoom import plot_signal_zoom
import numpy as np
from toksearch import Pipeline, MdsSignal

p = Pipeline([165340, 188702]); p.fetch("ip", MdsSignal(r"\ipmhd", "efit01"))
series = []
for rec in p.compute_serial():
    if "ip" in rec.errors:
        continue
    s = rec["ip"]
    series.append({"name": str(rec["shot"]),
                   "times": np.asarray(s["times"]),
                   "data": np.asarray(s["data"]) / 1e6})   # raw is A -> MA
plot_signal_zoom(series=series, title="Plasma current (zoomable)", y_label="MA")
```

## Rules

- Only use when the request has a zoom/interactive trigger term (see routing).
- Run the script IN-KERNEL with a bare `python /abs/path/script.py` -- never via
  `fdp`, and never with `cd`/`&&`/pipes (those force a subprocess: no render).
- Do NOT build your own Plotly figure -- call `plot_signal_zoom`.
- Display-only: do NOT read any kernel variable afterward; it sets none.

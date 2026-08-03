"""signal-zoom (Colab variant): interactive, zoomable signal charts (Plotly).

TWO-STEP, unlike the JupyterHub/Docker version -- verified 2026-08-02: on
Colab, toksearch/MDSplus can NEVER be imported in-kernel, because Colab's
kernel process imports its own numpy (2.0.2, from `dist-packages`) as part
of its OWN startup, before any user code runs -- no `sys.path` trick fixes
this, since the wrong numpy is already bound in `sys.modules` before you get
a chance to intervene. A conda-installed, compatible `numpy<2` genuinely
exists in `site-packages`, it's just permanently unreachable from inside
that same kernel process. The only way to reach it is a genuinely separate
process -- exactly what `fdp run` already does.

So here, fetching (needs toksearch/MDSplus) and plotting (needs to render
in-kernel for Plotly to display) are split into two steps that hand off
through a small .npz file:
  1. fetch_signal_for_zoom(...)   -- run via `fdp run` (subprocess)
  2. plot_signal_zoom_from_npz(...) -- run in-kernel (plain python)

Step 2's actual chart code (`plot_signal_zoom`/`_minmax_decimate`) is pure
numpy + plotly -- no toksearch/MDSplus import at all -- so it's unaffected by
the numpy conflict and renders fine using the kernel's own (2.0.2, otherwise
fine) numpy.
"""
import numpy as np


def fetch_signal_for_zoom(out_path, shots, expr, tree, names=None):
    """Fetch `expr` from `tree` for each shot and save the result as an .npz
    for plot_signal_zoom_from_npz() to load later.

    MUST run via `fdp run python script.py` (a subprocess) -- NOT in-kernel.
    toksearch/MDSplus cannot be imported in-kernel on Colab (see module
    docstring); this function assumes it's being called from a subprocess.

    Parameters
    ----------
    out_path : str
        Where to write the .npz (e.g. "/content/fs04_165920.npz").
    shots : list[int]
    expr : str
        MDSplus signal expression, e.g. r"\\fs04".
    tree : str
    names : list[str], optional
        Display name per shot (default: str(shot)). Only names for shots
        that actually returned data are kept -- shots with fetch errors are
        silently skipped (each caller should check the returned count).

    Returns
    -------
    int : number of shots successfully fetched and saved.
    """
    from toksearch import Pipeline, MdsSignal

    p = Pipeline(shots)
    p.fetch("sig", MdsSignal(expr, tree))
    results = p.compute_serial()

    arrays = {}
    n_ok = 0
    for i, rec in enumerate(results):
        if "sig" in rec.errors:
            continue
        d = rec["sig"]
        name = names[i] if names else str(rec["shot"])
        arrays[f"times_{n_ok}"] = np.asarray(d["times"])
        arrays[f"data_{n_ok}"] = np.asarray(d["data"])
        arrays[f"name_{n_ok}"] = np.array(name)
        n_ok += 1

    arrays["n_series"] = np.array(n_ok)
    np.savez(out_path, **arrays)
    print(f"Saved {n_ok} of {len(shots)} requested shots to {out_path}")
    return n_ok


def _in_ipython_kernel():
    """True only if we're running inside a live IPython KERNEL (not a subprocess).

    An interactive chart can ONLY render from in-kernel code. ARGUS routes a
    bare `python script.py` into the kernel via `get_ipython().run_cell`, but
    any command containing a shell operator (`&&`, `|`, `>`, ...) is NOT
    intercepted and runs as a genuine subprocess instead -- so a plot step
    written as `cd somewhere && python plot.py` silently renders nothing.
    See _SHELL_OPERATORS / _parse_python_invocation in sage_kernel_backend.py.
    """
    try:
        from IPython import get_ipython
        ip = get_ipython()
    except Exception:
        return False
    # A plain `python` REPL/subprocess has no shell; a terminal IPython shell
    # has one but no `.kernel`. Only a kernel can publish display output.
    return ip is not None and getattr(ip, "kernel", None) is not None


def _minmax_decimate(x, y, n_out):
    """Downsample to ~n_out points keeping each bin's min and max (in time order).

    Preserves spikes/envelope, unlike simple striding. Returns (x, y) unchanged
    if n_out is None or the trace already fits.
    """
    x = np.asarray(x)
    y = np.asarray(y)
    n = x.size
    if not n_out or n <= n_out:
        return x, y
    n_bins = max(1, int(n_out) // 2)
    bin_size = n // n_bins
    if bin_size < 2:
        return x, y
    trim = n_bins * bin_size
    xb = x[:trim].reshape(n_bins, bin_size)
    yb = y[:trim].reshape(n_bins, bin_size)
    rows = np.arange(n_bins)
    imin = yb.argmin(axis=1)
    imax = yb.argmax(axis=1)
    lo = np.minimum(imin, imax)   # earlier of the two within each bin
    hi = np.maximum(imin, imax)
    out_x = np.empty(n_bins * 2)
    out_y = np.empty(n_bins * 2)
    out_x[0::2] = xb[rows, lo]; out_x[1::2] = xb[rows, hi]
    out_y[0::2] = yb[rows, lo]; out_y[1::2] = yb[rows, hi]
    if trim < n:  # keep the tail so the end of the trace isn't dropped
        out_x = np.concatenate([out_x, x[trim:]])
        out_y = np.concatenate([out_y, y[trim:]])
    return out_x, out_y


def plot_signal_zoom(times=None, data=None, title="Signal", y_label="",
                     x_label="Time (ms)", series=None, height=500, max_points=10000):
    """Render an interactive, zoomable Plotly chart of one or more signals.

    Run this in-kernel (plain `python script.py`, never `fdp run`) -- it's
    the step that actually renders/displays the chart in the notebook.
    Usually called via plot_signal_zoom_from_npz() rather than directly.

    Display-only: renders the chart and returns the figure; sets NO kernel
    variable.
    """
    import plotly.graph_objects as go
    import plotly.io as pio

    # Colab's notebook frontend needs the renderer set explicitly -- without
    # this, display(fig) doesn't error, it just silently produces output
    # Colab's frontend can't render (verified 2026-08-02: a real chart request
    # completed with no traceback anywhere, and no chart ever appeared --
    # every output block was under 1.1KB; a real rendered chart is 200KB+).
    pio.renderers.default = "colab"

    if series is None:
        if times is None or data is None:
            raise ValueError("Pass either (times, data) or series=[...].")
        series = [{"name": title, "times": times, "data": data}]

    fig = go.Figure()
    for s in series:
        x, y = _minmax_decimate(s["times"], s["data"], max_points)
        name = s.get("name", "")
        fig.add_trace(go.Scattergl(
            x=x, y=y, mode="lines", name=name, line=dict(width=0.7),
            hovertemplate="t=%{x:.3f}<br>y=%{y:.4g}<extra>" + str(name) + "</extra>",
        ))

    fig.update_layout(
        title=title, xaxis_title=x_label, yaxis_title=y_label,
        template="plotly_white", height=height, dragmode="zoom",
        margin=dict(l=60, r=20, t=50, b=40),
        legend=dict(orientation="h", y=1.02, x=0),
        showlegend=len(series) > 1,
    )
    fig.update_xaxes(rangeslider_visible=True)

    if not _in_ipython_kernel():
        # Verified 2026-08-02: this is THE failure mode for this skill, and it
        # is 100% silent without this check -- display() below does NOT raise
        # in a subprocess, it just prints a repr, so the script exits 0 and
        # looks successful while rendering nothing at all. Caught after a run
        # whose plot step was `cd <dir> && python plot.py`: the `&&` makes
        # ARGUS treat the whole thing as a shell command and run it in a
        # subprocess instead of in the kernel.
        print(
            "ERROR: plot_signal_zoom is running in a SUBPROCESS, not the "
            "notebook kernel -- the interactive chart CANNOT render from "
            "here, and nothing was displayed.\n"
            "  Cause: the plot step was almost certainly run with a shell "
            "operator in the command (e.g. `cd <dir> && python plot.py`). "
            "Any of && | ; > makes ARGUS run the command as a subprocess "
            "instead of routing it into the kernel.\n"
            "  Fix: re-run the plot step as a BARE python command with an "
            "ABSOLUTE script path and no `cd`, e.g.\n"
            "      python /full/path/to/plot_script.py\n"
            "  (The fetch step is unaffected -- it SHOULD be a subprocess.)"
        )
        return fig

    try:
        from IPython.display import display
        display(fig)
    except Exception as e:
        # Never swallow this silently -- a silent failure here means "no
        # chart, no error, no clue why" (verified 2026-08-02: this exact
        # bare except hid a real render failure with zero trace of what went
        # wrong). Print so a failure is at least visible and debuggable.
        print(f"plot_signal_zoom: display(fig) failed: {type(e).__name__}: {e}")
    return fig


def plot_signal_zoom_from_npz(npz_path, title="Signal", y_label="",
                               x_label="Time (ms)", height=500, max_points=10000):
    """Load an .npz written by fetch_signal_for_zoom() and render it.

    Run in-kernel (plain `python script.py`) -- this is step 2 of the
    Colab two-step pattern (see module docstring).
    """
    npz = np.load(npz_path)
    n = int(npz["n_series"])
    series = [
        {
            "name": str(npz[f"name_{i}"]),
            "times": npz[f"times_{i}"],
            "data": npz[f"data_{i}"],
        }
        for i in range(n)
    ]
    return plot_signal_zoom(series=series, title=title, y_label=y_label,
                             x_label=x_label, height=height, max_points=max_points)

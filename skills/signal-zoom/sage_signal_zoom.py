"""sage-signal-zoom helper: interactive, zoomable signal charts (Plotly).

Display-only. No kernel variables, no cross-cell state. The user interacts with
the rendered chart directly:
  - drag a box on the plot to zoom into that region,
  - double-click to zoom back out (autoscale),
  - drag the range slider under the plot to pan / set a window.

Large traces (a filterscope is ~400k samples) are min-max decimated for display
so the range slider stays responsive. Min-max decimation keeps the min AND max
of each time bin, so the spike envelope is preserved -- individual ELM peaks stay
visible. Pass max_points=None to plot every raw sample (may lag for big traces).
"""
import numpy as np


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

    Single series:
        plot_signal_zoom(times, data, title="fs04", y_label="ph/cm2/sr/s")

    Multiple overlaid series (e.g. several shots, zoom them together):
        plot_signal_zoom(
            series=[{"name": "165340", "times": t1, "data": d1},
                    {"name": "188702", "times": t2, "data": d2}],
            title="Plasma current comparison", y_label="MA")

    Parameters
    ----------
    times, data : array-like
        x and y arrays of equal length (single-series shortcut).
    series : list of dict, optional
        [{"name", "times", "data"}, ...] for multiple traces. Overrides
        times/data when given.
    title, y_label, x_label : str
    height : int
    max_points : int, optional
        Min-max-decimate each trace to about this many points for display
        (default 10000 -- keeps the slider responsive while preserving spikes,
        so ELM peaks stay visible). Pass None to plot every raw sample; a ~400k
        filterscope trace at full resolution makes the range slider laggy.

    Display-only: renders the chart and returns the figure; sets NO kernel variable.
    """
    import plotly.graph_objects as go

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
        # Verified 2026-08-02 on the Colab port of this skill, and the same
        # trap applies here: this failure is 100% silent without the check --
        # display() does NOT raise in a subprocess, it just prints a repr, so
        # the script exits 0 and looks successful while rendering nothing.
        # Triggered by a plot command like `cd <dir> && python plot.py`: the
        # `&&` makes ARGUS run it as a subprocess instead of in the kernel.
        print(
            "ERROR: plot_signal_zoom is running in a SUBPROCESS, not the "
            "notebook kernel -- the interactive chart CANNOT render from "
            "here, and nothing was displayed.\n"
            "  Cause: the plot command almost certainly contained a shell "
            "operator (e.g. `cd <dir> && python plot.py`). Any of && | ; > "
            "makes ARGUS run the command as a subprocess instead of routing "
            "it into the kernel.\n"
            "  Fix: re-run as a BARE python command with an ABSOLUTE script "
            "path and no `cd`, e.g.\n"
            "      python /full/path/to/plot_script.py"
        )
        return fig

    try:
        from IPython.display import display
        display(fig)
    except Exception as e:
        # Never swallow this silently -- a silent failure here means "no
        # chart, no error, no clue why". Print so it's visible/debuggable.
        print(f"plot_signal_zoom: display(fig) failed: {type(e).__name__}: {e}")
    return fig

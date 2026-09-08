"""Helpers for the materials schema: samples, exposures, measurements, files.

The data is long-form on purpose. A measured quantity is a ROW, not a column,
so this module cannot and does not name the quantities it expects to find --
`quantities()` reports what is actually there, and everything else filters on
what that returned. A delivery measuring something new is queryable through
exactly these functions with no edit here.

Every lookup takes a COLLECTION. `retention_for(["W-DH", "W-DL"])` is one
request; the same information gathered one sample at a time is one HTTP round
trip per sample. Single-item convenience wrappers exist and are thin -- they
call the batch form with a list of one.

Table references are schema-qualified throughout. The lakehouse resolves an
unqualified name against `d3d` first, where `shots` is the full plasma
catalogue, so a bare `FROM samples` here would be a different question.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from d3d_lakehouse import LakehouseError  # noqa: E402,F401
from d3d_lakehouse import bearer_token as _token  # noqa: E402
from d3d_lakehouse import endpoint as _endpoint  # noqa: E402
from d3d_lakehouse import query as _query_api  # noqa: E402


class SampleNotFound(LookupError):
    """Raised when a named sample is not in the catalogue.

    An exception rather than an empty list: "no rows for sample X" must not be
    readable as "sample X was measured and the value was nothing".
    """


class ArtifactUnavailable(RuntimeError):
    """The artifact is catalogued but its bytes cannot be served."""


def _query(sql, params=()):
    return _query_api(sql, params)


def working_dir():
    """The notebook's working folder -- where fetched files belong.

    NOT the current directory. A script may be run from anywhere (`python
    /abs/path/script.py` leaves the process in the notebook's own folder, one
    level up), and a file written there is outside the working folder: it gets
    swept back, re-fetched by the next script, and swept again. Resolving
    against the exported working folder makes the destination the same no
    matter how the script was invoked, which is also what lets the local-copy
    check actually hit.
    """
    return os.environ.get("SAGE_OUTPUT_DIR") or os.getcwd()


def _as_list(x):
    """Accept a scalar or any iterable of them, uniformly."""
    if x is None:
        return None
    if isinstance(x, (str, bytes)) or not hasattr(x, "__iter__"):
        return [x]
    return list(x)


# --------------------------------------------------------------------------
# what is here -- discovery before filtering
# --------------------------------------------------------------------------

_DELIVERIES_CACHE = None
_QUANTITIES_CACHE = None


def deliveries(refresh=False):
    """Every delivery, with who provided it and when.

    Cached: provenance cannot change while a script runs, and this is read on
    the way into most other questions.
    """
    global _DELIVERIES_CACHE
    if _DELIVERIES_CACHE is None or refresh:
        _DELIVERIES_CACHE = _query(
            """SELECT delivery_id, source, contact, received_on, description, notes,
                      (SELECT count(*) FROM materials.samples s
                        WHERE s.delivery_id = d.delivery_id) AS n_samples
                 FROM materials.deliveries d ORDER BY received_on, delivery_id""")
    return _DELIVERIES_CACHE


def quantities(refresh=False):
    """Every measured quantity present, with its method, stage, unit and reach.

    START HERE. The schema stores measurements as rows, so the list of what is
    measurable is data, not documentation -- it is discovered by asking, and it
    grows when a delivery brings a new instrument.
    """
    global _QUANTITIES_CACHE
    if _QUANTITIES_CACHE is None or refresh:
        _QUANTITIES_CACHE = _query(
            """SELECT stage, method, quantity, unit,
                      count(DISTINCT sample_key) AS n_samples,
                      count(*) FILTER (WHERE point_index IS NOT NULL) AS n_profile_points
                 FROM materials.observations
                GROUP BY stage, method, quantity, unit
                ORDER BY stage, method NULLS FIRST, quantity""")
    return _QUANTITIES_CACHE


def samples(delivery_id=None, names=None):
    """Samples, optionally restricted to a delivery or a set of names."""
    sql = ["""SELECT sample_key, delivery_id, sample_id, name, ordinal,
                     material, description, investigator
                FROM materials.samples WHERE 1=1"""]
    params = []
    if delivery_id:
        sql.append("AND delivery_id = ?"); params.append(delivery_id)
    names = _as_list(names)
    if names is not None:
        sql.append("AND name IN (?)"); params.append(names)
    sql.append("ORDER BY delivery_id, ordinal, sample_id")
    return _query(" ".join(sql), tuple(params))


def _keys_for(names):
    """Resolve sample names to keys in ONE query, raising on any that is unknown."""
    names = _as_list(names)
    rows = _query("SELECT sample_key, name FROM materials.samples WHERE name IN (?)",
                  (names,))
    found = {r["name"]: r["sample_key"] for r in rows}
    missing = [n for n in names if n not in found]
    if missing:
        known = [r["name"] for r in _query(
            "SELECT name FROM materials.samples ORDER BY ordinal LIMIT 50")]
        raise SampleNotFound(
            "not in the catalogue: %s. Known samples include: %s"
            % (", ".join(map(str, missing)), ", ".join(map(str, known))))
    return found


# --------------------------------------------------------------------------
# measurements
# --------------------------------------------------------------------------

def observations(sample_names=None, quantity=None, method=None, stage=None,
                 profile=None):
    """Measured values for a GROUP of samples, in one request.

    `quantity`, `method` and `stage` accept a value or a collection; pass what
    `quantities()` reported. `profile` selects depth-resolved rows when True and
    single values when False; None returns both.
    """
    sql = ["""SELECT s.name AS sample_name, o.stage, o.method, o.quantity, o.qualifier,
                     o.value_num, o.value_std, o.value_text, o.unit,
                     o.depth_um, o.point_index, o.exposure_id, o.artifact_id
                FROM materials.observations o
                JOIN materials.samples s USING (sample_key)
               WHERE 1=1"""]
    params = []
    for col, val in (("s.name", sample_names), ("o.quantity", quantity),
                     ("o.method", method), ("o.stage", stage)):
        val = _as_list(val)
        if val is not None:
            sql.append("AND %s IN (?)" % col); params.append(val)
    if profile is True:
        sql.append("AND o.point_index IS NOT NULL")
    elif profile is False:
        sql.append("AND o.point_index IS NULL")
    sql.append("ORDER BY s.ordinal, o.stage, o.method, o.quantity, o.point_index")
    return _query(" ".join(sql), tuple(params))


def values_by_sample(sample_names, quantity, method=None, stage=None):
    """One scalar quantity for a GROUP of samples -> {sample: {...}}.

    The shape to compare samples against each other. Samples with no such
    measurement are absent from the result rather than present with a zero.
    """
    rows = observations(sample_names, quantity=quantity, method=method,
                        stage=stage, profile=False)
    out = {}
    for r in rows:
        out.setdefault(r["sample_name"], []).append(
            {k: r[k] for k in ("method", "stage", "quantity", "qualifier",
                               "value_num", "value_std", "unit")})
    return {k: (v[0] if len(v) == 1 else v) for k, v in out.items()}


def profiles(sample_names, quantity, method=None):
    """Depth-resolved series for a GROUP of samples -> {sample: [points]}.

    Points keep the order they were delivered in, and carry depth when the
    delivery supplied a depth axis. A point is a dict with the same keys a
    row from `observations()` uses -- `depth_um`, `value_num`, `value_std`,
    `unit`, `point_index` -- so a profile and a single measurement are
    filtered, renamed and plotted the same way.
    """
    rows = observations(sample_names, quantity=quantity, method=method, profile=True)
    out = {}
    for r in rows:
        out.setdefault(r["sample_name"], []).append(
            {"point_index": r["point_index"], "depth_um": r["depth_um"],
             "value_num": r["value_num"], "value_std": r["value_std"],
             "unit": r["unit"]})
    return out


# --------------------------------------------------------------------------
# exposures, and the bridge to shot data
# --------------------------------------------------------------------------

def exposures(sample_names=None, device=None):
    """Exposure campaigns, with the samples and shots each covers.

    An exposure is shared: several samples sit in the same plasma over the same
    shots, so this returns campaigns, not one row per sample.
    """
    sql = ["""SELECT e.exposure_id, e.delivery_id, e.slot, e.ordinal, e.facility,
                     e.device, e.description, e.coordinator, e.start_date, e.end_date,
                     (SELECT array_agg(s.name ORDER BY s.ordinal)
                        FROM materials.exposure_samples x
                        JOIN materials.samples s USING (sample_key)
                       WHERE x.exposure_id = e.exposure_id) AS sample_names,
                     (SELECT array_agg(sh.shot ORDER BY sh.shot)
                        FROM materials.exposure_shots sh
                       WHERE sh.exposure_id = e.exposure_id) AS shots
                FROM materials.exposures e WHERE 1=1"""]
    params = []
    if device:
        sql.append("AND e.device IN (?)"); params.append(_as_list(device))
    names = _as_list(sample_names)
    if names is not None:
        sql.append("""AND EXISTS (SELECT 1 FROM materials.exposure_samples x
                                    JOIN materials.samples s USING (sample_key)
                                   WHERE x.exposure_id = e.exposure_id
                                     AND s.name IN (?))""")
        params.append(names)
    sql.append("ORDER BY e.ordinal, e.exposure_id")
    return _query(" ".join(sql), tuple(params))


def exposure_conditions(exposure_ids=None, sample_names=None):
    """The plasma conditions of a GROUP of campaigns, one row per parameter."""
    sql = ["""SELECT p.exposure_id, e.slot, e.facility, p.name,
                     p.value_num, p.value_text, p.unit
                FROM materials.exposure_params p
                JOIN materials.exposures e USING (exposure_id)
               WHERE 1=1"""]
    params = []
    ids = _as_list(exposure_ids)
    if ids is not None:
        sql.append("AND p.exposure_id IN (?)"); params.append(ids)
    names = _as_list(sample_names)
    if names is not None:
        sql.append("""AND EXISTS (SELECT 1 FROM materials.exposure_samples x
                                    JOIN materials.samples s USING (sample_key)
                                   WHERE x.exposure_id = p.exposure_id
                                     AND s.name IN (?))""")
        params.append(names)
    sql.append("ORDER BY p.exposure_id, p.name")
    return _query(" ".join(sql), tuple(params))


def design(delivery_id=None):
    """The experiment's cells: which exposures each sample went through.

    A cell is a distinct combination of exposures, and the samples sharing it
    are that cell's replicates. This is the question to ask before stating what
    a comparison rests on -- `n_samples` is how many independent coupons
    support it, and a cell of one has no replication at all, so a difference
    between two such cells is a difference between two coupons and cannot be
    separated from coupon-to-coupon variation.

    It also says how many levels a factor has. Two cells differing only in
    which exposure of a facility they went through are two levels of that
    treatment, and a result that holds at one level is not a result about the
    treatment. Read the levels back from here rather than assuming a treatment
    is present-or-absent.

    Derived from `exposure_samples`, so it follows whatever design the delivery
    actually contains.
    """
    rows = _query("""SELECT s.name AS sample_name, e.exposure_id, e.slot,
                            e.facility, e.device
                       FROM materials.samples s
                       LEFT JOIN materials.exposure_samples x
                              ON x.sample_key = s.sample_key
                       LEFT JOIN materials.exposures e
                              ON e.exposure_id = x.exposure_id
                      WHERE (%s IS NULL OR s.delivery_id = %s)
                      ORDER BY s.name, e.exposure_id""",
                   (delivery_id, delivery_id))
    per_sample = {}
    detail = {}
    for r in rows:
        got = per_sample.setdefault(r["sample_name"], [])
        if r["exposure_id"] is not None:
            got.append(r["exposure_id"])
            detail[r["exposure_id"]] = {"exposure_id": r["exposure_id"],
                                        "slot": r["slot"], "facility": r["facility"],
                                        "device": r["device"]}
    cells = {}
    for name, ids in per_sample.items():
        cells.setdefault(tuple(sorted(ids)), []).append(name)
    out = []
    for ids, names in sorted(cells.items(), key=lambda kv: (len(kv[0]), kv[0])):
        out.append({"exposures": [detail[i] for i in ids],
                    "samples": sorted(names),
                    "n_samples": len(names)})
    return out


def shots_for_samples(sample_names=None, device=None):
    """{sample_name: [shot, ...]} for a GROUP of samples, in one request.

    This is the join to the rest of the lakehouse: the shots come back as plain
    numbers, so they go straight into the disruption, ELM and shot-fetching
    skills. `device` says which machine they are shots of.
    """
    sql = ["""SELECT s.name AS sample_name, e.device, sh.shot
                FROM materials.samples s
                JOIN materials.exposure_samples x USING (sample_key)
                JOIN materials.exposures e USING (exposure_id)
                JOIN materials.exposure_shots sh USING (exposure_id)
               WHERE 1=1"""]
    params = []
    names = _as_list(sample_names)
    if names is not None:
        sql.append("AND s.name IN (?)"); params.append(names)
    if device:
        sql.append("AND e.device IN (?)"); params.append(_as_list(device))
    sql.append("ORDER BY s.ordinal, sh.shot")
    out = {}
    for r in _query(" ".join(sql), tuple(params)):
        out.setdefault(r["sample_name"], []).append(r["shot"])
    return out


def samples_for_shots(shots, device=None):
    """{shot: [sample_name, ...]} -- the reverse join, also in one request.

    Answers "was anything exposed during these shots", for a whole shot list at
    once. A shot with no sample is absent from the result.
    """
    sql = ["""SELECT sh.shot, e.device, s.name AS sample_name
                FROM materials.exposure_shots sh
                JOIN materials.exposures e USING (exposure_id)
                JOIN materials.exposure_samples x USING (exposure_id)
                JOIN materials.samples s USING (sample_key)
               WHERE sh.shot IN (?)"""]
    params = [_as_list(shots)]
    if device:
        sql.append("AND e.device IN (?)"); params.append(_as_list(device))
    sql.append("ORDER BY sh.shot, s.ordinal")
    out = {}
    for r in _query(" ".join(sql), tuple(params)):
        out.setdefault(r["shot"], []).append(r["sample_name"])
    return out


# --------------------------------------------------------------------------
# files
# --------------------------------------------------------------------------

def artifacts(sample_names=None, shots=None, kind=None, delivery_id=None):
    """Catalogued files for a GROUP of samples or shots.

    Returns metadata only. `bytes = 0` means the file arrived empty; `notes`
    says so, and fetching it raises rather than handing back an empty body.
    """
    sql = ["""SELECT a.artifact_id, a.filename, a.kind, a.media_type, a.bytes,
                     a.notes, a.device, a.shot, a.delivery_id, a.metadata,
                     s.name AS sample_name
                FROM materials.artifacts a
                LEFT JOIN materials.samples s USING (sample_key)
               WHERE 1=1"""]
    params = []
    names = _as_list(sample_names)
    if names is not None:
        sql.append("AND s.name IN (?)"); params.append(names)
    sh = _as_list(shots)
    if sh is not None:
        sql.append("AND a.shot IN (?)"); params.append(sh)
    if kind:
        sql.append("AND a.kind IN (?)"); params.append(_as_list(kind))
    if delivery_id:
        sql.append("AND a.delivery_id = ?"); params.append(delivery_id)
    sql.append("ORDER BY a.kind, a.filename")
    return _query(" ".join(sql), tuple(params))


def read_data_file(artifact_id, dest=None, max_rows=None):
    """Fetch a delivered tabular text file and return (preamble, columns, rows).

    Instrument exports are usually a few lines of free-text preamble, then a
    header naming the columns, then numbers. Which lines are which differs by
    provider, so this finds the boundary instead of assuming it: the header is
    the last non-numeric line before numbers start.

    Returns
      preamble  list of str   -- the lines before the header, as written
      columns   list of str   -- the column names, as written
      rows      numpy array   -- float, shape (n, len(columns))

    Read the preamble. It commonly records what the numbers mean and what units
    they are in, and neither is recoverable from the numbers themselves.

    If the file is a raster -- one value per (time, position) and similar --
    pass the result to `as_grid()` before analysing it. Long-format grids
    punish row-wise filtering badly; see that function.
    """
    import numpy as np

    # The working directory, not a temp dir: the notebook agent is confined to
    # its working folder and may not read files outside it.
    path = fetch_artifact(artifact_id, dest=dest or working_dir())

    def numeric(line):
        parts = line.replace(",", " ").split()
        if not parts:
            return False
        try:
            [float(p) for p in parts]
            return len(parts) > 1
        except ValueError:
            return False

    preamble, columns, rows, header_seen = [], None, [], False
    with open(path, errors="replace") as fh:
        prev = None
        for line in fh:
            line = line.rstrip("\n")
            if not header_seen:
                if numeric(line):
                    header_seen = True
                    columns = (prev or "").split("\t")
                    if len(columns) < 2:
                        columns = (prev or "").split()
                    columns = [c.strip() for c in columns if c.strip()]
                    if preamble and preamble[-1] == prev:
                        preamble.pop()
                else:
                    if prev is not None:
                        preamble.append(prev)
                    prev = line
                    continue
            if numeric(line):
                parts = line.replace(",", " ").split()
                rows.append([float(p) for p in parts])
                if max_rows and len(rows) >= max_rows:
                    break
    arr = np.array(rows) if rows else np.empty((0, 0))
    if columns and arr.size and arr.shape[1] != len(columns):
        # A column name containing a space, or a ragged export. Keep the
        # numbers and say so rather than silently mislabelling them.
        columns = columns[:arr.shape[1]] + [
            "col%d" % i for i in range(len(columns), arr.shape[1])]
    return preamble, columns, arr


def as_grid(rows, columns=None):
    """Recognise a regular grid in a data file, and reshape it.

    Instrument exports are often a raster written long: an outer variable held
    constant while an inner one sweeps, repeated. `qpeak`-style heat-flux files
    are one value per (time, position), 1.5 million rows for a few dozen
    positions across sixty thousand time slices.

    Read long, that shape is a trap. Asking "which rows belong to this time?"
    with `rows[:, 0] == t` scans every row, and doing it once per time slice is
    quadratic: on one delivered file that is 94 billion comparisons and about
    ten minutes, to recover a structure the file's own header states. Reshaped,
    the same questions are array slices and take milliseconds.

    Returns None when the rows are not a regular grid, otherwise a dict:

        shape    (n_outer, n_inner)
        outer    index of the column held constant within a block
        values   {column name: array of shape (n_outer, n_inner)}
        axes     {column name: 1-D axis} for columns constant along an axis

    Detected from the data, not from the header, so a delivery that labels its
    dimensions differently -- or not at all -- is handled the same way.
    """
    import numpy as np

    if rows is None or getattr(rows, "size", 0) == 0 or rows.ndim != 2:
        return None
    n = rows.shape[0]

    # The outer variable is whichever column changes slowest: find the length
    # of the first run of equal values in each column.
    best = None
    for c in range(rows.shape[1]):
        col = rows[:, c]
        changes = np.flatnonzero(col[1:] != col[:-1])
        if changes.size == 0:
            continue                       # constant throughout -- not an axis
        block = int(changes[0]) + 1
        if block < 2 or block >= n or n % block:
            continue
        if best is None or block > best[1]:
            best = (c, block)
    if best is None:
        return None
    outer, inner = best[0], best[1]
    n_outer = n // inner

    # Every block must be the same size, and the inner sweep must repeat.
    oc = rows[:, outer].reshape(n_outer, inner)
    if not np.all(oc == oc[:, :1]):
        return None
    inner_cols = [c for c in range(rows.shape[1]) if c != outer]
    fast = None
    for c in inner_cols:
        g = rows[:, c].reshape(n_outer, inner)
        if np.allclose(g, g[:1], equal_nan=True):
            fast = c
            break
    if fast is None:
        return None                        # no repeating inner sweep: not a grid

    names = list(columns) if columns else ["col%d" % i for i in range(rows.shape[1])]
    out = {"shape": (n_outer, inner), "outer": names[outer], "inner": names[fast],
           "values": {}, "axes": {}}
    for c in range(rows.shape[1]):
        g = rows[:, c].reshape(n_outer, inner)
        out["values"][names[c]] = g
    out["axes"][names[outer]] = rows[:, outer].reshape(n_outer, inner)[:, 0]
    out["axes"][names[fast]] = rows[:, fast].reshape(n_outer, inner)[0]
    return out


def image_metadata(artifact_id):
    """Acquisition settings for one image, as recorded in the catalogue.

    Read from the catalogue, not downloaded: the settings were parsed when the
    delivery was catalogued, so asking for them across a whole set of images
    costs one query instead of one download each. Returns {} when the provider
    shipped no companion metadata for that file.
    """
    rows = _query("SELECT metadata FROM materials.artifacts WHERE artifact_id = ?",
                  (artifact_id,))
    return (rows[0]["metadata"] or {}) if rows else {}


def _re_sub(pattern, repl, text):
    """`re.sub`, imported here so the module keeps its lazy-import style."""
    import re
    return re.sub(pattern, repl, text)


def image_artifacts(sample_names=None, delivery_id=None, drop_near_duplicates=True):
    """Image files for a GROUP of samples, with their acquisition metadata.

    Deliveries often contain near-duplicate captures -- the same field at the
    same settings, saved seconds apart. Showing both says nothing twice, so by
    default one of each such pair is dropped: images whose companion metadata
    is identical except for a time-valued field are treated as the same
    picture. Pass drop_near_duplicates=False to see everything.

    Each row carries `represents` -- the number of delivered files it stands
    for -- so both populations are recoverable and neither can be quoted by
    accident:

        len(rows)                            images to look at (deduplicated)
        sum(r["represents"] for r in rows)   files as delivered

    Quoting a count from one of these beside a count from the other, without
    saying which is which, is inconsistent even though both numbers are right.
    """
    rows = [a for a in artifacts(sample_names=sample_names, delivery_id=delivery_id)
            if (a["media_type"] or "").startswith("image/")]
    for a in rows:
        a["metadata"] = a.get("metadata") or {}
    # Every row carries `represents`: how many delivered files it stands for.
    # Without it a count of these rows is ambiguous -- it is the deduplicated
    # population, but nothing on the row says so, and an answer that quotes it
    # beside a raw catalogue count for another sample is inconsistent while
    # every individual number is correct. That happened. So the row states its
    # own multiplicity, and both populations are recoverable:
    #
    #     len(rows)                      -> images to look at (deduplicated)
    #     sum(r["represents"] for r in rows) -> files as delivered
    #
    # Say which one you are quoting.
    if not drop_near_duplicates:
        for a in rows:
            a["represents"] = 1
        return rows
    seen, keep = {}, []
    for a in sorted(rows, key=lambda r: r["filename"]):
        # Acquisition settings alone do NOT identify a capture: an operator can
        # image two fields on one sample at the same magnification, voltage and
        # detector, and their metadata is then identical. Keying on settings
        # only, the second field is absorbed into the first and disappears from
        # the catalogue -- an image nobody can ask for. The filename separates
        # them, so it joins the key, with a one-letter variant suffix removed so
        # a raw/processed pair still collapses. Adding to the key can only
        # split, never merge: a delivery that names files differently gets less
        # deduplication, not a lost field.
        stem = _re_sub(r"\.[^.]+$", "", a["filename"])
        sig = (a["sample_name"], _re_sub(r"_[A-Za-z]$", "", stem),
               tuple(sorted((k, v) for k, v in a["metadata"].items()
                            if "TIME" not in k.upper() and "DATE" not in k.upper())))
        if not sig:
            a["represents"] = 1
            keep.append(a)
            continue
        if sig in seen:
            seen[sig]["represents"] += 1
            continue
        a["represents"] = 1
        seen[sig] = a
        keep.append(a)
    return keep


def load_image(artifact_id, dest=None):
    """Fetch one image and return it as a PIL Image, ready to display."""
    from PIL import Image
    return Image.open(fetch_artifact(artifact_id, dest=dest or working_dir()))


def show_images(artifact_ids, labels=None, ncols=3, width=4.2, title=None):
    """Display images side by side, for comparing samples.

    Comparing pictures taken at different magnifications shows a difference
    that is only zoom, so when the acquisition metadata records a magnification
    this raises rather than drawing a misleading figure. Pick one magnification
    and pass images from it.
    """
    import matplotlib.pyplot as plt
    ids = _as_list(artifact_ids)
    mags = set()
    metas = {a["artifact_id"]: (a["metadata"] or {})
             for a in _query("SELECT artifact_id, metadata FROM materials.artifacts "
                             "WHERE artifact_id IN (?)", (ids,))}
    for aid in ids:
        m = metas.get(aid, {})
        for key in m:
            if key.upper().endswith("MAG"):
                mags.add(m[key])
    if len(mags) > 1:
        raise ValueError(
            "these images were taken at different magnifications (%s); a "
            "side-by-side comparison of them shows zoom, not a difference in "
            "the samples. Choose one magnification."
            % ", ".join(sorted(mags)))
    n = len(ids)
    ncols = min(ncols, n)
    nrows = (n + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(width * ncols, width * nrows * 0.85))
    axes = [axes] if n == 1 else list(axes.ravel())
    for ax, aid in zip(axes, ids):
        ax.imshow(load_image(aid), cmap="gray")
        ax.set_xticks([]); ax.set_yticks([])
    if labels:
        for ax, lab in zip(axes, _as_list(labels)):
            ax.set_title(lab, fontsize=10)
    for ax in axes[n:]:
        ax.axis("off")
    if title:
        mag = mags.pop() if mags else None
        if mag and mag.isdigit():
            mag = "{:,}x".format(int(mag))
        fig.suptitle(title + (" -- %s" % mag if mag else ""), fontsize=11)
    fig.tight_layout()
    return fig


def save_figure(fig, filename, dpi=None):
    """Save a figure into the working folder and return its answer reference.

    Use this instead of `fig.savefig(...)`. It saves with
    `bbox_inches="tight"`, which is what keeps a legend placed beside the axes
    -- `bbox_to_anchor=(1.02, 0.5)`, the usual way to keep it clear of the
    data -- inside the saved image. That anchor puts the legend past the right
    edge of the canvas, and a plain `savefig` crops at the edge: the legend is
    drawn and then cut away, leaving a figure that looks deliberate with
    several unidentified curves on it. The kwarg is the whole difference, so
    it is applied here rather than left to each caller.

    Returns the markdown line that puts the figure in the answer. Paste it
    into the answer text -- a figure saved but never referenced is invisible
    to the reader, which is indistinguishable from never having made it.

        ref = mat.save_figure(fig, "lams_profiles_hmode.png")

    Prints a note when a curve cannot be identified from the figure alone:
    labelled curves with no legend, several curves carrying no labels, or one
    figure-level legend spanning panels whose series differ -- that last can
    name the series of only one panel. Fix what it names before moving on;
    the reader has only the figure.
    """
    root = os.path.realpath(working_dir())
    path = filename if os.path.isabs(filename) else os.path.join(root, filename)
    full = os.path.realpath(path)
    if full != root and not full.startswith(root + os.sep):
        raise ValueError(
            "%s is outside the working folder (%s), which is the only place "
            "the notebook can read a figure back from. Pass a bare filename, "
            "or a subfolder of it." % (filename, root))
    parent = os.path.dirname(full)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    for note in _figure_notes(fig):
        print("save_figure: %s" % note)
    fig.savefig(full, bbox_inches="tight", **({} if dpi is None else {"dpi": dpi}))
    name = os.path.relpath(full, root)
    return "![%s](%s)" % (_figure_alt(fig, name), name)


def _series_labels(ax):
    """The legend labels an axes would show, in order, ignoring the hidden."""
    return [lab for lab in ax.get_legend_handles_labels()[1]
            if lab and not lab.startswith("_")]


def _series_colors(ax):
    """Distinct line colours, as a stand-in for series count when unlabelled.

    Deduplicating by colour is what makes this usable on an errorbar plot,
    where the caps and bars are drawn as further lines in the colour of the
    series they belong to.
    """
    from matplotlib.colors import to_hex
    out = set()
    for line in ax.get_lines():
        try:
            out.add(to_hex(line.get_color()))
        except Exception:
            pass
    return out


def _errorbar_extents(ax):
    """The y range each error bar on an axes actually spans.

    Error bars live in the axes' containers, not its lines, so they are
    invisible to a check that only walks `ax.get_lines()`.
    """
    out = []
    for cont in getattr(ax, "containers", ()):
        cols = getattr(cont, "lines", (None, None, ()))
        cols = cols[2] if len(cols) > 2 else ()
        for col in cols or ():
            try:
                segments = col.get_segments()
            except Exception:
                continue
            for seg in segments:
                if len(seg):
                    ys = [point[1] for point in seg]
                    out.append((min(ys), max(ys)))
    return out


def _figure_notes(fig):
    """What a reader could not work out from this figure on its own."""
    notes = []
    axes = [ax for ax in fig.axes if ax.has_data()]
    if not axes:
        return notes
    labels = {id(ax): _series_labels(ax) for ax in axes}
    fig_legend = bool(getattr(fig, "legends", ()))
    ax_legend = any(ax.get_legend() is not None for ax in axes)
    if not fig_legend and not ax_legend:
        named = max((len(labels[id(ax)]) for ax in axes), default=0)
        if named > 1:
            notes.append(
                "%d labelled series and no legend on the figure -- add "
                "fig.legend(...) or ax.legend() so the curves can be told "
                "apart" % named)
        elif named == 0:
            drawn = max((len(_series_colors(ax)) for ax in axes), default=0)
            if drawn > 1:
                notes.append(
                    "%d curves drawn, none of them labelled -- pass label= on "
                    "each and add a legend" % drawn)
    if fig_legend and len(axes) > 1:
        distinct = {frozenset(labels[id(ax)]) for ax in axes if labels[id(ax)]}
        if len(distinct) > 1:
            notes.append(
                "one figure-level legend spans %d panels whose series labels "
                "differ, so it can name the series of only one of them -- "
                "label the series by what the panels share and put the rest "
                "in each panel title, or give every panel its own ax.legend()"
                % len(axes))
    hidden_low = hidden_high = bars = 0
    for ax in axes:
        top = ax.get_ylim()[1]
        log_y = ax.get_yscale() == "log"
        for low, high in _errorbar_extents(ax):
            bars += 1
            if log_y and low <= 0:
                hidden_low += 1
            elif high > top:
                hidden_high += 1
    if bars and (hidden_low or hidden_high):
        notes.append(
            "error bars are drawn but %d of %d are not visible in the plotted "
            "range (%d reach zero or below on a log axis, %d run above the "
            "top) -- set the y-limits from value+sigma and draw the lower end "
            "to a positive floor, or report the uncertainties in a table and "
            "describe the figure as showing values only"
            % (hidden_low + hidden_high, bars, hidden_low, hidden_high))
    return notes


def _figure_alt(fig, name):
    """Alt text for the reference: the figure's own title, else its filename."""
    text = ""
    try:
        text = fig.get_suptitle()
    except Exception:
        sup = getattr(fig, "_suptitle", None)
        text = sup.get_text() if sup is not None else ""
    if not text:
        for ax in fig.axes:
            if ax.get_title():
                text = ax.get_title()
                break
    return (text
            or os.path.splitext(os.path.basename(name))[0].replace("_", " ").strip()
            or os.path.basename(name))


_ARTIFACT_FACTS = {}


def _artifact_facts(artifact_id):
    """(filename, bytes) for one artifact, cached for the process.

    The catalogue is the authority on what a complete copy looks like, and it
    cannot change while a script runs.
    """
    if artifact_id not in _ARTIFACT_FACTS:
        rows = _query("SELECT filename, bytes, sha256 FROM materials.artifacts "
                      "WHERE artifact_id = ?", (artifact_id,))
        _ARTIFACT_FACTS[artifact_id] = (
            (rows[0]["filename"], rows[0]["bytes"], rows[0]["sha256"])
            if rows else (None, None, None))
    return _ARTIFACT_FACTS[artifact_id]


def _expected_filename(artifact_id):
    return _artifact_facts(artifact_id)[0]


def _expected_size(artifact_id):
    return _artifact_facts(artifact_id)[1]


def _expected_sha256(artifact_id):
    return _artifact_facts(artifact_id)[2]


_LOCAL_HASHES = {}


def _local_sha256(path):
    """sha256 of a local file, memoised on (path, size, mtime)."""
    import hashlib
    st = os.stat(path)
    key = (path, st.st_size, st.st_mtime_ns)
    if key not in _LOCAL_HASHES:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for block in iter(lambda: fh.read(1024 * 1024), b""):
                h.update(block)
        _LOCAL_HASHES[key] = h.hexdigest()
    return _LOCAL_HASHES[key]


_DOC_TEXT = {}

# Media types whose text can be extracted. Anything else is data, not prose.
_READABLE = ("text/", "application/pdf", "spreadsheet", "wordprocessing")


def documents(delivery_id=None, kind=None):
    """The delivery's readable documents -- reports, spreadsheets, datasheets.

    A delivery carries prose alongside its data: an exposure log, a summary
    workbook, a proposal. These record the things the tables cannot -- how an
    instrument was configured, what a column means, why a shot is missing.
    """
    rows = artifacts(delivery_id=delivery_id, kind=kind)
    # A text file that accompanies an image is that image's acquisition record,
    # already parsed into the catalogue -- not a document about the delivery.
    # Excluding them keeps this list to what a person would call a document,
    # and keeps a search over it fast.
    companions = set()
    for a in rows:
        if (a["media_type"] or "").startswith("image/"):
            companions.add((a.get("kind"), a["filename"].rsplit(".", 1)[0]))
    out = [a for a in rows
           if any(t in (a["media_type"] or "") for t in _READABLE)
           and (a.get("kind"), a["filename"].rsplit(".", 1)[0]) not in companions]
    return sorted(out, key=lambda a: (a["kind"] or "", a["filename"]))


def document_text(artifact_id):
    """Extract a document's text. Cached for the process."""
    if artifact_id in _DOC_TEXT:
        return _DOC_TEXT[artifact_id]
    rows = _query("SELECT filename, media_type FROM materials.artifacts "
                  "WHERE artifact_id = ?", (artifact_id,))
    if not rows:
        raise LookupError("no such artifact: %s" % artifact_id)
    mt = rows[0]["media_type"] or ""
    path = fetch_artifact(artifact_id)
    out = []
    try:
        if "pdf" in mt:
            from pypdf import PdfReader
            for i, page in enumerate(PdfReader(path).pages, 1):
                out.append("[page %d] %s" % (i, page.extract_text() or ""))
        elif "spreadsheet" in mt:
            import openpyxl
            wb = openpyxl.load_workbook(path, data_only=True)
            for ws in wb.worksheets:
                for r, row in enumerate(ws.iter_rows(values_only=True), 1):
                    cells = [str(c) for c in row if c is not None]
                    if cells:
                        out.append("[%s r%d] %s" % (ws.title, r, "\t".join(cells)))
        elif "wordprocessing" in mt:
            import docx
            d = docx.Document(path)
            for p in d.paragraphs:
                if p.text.strip():
                    out.append(p.text)
            for t in d.tables:
                for row in t.rows:
                    cells = [c.text.strip() for c in row.cells if c.text.strip()]
                    if cells:
                        out.append("\t".join(cells))
        else:
            out.append(open(path, errors="replace").read())
    except ImportError as e:
        raise RuntimeError(
            "cannot read %s: %s. The reader for this format is missing."
            % (rows[0]["filename"], e)) from None
    _DOC_TEXT[artifact_id] = "\n".join(out)
    return _DOC_TEXT[artifact_id]


def find_in_documents(pattern, delivery_id=None, context=90, max_hits=40,
                      ignore_case=True):
    """Search EVERY document in the delivery for a pattern, in one call.

    Answers "does this delivery say anything about X, and where?" -- the
    question that otherwise costs one script per file and per format.
    Spreadsheets, PDFs, Word documents and plain text are all searched; the
    caller does not need to know which format holds the answer.

    Returns hits as {filename, kind, artifact_id, line, text}, so a promising
    hit can be followed up with `document_text()` for full context.

    Searching for a unit, an instrument name or a column heading is usually
    more productive than searching for a number, since numbers are often
    formatted differently in prose than in a table.
    """
    import re as _re
    flags = _re.IGNORECASE if ignore_case else 0
    try:
        rx = _re.compile(pattern, flags)
    except _re.error as e:
        raise ValueError("bad search pattern %r: %s" % (pattern, e)) from None

    hits = []
    for a in documents(delivery_id=delivery_id):
        try:
            text = document_text(a["artifact_id"])
        except Exception as e:                                   # noqa: BLE001
            hits.append({"filename": a["filename"], "kind": a["kind"],
                         "artifact_id": a["artifact_id"], "line": None,
                         "text": "<unreadable: %s>" % e})
            continue
        for n, line in enumerate(text.splitlines(), 1):
            m = rx.search(line)
            if not m:
                continue
            lo = max(0, m.start() - context // 2)
            hits.append({"filename": a["filename"], "kind": a["kind"],
                         "artifact_id": a["artifact_id"], "line": n,
                         "text": line[lo:lo + context].strip()})
            if len(hits) >= max_hits:
                return hits
    return hits


def fetch_artifact(artifact_id, dest=None):
    """Download one catalogued file. Returns the path it was written to.

    Ask for it by `artifact_id`, from `artifacts()`. There is no path
    parameter: the server resolves the location itself, so a file that was not
    catalogued cannot be requested.
    """
    import urllib.error
    import urllib.request

    # endpoint() already carries the /FEDER prefix -- the same base the query
    # calls are built on. Appending it again yields /FEDER/FEDER and a 404 that
    # reads as a missing artifact rather than a wrong URL.
    # Already here? Do not fetch it again.
    #
    # An artifact is immutable -- its id is derived from its content path, and
    # a changed file is a new id -- so a local copy of the right size IS the
    # artifact. Re-downloading one costs a transfer and, worse, a write: on a
    # notebook whose working folder is network-backed, repeatedly rewriting
    # hundreds of megabytes puts a blocking filesystem write on the critical
    # path of every analysis. Several scripts in one session each re-pulling
    # the same files is the normal pattern, so this is the common case.
    dest = dest or working_dir()
    # Identity is the CONTENT, not the name and size.
    #
    # A delivery reuses filenames across samples -- one micrograph name appears
    # once per sample -- and uncompressed images of the same settings are
    # byte-identical in LENGTH while differing entirely in content. Keying the
    # cache on (filename, size) therefore returned the FIRST sample's image for
    # every later sample, silently: right name, right size, wrong picture. In
    # this delivery 88 (filename, size) pairs are shared by more than one
    # artifact and all 88 differ in content, so the collision was the rule
    # rather than the exception.
    #
    # The catalogue records a checksum per artifact, so the check verifies that.
    # Hashing is memoised on (path, size, mtime), and a mismatch means the name
    # is taken by a DIFFERENT artifact -- so the fetch goes to a disambiguated
    # path instead of overwriting a file another sample's analysis may hold.
    want = _expected_size(artifact_id)
    want_hash = _expected_sha256(artifact_id)
    _target = None
    if dest:
        cached = dest if os.path.isfile(dest) else os.path.join(
            dest, _expected_filename(artifact_id) or "")
        if want and os.path.isfile(cached) and os.path.getsize(cached) == want:
            try:
                if not want_hash or _local_sha256(cached) == want_hash:
                    return cached
            except OSError:
                pass
            # Same name, same length, different artifact.
            _stem, _ext = os.path.splitext(os.path.basename(cached))
            _target = os.path.join(os.path.dirname(cached),
                                   "%s__%s%s" % (_stem, artifact_id[:8], _ext))
            if (os.path.isfile(_target) and want
                    and os.path.getsize(_target) == want):
                try:
                    if not want_hash or _local_sha256(_target) == want_hash:
                        return _target
                except OSError:
                    pass

    url = "%s/materials/artifact/%s" % (_endpoint(), artifact_id)
    headers = {}
    tok = _token()
    if tok:
        headers["Authorization"] = "Bearer %s" % tok
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            name = _target or dest or resp.headers.get_filename() or artifact_id
            if _target is None and dest and os.path.isdir(dest):
                name = os.path.join(dest, resp.headers.get_filename() or artifact_id)
            with open(name, "wb") as fh:
                while True:
                    block = resp.read(1024 * 1024)
                    if not block:
                        break
                    fh.write(block)
            return name
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        if e.code == 409:
            raise ArtifactUnavailable(detail) from None
        if e.code == 404:
            raise LookupError("no such artifact: %s" % artifact_id) from None
        if e.code in (401, 403):
            raise LakehouseError(
                "this file needs a valid FDP token: %s" % detail) from None
        raise LakehouseError("HTTP %d fetching %s: %s"
                             % (e.code, artifact_id, detail[:300])) from None

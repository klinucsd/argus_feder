"""d3d-elm-index helper: query stored ELM labels and filterscope availability.

Local SQLite file -- no network, no fdp wrapper needed. Read-only.

WHAT THIS ANSWERS
-----------------
Anything derivable from three kinds of stored fact:
  1. ELM labels -- when a shot was ELMy, and when individual ELMs fired,
     produced by running a named detector at recorded parameters.
  2. Detector provenance -- which method/version/parameters produced a label,
     so two methods can be compared rather than silently mixed.
  3. Signal availability -- which filterscope channels a shot actually has,
     at what sampling rate, and why a channel is missing when it is.

It is NOT a list of canned answers. Compose the primitives below, or drop to
`query_elm_index(sql)` for anything they do not cover. `schema()` prints the
full table/column reference for writing that SQL.

WHAT THIS IS NOT
----------------
Not the raw waveform -- to fetch a D-alpha trace use d3d-filterscopes or
d3d-shot-fetcher. Not shot metadata -- for kappa, Ip, pulse length or the
signal catalog use d3d-relational-db. This skill holds derived ELM labels and
the availability facts collected while producing them.

The file is looked up under either filename (`elm.sqlite` or
`elm_index.sqlite`) in each folder in turn, matching the d3d-relational-db
lookup order so both databases are found the same way:
  1. $ELM_DB_PATH (explicit override -- exact file, not a folder)
  2. ~/work/_User-Persistent-Storage_CephBlock_/feder/  (NRP persistent)
  3. ~/feder_data/                                      (local dev)
  4. ~
  5. /content/                                          (Colab -- upload via file browser)
"""
import json
import os
import sqlite3

_FOLDERS = [
    "~/work/_User-Persistent-Storage_CephBlock_/feder",
    "~/feder_data",
    "~",
    "/content",
]
_FILENAMES = ["elm.sqlite", "elm_index.sqlite"]


class ShotNotIndexed(LookupError):
    """Raised when a shot has never been run through a detector.

    Deliberately an exception rather than an empty result. "No rows" for an
    un-analysed shot is indistinguishable from "analysed, no ELMs found", and
    reporting the first as the second is a factual error about the machine.
    Use `is_indexed(shot)` to test, or catch this.
    """


def locate_elm_db():
    """Return the path to the ELM index sqlite file, or None if not found."""
    candidates = []
    env_path = os.environ.get("ELM_DB_PATH")
    if env_path:
        candidates.append(env_path)
    for folder in _FOLDERS:
        for fname in _FILENAMES:
            candidates.append(os.path.expanduser(f"{folder}/{fname}"))
    for p in candidates:
        if p and os.path.exists(p):
            return p
    return None


def _connect():
    path = locate_elm_db()
    if not path:
        searched = ", ".join(
            os.path.expanduser(f"{folder}/{{{'|'.join(_FILENAMES)}}}") for folder in _FOLDERS
        )
        raise FileNotFoundError(
            f"ELM index not found. Searched $ELM_DB_PATH, then {searched}.\n"
            f"Fix: place your copy (either name, {' or '.join(_FILENAMES)}) in "
            "any of those folders -- on Colab, upload it via the file browser "
            "(folder icon, left sidebar); it lands at /content/ automatically. "
            "Note this must be re-uploaded each fresh Colab session."
        )
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        con.execute("SELECT 1 FROM sqlite_master LIMIT 1")
        return con
    except sqlite3.OperationalError:
        # A database left in WAL mode cannot be opened read-only unless its
        # -shm/-wal sidecars are present or the directory is writable: SQLite
        # reports the unhelpful "unable to open database file". Distributed
        # copies should be in rollback-journal mode, but a WAL copy is easy to
        # produce by accident, so fall back to immutable rather than failing.
        # Safe here because this file is only ever read.
        con.close()
        return sqlite3.connect(f"file:{path}?immutable=1", uri=True)


def query_elm_index(sql, params=()):
    """Run a read-only SQL query against the ELM index. Returns a list of dicts.

    The escape hatch: use this for anything the named functions do not cover.
    Call `schema()` for the table and column reference.
    """
    con = _connect()
    try:
        con.row_factory = sqlite3.Row
        return [dict(r) for r in con.execute(sql, params).fetchall()]
    finally:
        con.close()


def _default_run(granularity):
    """run_id of the run explicitly blessed for this granularity.

    This used to fall back to the newest run of the granularity when none was
    flagged. That is a silent-wrong-answer waiting to happen, and it happened:
    once human ground-truth and a 23-shot comparison run were loaded, "newest
    burst run" stopped meaning "the detector run over the whole index" and
    every unqualified answer would have quietly narrowed to 23 shots without
    anything looking broken.

    So there is no fallback. An index with no blessed run raises, and the
    caller picks a run_id deliberately.
    """
    rows = query_elm_index(
        """SELECT run_id FROM elm_runs
           WHERE granularity = ? AND superseded = 0 AND is_default = 1""",
        (granularity,))
    if len(rows) == 1:
        return rows[0]["run_id"]
    avail = [(r["run_id"], r["method"], r["granularity"]) for r in runs()
             if r["granularity"] == granularity]
    if not rows:
        raise LookupError(
            f"no run is marked default for granularity {granularity!r}, so "
            f"there is no safe implicit choice. Pass run_id= explicitly. "
            f"Candidates: {avail}")
    raise LookupError(
        f"{len(rows)} runs are marked default for {granularity!r} -- the index "
        f"is inconsistent. Pass run_id= explicitly. Candidates: {avail}")


# --------------------------------------------------------------------------
# Orientation -- call this first when you do not know what the index holds
# --------------------------------------------------------------------------

def _composition_caveat():
    """Describe how the indexed shots are distributed, computed not hardcoded.

    The index is built in batches with different sampling strategies, so a
    fixed sentence about its composition goes stale as soon as one is added --
    which has already happened once. Derive it instead.
    """
    rows = query_elm_index(
        """SELECT (shot / 10000) * 10000 AS decade, COUNT(DISTINCT shot) n
           FROM elm_run_shots GROUP BY decade ORDER BY n DESC""")
    total = sum(r["n"] for r in rows) or 1
    top = rows[0] if rows else None
    head = ""
    if top and top["n"] / total > 0.25:
        head = (f" {100*top['n']/total:.0f}% of it falls in shots "
                f"{top['decade']}-{top['decade']+9999} alone.")
    return (
        "The indexed shots are NOT a uniform sample of the archive: they are "
        "an even-stride sample plus a validation set plus one or more "
        f"contiguous blocks, spread over {len(rows)} shot-number decades."
        + head +
        " Any proportion computed over the whole index inherits that shape. "
        "For an archive-representative figure restrict to a known-unbiased "
        "shot list; for an era-representative one restrict to a contiguous "
        "block. Use coverage_summary() to see the distribution.")


def elm_index_info():
    """What this index contains and, importantly, what it does not.

    Call this before answering any question about coverage, totals or
    proportions. The index is a growing subset of the archive, not a census,
    and it is not a uniform sample -- see `caveats` in the returned dict.
    """
    info = {"path": locate_elm_db()}
    info["runs"] = runs()
    row = query_elm_index(
        """SELECT COUNT(DISTINCT shot) shots, MIN(shot) lo, MAX(shot) hi
           FROM elm_run_shots""")[0]
    info["shots_indexed"] = row["shots"]
    info["shot_range"] = (row["lo"], row["hi"])
    info["status_counts"] = {
        r["status"]: r["n"] for r in query_elm_index(
            """SELECT status, COUNT(DISTINCT shot) n FROM elm_run_shots
               GROUP BY status ORDER BY n DESC""")}
    # Name the method and the source, not just the run number. An agent
    # carrying stale context ("this index has one detector") has to be
    # contradicted HERE, in the orientation call, or it will not look further.
    # shots_indexed counts every shot ANY run touched, including shots that
    # only a human labelled. Quoting it as "shots analysed by the detector"
    # overstates detector coverage, so give that number separately.
    info["shots_with_detector_labels"] = query_elm_index(
        """SELECT COUNT(DISTINCT s.shot) n FROM elm_run_shots s
           JOIN elm_runs r ON r.run_id = s.run_id
           WHERE r.method NOT LIKE 'human%'""")[0]["n"]
    info["label_sources"] = [
        {"method": r["method"],
         "kind": _run_kind(r),
         "source": ("hand-labelled by a DIII-D expert"
                    if _run_meta(r)["is_ground_truth"] else "detector output"),
         "granularity": r["granularity"],
         "run_id": r["run_id"]}
        for r in info["runs"]]
    _methods = sorted({d["method"] for d in info["label_sources"]})
    _truth = sorted({d["method"] for d in info["label_sources"]
                     if d["source"].startswith("hand")})
    info["summary"] = (
        f"{len(_methods)} distinct labelling methods across "
        f"{len(info['label_sources'])} runs: {', '.join(_methods)}."
        + (f" {len(_truth)} of these are EXPERT GROUND TRUTH, not detector "
           f"output: {', '.join(_truth)}." if _truth else "")
        + " Never present them as interchangeable, and never total them."
        + f" Of {info['shots_indexed']} shots present, "
          f"{info['shots_with_detector_labels']} were analysed by a detector; "
          f"the rest carry only hand-made labels.")
    info["labels"] = {
        f"run {r['run_id']} ({r['granularity']})": r["n"] for r in query_elm_index(
            """SELECT r.run_id, r.granularity, COUNT(l.label_id) n
               FROM elm_runs r LEFT JOIN elm_labels l ON l.run_id = r.run_id
               GROUP BY r.run_id ORDER BY r.run_id""")}
    info["label_classes"] = [r["label"] for r in query_elm_index(
        "SELECT DISTINCT label FROM elm_labels ORDER BY label")]
    info["availability_rows"] = query_elm_index(
        "SELECT COUNT(*) n FROM signal_availability")[0]["n"]
    info["channels_tracked"] = [r["signal"] for r in query_elm_index(
        "SELECT DISTINCT signal FROM signal_availability ORDER BY signal")]
    info["caveats"] = [
        "This index holds MORE THAN ONE labelling method, and some of them are "
        "expert ground truth rather than detector output -- see `summary` and "
        "`label_sources`. Do not assume a single detector, do not add label "
        "counts across methods, and do not compare an ELM-event method against "
        "a regime-window method. Use compare_on_shot() and "
        "shots_with_multiple_sources().",
        "A shot absent from the index has NOT been analysed. That is not the "
        "same as 'no ELMs' -- see ShotNotIndexed.",
        "A 'labeled' status means the detector found D-alpha transients, NOT "
        "that the discharge was in ELMy H-mode. It declines only rarely, and "
        "when validated against discharges hand-labelled as QH-mode -- a "
        "regime with no ELMs -- it labelled every one. So there is no correct "
        "answer to 'what fraction of shots are ELMy'; the index cannot support "
        "that statement under any denominator. Use burst count and ELMy "
        "duration, which do separate regimes, rather than the binary label.",
        _composition_caveat(),
        "Only the label classes listed above are produced. Absence of a class "
        "(for example QH) means this detector does not emit it, NOT that the "
        "regime did not occur.",
        "Never compare counts across granularity: one 'interval' row is an "
        "ELMy phase, one 'burst' row is a single ELM.",
        "signal_snr is in dB and CAN BE NEGATIVE. The detector selects the "
        "best available channel, not a good one, and labels the shot anyway. "
        "Check signal_snr before presenting a shot's labels as reliable.",
    ]
    # DISTINCT: elm_run_shots has one row per (run, shot), so a plain COUNT
    # multiplies by the number of runs.
    info["low_snr_labeled_shots"] = query_elm_index(
        """SELECT COUNT(DISTINCT shot) n FROM elm_run_shots
           WHERE status = 'labeled' AND signal_snr < 0""")[0]["n"]
    return info


def schema():
    """Print the table and column reference, for writing SQL via query_elm_index."""
    con = _connect()
    try:
        for (name, kind, sql) in con.execute(
                """SELECT name, type, sql FROM sqlite_master
                   WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%'
                   ORDER BY type DESC, name"""):
            cols = [f"{r[1]} {r[2]}" for r in con.execute(f'PRAGMA table_info("{name}")')]
            n = con.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            print(f"{kind.upper()} {name}  ({n:,} rows)")
            for c in cols:
                print(f"    {c}")
            print()
    finally:
        con.close()


def runs():
    """Every detector execution in the index, with its provenance.

    A label is meaningless without this: the same detector at a different
    merge time produces a different product. `parameters` is JSON.
    """
    return query_elm_index(
        """SELECT run_id, method, method_version, granularity, parameters,
                  source_repo, source_commit, signal_candidates, created_at,
                  is_default, superseded, notes
           FROM elm_runs ORDER BY run_id""")


# --------------------------------------------------------------------------
# Per-shot
# --------------------------------------------------------------------------

def is_indexed(shot):
    """Has this shot been run through any detector?"""
    return bool(query_elm_index(
        "SELECT 1 FROM elm_run_shots WHERE shot = ? LIMIT 1", (shot,)))


def shot_status(shot, run_id=None):
    """Per-run outcome for one shot: status, channel used, SNR, window, count.

    Times (`t_start`, `t_end`) are in MILLISECONDS.

    status is one of:
      labeled     -- analysed, ELMs found
      none_found  -- analysed, genuinely no ELMs
      no_data     -- the signal could not be fetched (see `error`)
      error       -- data returned but unusable by this detector (see `error`)
    """
    if not is_indexed(shot):
        raise ShotNotIndexed(
            f"shot {shot} is not in the ELM index -- it has not been analysed. "
            "This is NOT evidence that the shot has no ELMs.")
    sql = """SELECT s.run_id, r.method, r.granularity, s.status, s.signal_used,
                    s.signal_snr, s.t_start, s.t_end, s.n_labels, s.error
             FROM elm_run_shots s JOIN elm_runs r ON r.run_id = s.run_id
             WHERE s.shot = ?"""
    p = [shot]
    if run_id is not None:
        sql += " AND s.run_id = ?"
        p.append(run_id)
    return query_elm_index(sql + " ORDER BY s.run_id", tuple(p))


def elm_windows(shot, run_id=None):
    """ELMy phases for a shot: [{start_time, end_time, label, ...}, ...] in ms.

    Interval granularity -- one row per continuous ELMy period. For individual
    ELMs use `elm_bursts`. Empty list means analysed-and-none-found; an
    un-analysed shot raises ShotNotIndexed instead.
    """
    rid = run_id if run_id is not None else _default_run("interval")
    if not is_indexed(shot):
        raise ShotNotIndexed(
            f"shot {shot} is not in the ELM index -- it has not been analysed.")
    return query_elm_index(
        """SELECT start_time, end_time, end_time - start_time AS duration_ms,
                  label, confidence, run_id
           FROM elm_labels WHERE shot = ? AND run_id = ? ORDER BY start_time""",
        (shot, rid))


def elm_bursts(shot, t_start=None, t_end=None, run_id=None):
    """Individual ELM events for a shot, optionally restricted to [t_start, t_end] ms.

    Burst granularity -- one row per ELM. Use for counting, frequency, or
    "the ELMs between 2000 and 3000 ms".
    """
    rid = run_id if run_id is not None else _default_run("burst")
    if not is_indexed(shot):
        raise ShotNotIndexed(
            f"shot {shot} is not in the ELM index -- it has not been analysed.")
    sql = """SELECT start_time, end_time, end_time - start_time AS duration_ms, label
             FROM elm_labels WHERE shot = ? AND run_id = ?"""
    p = [shot, rid]
    if t_start is not None:
        sql += " AND end_time >= ?"
        p.append(t_start)
    if t_end is not None:
        sql += " AND start_time <= ?"
        p.append(t_end)
    return query_elm_index(sql + " ORDER BY start_time", tuple(p))


def was_elmy_at(shot, time_ms, run_id=None):
    """Was the plasma in an ELMy phase at this time? Returns the window, or None.

    None means no ELMy phase covers that instant. It does NOT mean L-mode:
    the quiet period could be ELM-suppressed H-mode or QH-mode, neither of
    which this detector distinguishes.
    """
    rid = run_id if run_id is not None else _default_run("interval")
    rows = query_elm_index(
        """SELECT start_time, end_time, label FROM elm_labels
           WHERE shot = ? AND run_id = ? AND ? BETWEEN start_time AND end_time""",
        (shot, rid, time_ms))
    return rows[0] if rows else None


def elm_statistics(shot, interval_run=None, burst_run=None):
    """Derived per-shot ELM numbers: counts, ELMy duration, frequency, period.

    Frequency is bursts divided by total ELMy duration, so it is the rate
    *while ELMing*, not averaged over the whole shot.
    """
    if not is_indexed(shot):
        raise ShotNotIndexed(
            f"shot {shot} is not in the ELM index -- it has not been analysed.")
    iw = elm_windows(shot, interval_run)
    bs = elm_bursts(shot, run_id=burst_run)
    elmy_ms = sum(w["duration_ms"] for w in iw)
    out = {
        "shot": shot,
        "n_windows": len(iw),
        "n_bursts": len(bs),
        "elmy_duration_ms": elmy_ms,
        "first_elm_ms": bs[0]["start_time"] if bs else None,
        "last_elm_ms": bs[-1]["end_time"] if bs else None,
        "frequency_hz": (len(bs) * 1000.0 / elmy_ms) if elmy_ms > 0 else None,
        "mean_period_ms": (elmy_ms / len(bs)) if bs else None,
        "mean_burst_ms": (sum(b["duration_ms"] for b in bs) / len(bs)) if bs else None,
    }
    st = shot_status(shot)
    out["signal_used"] = st[0]["signal_used"] if st else None
    out["status"] = st[0]["status"] if st else None
    return out


# --------------------------------------------------------------------------
# Cohorts -- filter the indexed population
# --------------------------------------------------------------------------

def find_shots(shot_min=None, shot_max=None, status=None, signal_used=None,
               min_windows=None, min_elmy_ms=None, max_elmy_ms=None,
               min_bursts=None, label=None, limit=None):
    """Shots matching any combination of criteria. Returns rows with the numbers.

    Every argument is optional and they AND together. Searches only indexed
    shots -- a shot that matches but has not been analysed cannot appear.
    """
    iv, bu = _default_run("interval"), _default_run("burst")
    where, p = ["s.run_id = ?"], [iv]
    if shot_min is not None:
        where.append("s.shot >= ?"); p.append(shot_min)
    if shot_max is not None:
        where.append("s.shot <= ?"); p.append(shot_max)
    if status is not None:
        where.append("s.status = ?"); p.append(status)
    if signal_used is not None:
        where.append("s.signal_used = ?"); p.append(signal_used)

    having = []
    if min_windows is not None:
        having.append("n_windows >= ?");
    if min_elmy_ms is not None:
        having.append("elmy_ms >= ?")
    if max_elmy_ms is not None:
        having.append("elmy_ms <= ?")
    if min_bursts is not None:
        having.append("n_bursts >= ?")

    label_clause = " AND l.label = ?" if label else ""
    sql = f"""
        SELECT s.shot, s.status, s.signal_used, s.signal_snr,
               COUNT(l.label_id) AS n_windows,
               IFNULL(SUM(l.end_time - l.start_time), 0) AS elmy_ms,
               (SELECT COUNT(*) FROM elm_labels b
                 WHERE b.shot = s.shot AND b.run_id = ?) AS n_bursts
        FROM elm_run_shots s
        LEFT JOIN elm_labels l
               ON l.run_id = s.run_id AND l.shot = s.shot{label_clause}
        WHERE {' AND '.join(where)}
        GROUP BY s.shot
    """
    params = [bu] + ([label] if label else []) + p
    for v in (min_windows, min_elmy_ms, max_elmy_ms, min_bursts):
        if v is not None:
            params.append(v)
    if having:
        sql += " HAVING " + " AND ".join(having)
    sql += " ORDER BY s.shot"
    if limit:
        sql += f" LIMIT {int(limit)}"
    return query_elm_index(sql, tuple(params))


# --------------------------------------------------------------------------
# Signal availability -- what the archive holds, independent of any detector
# --------------------------------------------------------------------------

def signal_availability(shot=None, signal=None, shot_min=None, shot_max=None,
                        present=None, min_rate_khz=None, limit=None):
    """What each filterscope channel holds, per shot: samples, rate, units, error.

    UNITS: `t_start` and `t_end` are MILLISECONDS, matching every other time in
    this index. A typical shot runs 0.02 to 6000.0 -- that is 6 seconds, not
    6000. Reporting those as seconds is a 1000x error.

    Not keyed on a detector run -- availability is a property of the archive.
    `present=0` rows carry the reason in `error`.
    """
    where, p = ["1=1"], []
    for col, val in (("shot", shot), ("signal", signal), ("present", present)):
        if val is not None:
            where.append(f"{col} = ?"); p.append(val)
    if shot_min is not None:
        where.append("shot >= ?"); p.append(shot_min)
    if shot_max is not None:
        where.append("shot <= ?"); p.append(shot_max)
    if min_rate_khz is not None:
        where.append("rate_khz >= ?"); p.append(min_rate_khz)
    sql = (f"SELECT shot, signal, present, n_samples, t_start, t_end, rate_khz, "
           f"units, error FROM signal_availability WHERE {' AND '.join(where)} "
           f"ORDER BY shot, signal")
    if limit:
        sql += f" LIMIT {int(limit)}"
    return query_elm_index(sql, tuple(p))


def shots_with_signals(signals, shot_min=None, shot_max=None, min_rate_khz=None):
    """Indexed shots that have ALL of `signals` present (optionally above a rate).

    Returns {'have': [...], 'missing': [...], 'not_indexed_note': str} so the
    caller can tell "checked and absent" from "never checked".
    """
    if isinstance(signals, str):
        signals = [signals]
    ph = ",".join("?" * len(signals))
    where, p = [f"signal IN ({ph})", "present = 1"], list(signals)
    if shot_min is not None:
        where.append("shot >= ?"); p.append(shot_min)
    if shot_max is not None:
        where.append("shot <= ?"); p.append(shot_max)
    if min_rate_khz is not None:
        where.append("rate_khz >= ?"); p.append(min_rate_khz)
    have = [r["shot"] for r in query_elm_index(
        f"""SELECT shot FROM signal_availability WHERE {' AND '.join(where)}
            GROUP BY shot HAVING COUNT(DISTINCT signal) = {len(signals)}
            ORDER BY shot""", tuple(p))]

    rng, rp = ["1=1"], []
    if shot_min is not None:
        rng.append("shot >= ?"); rp.append(shot_min)
    if shot_max is not None:
        rng.append("shot <= ?"); rp.append(shot_max)
    checked = [r["shot"] for r in query_elm_index(
        f"SELECT DISTINCT shot FROM signal_availability WHERE {' AND '.join(rng)}",
        tuple(rp))]
    return {
        "have": have,
        "missing": sorted(set(checked) - set(have)),
        "not_indexed_note": (
            f"{len(checked)} shots in this range have been checked. Any shot in "
            "the range not listed in either group has never been fetched, and "
            "its availability is unknown -- not absent."),
    }


def coverage_summary(bucket=10000):
    """Indexed shots and usable fraction, bucketed by shot number.

    Shows where in the archive the index actually has data. Useful before
    quoting any proportion, and it is how the filterscope coverage boundary
    was found.
    """
    return query_elm_index(
        f"""SELECT (shot / {int(bucket)}) * {int(bucket)} AS bucket,
                   COUNT(DISTINCT shot) AS shots_indexed,
                   SUM(CASE WHEN status IN ('labeled','none_found') THEN 1 ELSE 0 END) AS usable,
                   SUM(CASE WHEN status = 'labeled' THEN 1 ELSE 0 END) AS labeled
            FROM elm_run_shots WHERE run_id = ?
            GROUP BY bucket ORDER BY bucket""", (_default_run("interval"),))


# --------------------------------------------------------------------------
# Comparing methods -- the reason provenance is stored
# --------------------------------------------------------------------------

# Measured on this archive over a 10,000-shot run, 2026-08-07.
#
# Two different "sizes" matter and confusing them understates cost 3x. The four
# candidate channels decode to ~9.6 MB of arrays per shot, but ~31 MB crosses
# the wire: reading four channels pulls whole tree files, and the spectroscopy
# tree holds ~900 tags. Quote the wire figure for transfer cost.
_MB_PER_SHOT_WIRE = 31.0        # measured: 44.6 GB over 1,400 shots
_MB_PER_SHOT_ARRAYS = 9.6       # what is actually decoded and used
#
# Time varies by an order of magnitude with Pelican's mood -- 1.4 s/shot on a
# good day, 15.8 s on a bad one, same shot. Run pelican_speed.py rather than
# trusting these. 0.91 s/shot is the measured average over the 10,000-shot run
# with 8 workers, which is the sensible way to run a bulk job.
_SEC_PER_SHOT_SERIAL = 1.4
_SEC_PER_SHOT_8_WORKERS = 0.91
_SEC_PER_SHOT_NO_DATA = 0.65    # below the coverage boundary; a fast tree miss
#
# Between 130000 and the boundary a miss is NOT cheap: the tree exists but the
# data does not, so the archive searches before giving up (~6 s/shot).
_FIRST_SHOT_WITH_FILTERSCOPE = 130882   # located exactly by contiguous scanning


def fetch_estimate(shots):
    """Cost of fetching raw filterscope data for `shots`, from measured rates.

    Use this to make a concrete offer when a question needs a shot the index
    does not cover -- "~48 MB, about 7 s" beats "it might take a while", and
    stops the numbers being invented. Returns a dict; nothing is fetched.

    Note `can_label`: the raw trace can be fetched with d3d-filterscopes, but
    GA's detector is not installed here, so NEW ELM LABELS cannot be produced
    in the notebook. Availability, sampling rate and the trace itself are
    obtainable; a label is not.
    """
    if isinstance(shots, int):
        shots = [shots]
    shots = sorted(set(shots))
    already = {s for s in shots if is_indexed(s)}
    todo = [s for s in shots if s not in already]
    # Shots below the coverage boundary almost certainly return nothing, and a
    # miss is cheaper than a hit -- worth saying so rather than over-quoting.
    likely_empty = [s for s in todo if s < _FIRST_SHOT_WITH_FILTERSCOPE]
    likely_data = [s for s in todo if s >= _FIRST_SHOT_WITH_FILTERSCOPE]
    serial = (len(likely_data) * _SEC_PER_SHOT_SERIAL
              + len(likely_empty) * _SEC_PER_SHOT_NO_DATA)
    parallel = (len(likely_data) * _SEC_PER_SHOT_8_WORKERS
                + len(likely_empty) * _SEC_PER_SHOT_NO_DATA)
    return {
        "requested": len(shots),
        "already_indexed": sorted(already),
        "would_fetch": todo,
        "megabytes": round(len(likely_data) * _MB_PER_SHOT_WIRE, 1),
        "megabytes_note": (
            f"{_MB_PER_SHOT_WIRE} MB/shot crosses the wire; only "
            f"{_MB_PER_SHOT_ARRAYS} MB/shot is decoded and used"),
        "seconds": round(serial, 1),
        "seconds_8_workers": round(parallel, 1),
        "likely_no_data": likely_empty,
        "can_answer_by_fetching": [
            "which filterscope channels exist for the shot",
            "sampling rate and time coverage",
            "the raw D-alpha trace itself (plot, peak counting)",
        ],
        "can_NOT_answer_by_fetching": [
            "ELM labels from GA's detector -- mode_classifier is not installed "
            "in this image, so new labels cannot be produced here",
        ],
        "basis": (f"measured over a 10,000-shot run: {_MB_PER_SHOT_WIRE} MB/shot "
                  f"on the wire, {_SEC_PER_SHOT_SERIAL}s/shot serial or "
                  f"{_SEC_PER_SHOT_8_WORKERS}s/shot with 8 workers. Throughput "
                  f"varies ~10x day to day -- run pelican_speed.py to check."),
    }


def compare_runs(run_a, run_b, shot=None):
    """Per-shot label counts from two runs side by side, with their metadata.

    Guards the granularity trap: comparing an interval run against a burst run
    is meaningless, so the differing granularity is returned explicitly for
    the caller to check rather than silently differenced.
    """
    meta = {r["run_id"]: r for r in runs()}
    for rid in (run_a, run_b):
        if rid not in meta:
            raise LookupError(f"no run {rid}; have {sorted(meta)}")
    # The shot list must be DISTINCT: elm_run_shots holds one row per (run,
    # shot), so joining labels against it directly counts every label once per
    # run being compared -- silently doubling both columns.
    sql = """
        SELECT s.shot,
               SUM(CASE WHEN l.run_id = ? THEN 1 ELSE 0 END) AS n_a,
               SUM(CASE WHEN l.run_id = ? THEN 1 ELSE 0 END) AS n_b
        FROM (SELECT DISTINCT shot FROM elm_run_shots WHERE run_id IN (?, ?)) s
        LEFT JOIN elm_labels l ON l.shot = s.shot AND l.run_id IN (?, ?)
    """
    p = [run_a, run_b, run_a, run_b, run_a, run_b]
    if shot is not None:
        sql += " WHERE s.shot = ?"
        p.append(shot)
    rows = query_elm_index(sql + " GROUP BY s.shot ORDER BY s.shot", tuple(p))
    return {
        "run_a": meta[run_a],
        "run_b": meta[run_b],
        "comparable": meta[run_a]["granularity"] == meta[run_b]["granularity"],
        "granularity_warning": (
            None if meta[run_a]["granularity"] == meta[run_b]["granularity"] else
            f"run {run_a} is {meta[run_a]['granularity']!r} and run {run_b} is "
            f"{meta[run_b]['granularity']!r} -- these are different products. "
            "Counts are not comparable; report them separately."),
        "per_shot": rows,
    }


# --------------------------------------------------------------------------
# Label sets that are not ours: hand-labelled ground truth, and other detectors
# --------------------------------------------------------------------------

# A run's granularity says how finely it cuts time. It does NOT say what the
# labels mean. Two 'interval' runs can be a detector's merged ELM phases and a
# human's confinement-regime windows -- same granularity, completely different
# statements. Differencing them produces a number that looks fine and means
# nothing, which is exactly the failure the granularity guard was built to stop.
KIND_ELM_EVENTS = "elm_events"
KIND_REGIME = "regime_windows"

# Only a fallback: a regime run should name its own quiescent classes.
DEFAULT_QUIESCENT_CLASSES = ("QH", "BBQH", "WPQH", "WBQH", "QM")

# Fallbacks only. A run should DECLARE these in its own `parameters`; these
# values are used when it does not, so an older run still renders sensibly.
DEFAULT_REGIME_MEANINGS = {
    "ELMy H": "ELMing H-mode -- the plasma IS producing ELMs",
    "QH": "Quiescent H-mode -- good confinement, no ELMs, edge oscillates instead",
    "BBQH": "Broad-Band Quiescent H-mode",
    "WPQH": "Wide-Pedestal Quiescent H-mode",
}


def _ground_truth_methods():
    """Method names this index declares as expert-produced. Never hardcoded."""
    return {r["method"] for r in runs() if _run_meta(r)["is_ground_truth"]}


def _params(run):
    try:
        return json.loads(run.get("parameters") or "{}") or {}
    except (ValueError, TypeError):
        return {}


def _run_meta(run):
    """What a run declares about itself.

    Everything here is READ FROM THE RUN, never inferred from a method name we
    happen to recognise. A method this module has never heard of must work as
    well as the ones that existed when it was written, so a new detector or a
    new expert label set needs no code change here -- only correct
    `parameters` at load time.

    Recognised keys in `parameters`:
      kind               'elm_events' | 'regime_windows'
      produced_by        'human' | 'detector'
      class_meanings     {label: plain-English meaning}
      quiescent_classes  [label, ...] -- classes in which a detector firing is
                         notable (only meaningful for regime runs)

    The fallbacks below keep older runs, written before these keys existed,
    behaving as they did.
    """
    p = _params(run)
    kind = str(p.get("kind") or "")
    if kind not in (KIND_ELM_EVENTS, KIND_REGIME):
        kind = KIND_REGIME if "regime" in kind.lower() else KIND_ELM_EVENTS
    produced = str(p.get("produced_by") or "").lower()
    if produced not in ("human", "detector"):
        # Legacy fallback: the first ground-truth runs were named human_*.
        produced = "human" if str(run.get("method", "")).startswith("human") else "detector"
    return {
        "kind": kind,
        "produced_by": produced,
        "is_ground_truth": produced == "human",
        # One name per method, declared by the run. Without this the stored
        # method name ('slope_outlier') and the name a person uses ('GA's
        # mode_classifier detector') drift apart, and the same thing gets two
        # names in one answer.
        "display_name": p.get("display_name") or run.get("method"),
        "class_meanings": p.get("class_meanings") or DEFAULT_REGIME_MEANINGS,
        "quiescent_classes": tuple(p.get("quiescent_classes")
                                   or DEFAULT_QUIESCENT_CLASSES),
    }


def _run_kind(run):
    """What a run's labels assert. Reads the run's own declaration."""
    return _run_meta(run)["kind"]


def label_sets():
    """Every label set in the index, with who produced it and what it asserts.

    Call this before any cross-method question. The index holds both machine
    output and hand-labelled ground truth, and conflating them is the easiest
    mistake to make here.
    """
    counts = {r["run_id"]: r["n"] for r in query_elm_index(
        "SELECT run_id, COUNT(DISTINCT shot) n FROM elm_run_shots GROUP BY run_id")}
    # Per-status counts, so "how often did this method fail?" is a lookup.
    # Deriving it from zero-event shots silently merges two different things:
    # a method that ran and found nothing, and one that crashed.
    status = {}
    for r in query_elm_index(
            "SELECT run_id, status, COUNT(*) n FROM elm_run_shots GROUP BY run_id, status"):
        status.setdefault(r["run_id"], {})[r["status"]] = r["n"]
    out = []
    for r in runs():
        human = _run_meta(r)["is_ground_truth"]
        out.append({
            "run_id": r["run_id"],
            "method": r["method"],
            "display_name": _run_meta(r)["display_name"],
            "granularity": r["granularity"],
            "kind": _run_kind(r),
            "source": "hand-labelled by a domain expert" if human else "detector output",
            "is_ground_truth": human,
            "shots": counts.get(r["run_id"], 0),
            "status_counts": status.get(r["run_id"], {}),
            "n_failed": status.get(r["run_id"], {}).get("error", 0),
            "n_ran_and_found_nothing": status.get(r["run_id"], {}).get("none_found", 0),
            "is_default": bool(r.get("is_default")),
            "notes": r.get("notes"),
        })
    return {
        "runs": out,
        "guidance": (
            "When reporting how often a method failed, read `n_failed` "
            "(status 'error') -- never count shots with zero events, which "
            "merges a crash with an honest 'ran and found nothing' "
            "(`n_ran_and_found_nothing`). "
            "Ground-truth runs are scoped: they cover only the shots and time "
            "windows a person actually labelled. Never read absence in a "
            "ground-truth run as 'no ELM happened' outside that scope, and "
            "never compare a run of kind 'regime_windows' against one of kind "
            "'elm_events' -- see compare_on_shot(), which enforces both."),
    }


def _regime_at(windows, t):
    """The most specific hand-labelled regime covering `t`, or None.

    The expert's windows OVERLAP: narrow ELMy H intervals are nested inside
    broad QH/WPQH spans, marking ELMy stretches within an otherwise quiescent
    phase. Taking the first window that contains a time therefore assigns those
    bursts to the enclosing quiescent span and badly overstates how often a
    detector fires "during quiescence" -- on shot 163518 it turned 44 quiescent
    bursts into 75.

    The narrower window is the more specific claim, so it wins; ties go to the
    one that starts later.
    """
    hits = [w for w in windows if w["start_ms"] <= t <= w["end_ms"]]
    if not hits:
        return None
    return min(hits, key=lambda w: (w["end_ms"] - w["start_ms"], -w["start_ms"]))


def regime_windows(shot, run_id=None):
    """Hand-labelled confinement-regime windows for a shot, in ms.

    This is ground truth about which regime the plasma was in -- ELMing H-mode
    or one of the quiescent variants -- NOT a list of ELMs.
    """
    allruns = {r["run_id"]: r for r in runs()}
    if run_id is None:
        cand = [rid for rid, r in allruns.items() if _run_kind(r) == KIND_REGIME]
        if not cand:
            raise LookupError("this index holds no regime-labelled run")
        if len(cand) > 1:
            raise LookupError(
                f"this index holds {len(cand)} regime-labelled runs "
                f"{[(rid, allruns[rid]['method']) for rid in cand]}; pass "
                f"run_id= to say which one. Picking one silently would attribute "
                f"one labeller's regimes to another.")
        run_id = cand[0]
    means = _run_meta(allruns[run_id])["class_meanings"] if run_id in allruns else {}
    rows = query_elm_index(
        """SELECT start_time, end_time, label FROM elm_labels
           WHERE run_id = ? AND shot = ? ORDER BY start_time""", (run_id, shot))
    if not rows:
        raise ShotNotIndexed(
            f"shot {shot} has no hand-labelled regime windows (run {run_id}). "
            f"Only a few hundred shots were labelled; absence here means "
            f"'nobody labelled it', not 'no regime'.")
    return [{"start_ms": r["start_time"], "end_ms": r["end_time"],
             "regime": r["label"], "means": means.get(r["label"], "")}
            for r in rows]


def regime_at(shot, time_ms, run_id=None):
    """Which hand-labelled regime the plasma was in at a moment, if any.

    Time outside every labelled window returns None with a reason: MODE_INFO
    records L-mode as the unlabelled background, so unlabelled does not mean
    unknown in every case -- but it does mean nobody asserted anything.
    """
    w = _regime_at(regime_windows(shot, run_id), time_ms)
    if w:
        return w
    return {"regime": None, "means": "no hand-labelled regime covers this time "
            "(unlabelled background, which the source documents as L-mode)"}


def compare_on_shot(shot, run_ids=None):
    """Put several label sets side by side for one shot, safely.

    Two guards, both of which exist because getting them wrong yields a
    plausible-looking number:

    1. Runs of different `kind` are never compared. Regime windows and ELM
       events are different statements.
    2. Counts are clipped to the intersection of the runs' analysis windows.
       Hand-labelled runs often cover only a slice of the discharge -- one is
       17 ms long -- so an unclipped whole-shot run would show hundreds of
       'extra' events it never claimed were in that window.
    """
    meta = {r["run_id"]: r for r in runs()}
    if run_ids is None:
        run_ids = [rid for rid, r in meta.items()
                   if query_elm_index("SELECT 1 FROM elm_run_shots WHERE run_id=? AND shot=?",
                                      (rid, shot))]
    if not run_ids:
        raise ShotNotIndexed(f"shot {shot} appears in no run of this index")

    kinds = {rid: _run_kind(meta[rid]) for rid in run_ids}
    grans = {rid: meta[rid]["granularity"] for rid in run_ids}
    event_runs = [rid for rid in run_ids if kinds[rid] == KIND_ELM_EVENTS]

    # The comparable window is the intersection of every scoped run's window.
    lo, hi = None, None
    for rid in event_runs:
        row = query_elm_index(
            "SELECT t_start, t_end FROM elm_run_shots WHERE run_id=? AND shot=?",
            (rid, shot))
        if row and row[0]["t_start"] is not None:
            lo = row[0]["t_start"] if lo is None else max(lo, row[0]["t_start"])
            hi = row[0]["t_end"] if hi is None else min(hi, row[0]["t_end"])

    rows = []
    for rid in event_runs:
        st = query_elm_index(
            "SELECT status, error FROM elm_run_shots WHERE run_id=? AND shot=?",
            (rid, shot))
        clip = ("", ()) if lo is None else (
            " AND end_time >= ? AND start_time <= ?", (lo, hi))
        n = query_elm_index(
            "SELECT COUNT(*) c FROM elm_labels WHERE run_id=? AND shot=?" + clip[0],
            (rid, shot) + clip[1])[0]["c"]
        rows.append({
            "run_id": rid, "method": meta[rid]["method"],
            "display_name": _run_meta(meta[rid])["display_name"],
            "granularity": grans[rid],
            "source": ("ground truth" if _run_meta(meta[rid])["is_ground_truth"]
                       else "detector"),
            "n_events_in_window": n,
            "status": st[0]["status"] if st else "not in this run",
            "error": st[0]["error"] if st else None,
        })

    out = {
        "shot": shot,
        "comparable_window_ms": None if lo is None else [lo, hi],
        "event_level": sorted(rows, key=lambda r: r["run_id"]),
    }
    regime = [rid for rid in run_ids if kinds[rid] == KIND_REGIME]
    if regime:
        try:
            out["regime_context"] = regime_windows(shot, regime[0])
        except ShotNotIndexed:
            out["regime_context"] = None
        out["note"] = ("Regime windows are shown as CONTEXT only. They are not "
                       "counted alongside ELM events -- a regime window is not "
                       "an ELM.")
    if any(r["status"] == "error" for r in rows):
        out["warning"] = ("At least one detector failed on this shot and "
                          "produced zero events. Zero-because-it-crashed is "
                          "not zero-because-it-found-nothing; do not read it "
                          "as agreement with a ground truth of 0.")
    mixed = {grans[rid] for rid in event_runs}
    if len(mixed) > 1:
        out["granularity_warning"] = (
            f"event-level runs span granularities {sorted(mixed)}; counts are "
            f"NOT comparable across them")
    return out


def plot_comparison(shot, dalpha=None, run_ids=None, ax=None, figsize=(9.5, None),
                    show_duplicates=False):
    """Draw every label set for a shot as parallel tracks, over a regime strip.

    The point of the figure is not that the runs disagree -- counts already say
    that -- but WHERE they disagree relative to ground truth. So each event is
    coloured by the hand-labelled regime it falls in, and each row is annotated
    with how many of its events landed in a quiescent window, where a correct
    detector should find almost nothing.

    `dalpha` optionally overlays the trace ({'times':..., 'data':...} from
    d3d-filterscopes); the figure renders fine without it, since this skill
    must not require the network.

    Runs whose events are identical to an earlier run are dropped by default:
    the same execution over a different shot set draws an identical row and
    only adds clutter. `show_duplicates=True` keeps them.
    """
    import matplotlib.pyplot as plt

    # Palette by position, not by method name: a detector this module has
    # never heard of still gets its own colour.
    DETECTOR_COLOURS = ["#1f5fa8", "#c1272d", "#1a7f5a", "#8a5cc4", "#b06c00"]
    CLASS_COLOURS = ["#e8a0a0", "#8fb8dd", "#b09fd8", "#8fd0dd", "#d8c48f", "#a8d8a8"]

    cmp_ = compare_on_shot(shot, run_ids)
    meta = {r["run_id"]: r for r in runs()}
    rmeta = {rid: _run_meta(r) for rid, r in meta.items()}
    rows = list(cmp_["event_level"])
    dropped_gran = []
    if run_ids is None and any(r["granularity"] == "burst" for r in rows):
        dropped_gran = [r for r in rows if r["granularity"] != "burst"]
        rows = [r for r in rows if r["granularity"] == "burst"]
    rows.sort(key=lambda r: (r["source"] != "ground truth", r["run_id"]))

    lo, hi = cmp_["comparable_window_ms"] or (None, None)
    regime = cmp_.get("regime_context") or []

    reg_runs = [rid for rid in meta if rmeta[rid]["kind"] == KIND_REGIME]
    rm = rmeta[reg_runs[0]] if reg_runs else None
    QUIESCENT = tuple(rm["quiescent_classes"]) if rm else DEFAULT_QUIESCENT_CLASSES

    def regime_of(t):
        w = _regime_at(regime, t)
        return w["regime"] if w else None

    # Fetch once; needed for dedup, colouring and the per-row breakdown.
    ev = {}
    for st in rows:
        q = query_elm_index(
            "SELECT start_time, end_time FROM elm_labels WHERE run_id=? AND shot=? "
            "ORDER BY start_time", (st["run_id"], shot))
        ev[st["run_id"]] = [(r["start_time"], r["end_time"]) for r in q]

    if lo is None:
        lo = min([e[0] for v in ev.values() for e in v] or [0])
        hi = max([e[1] for v in ev.values() for e in v] or [1])

    def clipped(rid):
        return tuple((round(max(a, lo), 3), round(min(b, hi), 3))
                     for a, b in ev[rid] if b >= lo and a <= hi)

    dup = {}
    if not show_duplicates:
        keep, seen = [], {}
        for st in rows:
            sig = clipped(st["run_id"])
            if sig and sig in seen:
                dup[st["run_id"]] = seen[sig]
                continue
            seen[sig] = st["run_id"]
            keep.append(st)
        rows = keep

    n = len(rows)
    if ax is None:
        # Height floors against width. A notebook scales the image to the cell
        # width, so a very wide, short figure renders about an inch tall and the
        # tracks become unreadable regardless of how many rows there are.
        auto = (1.35 + 0.62 * n + (0.55 if regime else 0)
                + (1.1 if dalpha is not None else 0))
        h = figsize[1] or max(auto, figsize[0] / 2.4)
        _, ax = plt.subplots(figsize=(figsize[0], h))

    # Only reserve the strip row when there is actually a regime to draw --
    # otherwise every unlabelled shot renders with a band of dead space.
    strip = n
    top = n + (1 if regime else 0.15) + (1.3 if dalpha is not None else 0)

    # Type scales with width: the host renders this at a fixed pixel width, so
    # 8pt in an 11-inch figure and 8pt in a 14-inch figure are NOT the same size
    # on screen. Sizes below are quoted for a 9.5-inch figure.
    fs = ax.figure.get_size_inches()[0] / 9.5
    minw = (hi - lo) / 350.0          # keep single ELMs visible at this scale

    # --- regime strip -----------------------------------------------------
    classes = []
    for w in regime:
        if w["regime"] not in classes:
            classes.append(w["regime"])
    FILL = {c: CLASS_COLOURS[i % len(CLASS_COLOURS)] for i, c in enumerate(classes)}
    if regime:
        for w in regime:
            a, b = max(w["start_ms"], lo), min(w["end_ms"], hi)
            if b <= a:
                continue
            ax.barh(strip + 0.5, b - a, left=a, height=0.70,
                    color=FILL.get(w["regime"], "0.8"), lw=0)
            if (b - a) > (hi - lo) * 0.06:
                ax.text((a + b) / 2, strip + 0.5, w["regime"], ha="center",
                        va="center", fontsize=10 * fs, color="#1a1a1a")
        ax.text(lo - (hi - lo) * 0.012, strip + 0.5, "hand-labelled\nregime",
                ha="right", va="center", fontsize=11 * fs, color="#1a1a1a")

    if dalpha is not None:
        t = [x for x in dalpha["times"] if lo <= x <= hi]
        idx = [i for i, x in enumerate(dalpha["times"]) if lo <= x <= hi]
        y = [dalpha["data"][i] for i in idx]
        if y:
            span = (max(y) - min(y)) or 1.0
            ax.plot(t, [strip + 1.15 + 1.05 * (v - min(y)) / span for v in y],
                    lw=0.5, color="0.3")
            ax.text(lo - (hi - lo) * 0.012, strip + 1.65, "D-alpha", ha="right",
                    va="center", fontsize=11 * fs, color="0.3")

    # --- one row per label set -------------------------------------------
    ticks, ticklabels, colours, det_seen = [], [], [], {}
    for i, st in enumerate(rows):
        row = n - 1 - i
        rid = st["run_id"]
        r = meta[rid]
        human = st["source"] == "ground truth"
        base = ("#111111" if human else
                DETECTOR_COLOURS[det_seen.setdefault(r["method"], len(det_seen))
                                 % len(DETECTOR_COLOURS)])
        inq = 0
        for a, b in ev[rid]:
            if b < lo or a > hi:
                continue
            reg = regime_of((a + b) / 2.0)
            if reg in QUIESCENT:
                inq += 1
            ax.barh(row + 0.5, max(b - a, minw), left=a, height=0.66,
                    color=FILL.get(reg, base) if reg else base, lw=0)
        # outline in the run's own colour so rows stay distinguishable
        ax.barh(row + 0.5, 0, left=lo, height=0.66, color=base)
        ticks.append(row + 0.5)
        colours.append(base)
        nin = st["n_events_in_window"]
        tag = "ground truth" if human else "detector"
        extra = f"  |  {inq} in quiescent" if regime and nin else ""
        crashed = "   CRASHED" if st["status"] == "error" else ""
        ticklabels.append(f"{rmeta[rid]['display_name']}  ({tag})\n"
                          f"n={nin}{extra}{crashed}")

    ax.set_xlim(lo, hi)
    ax.set_ylim(0, top)
    ax.set_yticks(ticks)
    ax.set_yticklabels(ticklabels, fontsize=11 * fs)
    for lbl, c in zip(ax.get_yticklabels(), colours):
        lbl.set_color(c)
    ax.tick_params(axis="y", length=0)
    ax.tick_params(axis="x", labelsize=11 * fs)
    ax.set_xlabel("time (ms)", fontsize=11 * fs)
    ax.set_title(f"DIII-D shot {shot}: who says an ELM happened, and where",
                 fontsize=14 * fs, loc="left", pad=26)
    sub = []
    if lo is not None:
        sub.append(f"comparable window {lo:.0f}-{hi:.0f} ms")
    if regime:
        sub.append("events coloured by the hand-labelled regime they fall in")
    if dup:
        sub.append("identical run(s) hidden: "
                   + ", ".join(f"run {k} = run {v}" for k, v in dup.items()))
    if dropped_gran:
        sub.append("interval run(s) omitted: "
                   + ", ".join(f"run {d['run_id']}" for d in dropped_gran))
    if sub:
        ax.text(0, 1.012, "   |   ".join(sub), transform=ax.transAxes,
                fontsize=9.5 * fs, color="0.4", va="bottom")
    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
    ax.grid(axis="x", color="0.9", lw=0.6)
    ax.set_axisbelow(True)
    return ax


def shots_with_multiple_sources(min_sources=2, require_ground_truth=False, limit=50):
    """Shots labelled by more than one source -- the ones worth comparing.

    Answers "find me a shot where several methods can be compared" without the
    caller having to know any shot numbers, which is the normal situation: a
    user asking about detector agreement has no way to guess which discharges
    carry which labels.

    Counts distinct METHODS, not runs. Runs 1 and 2 are the same detector at
    two granularities; counting runs would report every indexed shot as having
    "two sources" when it has one.
    """
    rows = query_elm_index(
        """SELECT s.shot,
                  COUNT(DISTINCT r.method) AS n_sources,
                  GROUP_CONCAT(DISTINCT r.method) AS methods,
                  SUM(CASE WHEN r.method LIKE 'human%' THEN 1 ELSE 0 END) AS n_truth
             FROM elm_run_shots s JOIN elm_runs r ON r.run_id = s.run_id
            WHERE r.superseded = 0
            GROUP BY s.shot
           HAVING n_sources >= ?
            ORDER BY n_sources DESC, s.shot""", (min_sources,))
    out = []
    for r in rows:
        methods = sorted(str(r["methods"]).split(","))
        truth = [m for m in methods if m in _ground_truth_methods()]
        if require_ground_truth and not truth:
            continue
        out.append({
            "shot": r["shot"],
            "n_sources": r["n_sources"],
            "methods": methods,
            "ground_truth": truth,
            "has_expert_labels": bool(truth),
        })
    return out[:limit]


def firing_rate_by_regime(detector_run=None, regime_run=None, shots=None):
    """How often a detector fires inside each hand-labelled regime, per second.

    The population-scale version of the "n in quiescent" count that
    plot_comparison() shows for one shot. A detector that works should fire
    often in ELMy H and rarely in the quiescent regimes, and the ratio is the
    single most useful summary of whether it discriminates.

    Two things here are easy to get wrong by hand, so they are done here once:

    * Regime windows OVERLAP -- narrow ELMy H intervals are nested inside broad
      quiescent spans. Both the event counts and the per-regime durations must
      assign each event and each instant to exactly ONE regime, the narrowest
      covering it. Counting an event once per containing window inflates every
      class; summing raw window lengths double-counts the overlapped time.
    * Rates need exclusive duration as the denominator, not window count.

    Returns per-regime rows plus an `elmy_vs_quiescent` summary. Quiescent
    classes come from the regime run's own declaration, not a fixed list.
    """
    regime_run = regime_run or next(
        (r["run_id"] for r in runs() if _run_kind(r) == KIND_REGIME), None)
    if regime_run is None:
        raise LookupError("this index holds no regime-labelled run")
    detector_run = detector_run or _default_run("burst")
    meta = {r["run_id"]: r for r in runs()}
    quiescent = set(_run_meta(meta[regime_run])["quiescent_classes"])

    wins, evs = {}, {}
    for r in query_elm_index(
            "SELECT shot, start_time, end_time, label FROM elm_labels WHERE run_id = ?",
            (regime_run,)):
        wins.setdefault(r["shot"], []).append(
            {"start_ms": r["start_time"], "end_ms": r["end_time"], "regime": r["label"]})
    for r in query_elm_index(
            """SELECT shot, start_time, end_time FROM elm_labels
               WHERE run_id = ? AND shot IN (SELECT shot FROM elm_run_shots WHERE run_id = ?)""",
            (detector_run, regime_run)):
        evs.setdefault(r["shot"], []).append((r["start_time"] + r["end_time"]) / 2.0)

    use = sorted(set(wins) & set(evs)) if shots is None else sorted(set(shots) & set(wins))
    secs, cnt, shot_n = {}, {}, {}
    for shot in use:
        ws = wins[shot]
        edges = sorted({x for w in ws for x in (w["start_ms"], w["end_ms"])})
        for a, b in zip(edges, edges[1:]):
            w = _regime_at(ws, (a + b) / 2.0)
            if w:
                secs[w["regime"]] = secs.get(w["regime"], 0.0) + (b - a) / 1000.0
                shot_n.setdefault(w["regime"], set()).add(shot)
        for t in evs.get(shot, []):
            w = _regime_at(ws, t)
            if w:
                cnt[w["regime"]] = cnt.get(w["regime"], 0) + 1

    rows = []
    for reg in sorted(secs, key=lambda k: -secs[k]):
        s = secs[reg]
        rows.append({"regime": reg, "is_quiescent": reg in quiescent,
                     "shots": len(shot_n.get(reg, ())),
                     "exclusive_seconds": round(s, 1),
                     "events": cnt.get(reg, 0),
                     "events_per_second": round(cnt.get(reg, 0) / s, 2) if s else None})
    qs = sum(secs.get(k, 0.0) for k in secs if k in quiescent)
    qc = sum(cnt.get(k, 0) for k in cnt if k in quiescent)
    es = sum(secs.get(k, 0.0) for k in secs if k not in quiescent)
    ec = sum(cnt.get(k, 0) for k in cnt if k not in quiescent)
    return {
        "detector": meta[detector_run]["method"], "detector_run": detector_run,
        "regime_source": meta[regime_run]["method"], "regime_run": regime_run,
        "shots_compared": len(use),
        "by_regime": rows,
        "elmy_vs_quiescent": {
            "elmy_events_per_second": round(ec / es, 2) if es else None,
            "quiescent_events_per_second": round(qc / qs, 2) if qs else None,
            "ratio": round((ec / es) / (qc / qs), 1) if es and qs and qc else None,
        },
        "caveat": ("Rates use each regime's EXCLUSIVE duration; overlapping "
                   "windows are resolved to the narrowest. A non-zero quiescent "
                   "rate is not automatically wrong -- quiescent phases can "
                   "contain real ELMs."),
    }


def events_by_regime(shot, detector_run=None, regime_run=None):
    """One shot: how many of a detector's events fall in each labelled regime.

    The per-shot counterpart of firing_rate_by_regime(), and the same numbers
    plot_comparison() prints in its row labels -- so a figure and the text
    beside it cannot disagree.

    An event is assigned to the regime containing its MIDPOINT. Events straddle
    regime boundaries, so the choice matters and has to be made once: on shot
    163518 counting by start time gives 46 events in quiescent regimes and by
    midpoint 44. Neither is wrong, but two numbers for one quantity in one
    answer is.
    """
    regime_run = regime_run or next(
        (r["run_id"] for r in runs() if _run_kind(r) == KIND_REGIME), None)
    if regime_run is None:
        raise LookupError("this index holds no regime-labelled run")
    detector_run = detector_run or _default_run("burst")
    meta = {r["run_id"]: r for r in runs()}
    quiescent = set(_run_meta(meta[regime_run])["quiescent_classes"])

    wins = regime_windows(shot, regime_run)
    ev = query_elm_index(
        "SELECT start_time, end_time FROM elm_labels WHERE run_id = ? AND shot = ?",
        (detector_run, shot))

    counts, unlabelled = {}, 0
    for r in ev:
        w = _regime_at(wins, (r["start_time"] + r["end_time"]) / 2.0)
        if w:
            counts[w["regime"]] = counts.get(w["regime"], 0) + 1
        else:
            unlabelled += 1
    return {
        "shot": shot,
        "detector": _run_meta(meta[detector_run])["display_name"],
        "regime_source": _run_meta(meta[regime_run])["display_name"],
        "n_events": len(ev),
        "by_regime": dict(sorted(counts.items(), key=lambda kv: -kv[1])),
        "n_quiescent": sum(v for k, v in counts.items() if k in quiescent),
        "n_elmy": sum(v for k, v in counts.items() if k not in quiescent),
        "n_outside_any_labelled_regime": unlabelled,
        "assignment": "each event assigned by its midpoint",
    }


def regime_summary(shot, regime_run=None, discharge_ms=6000.0):
    """Time spent in each hand-labelled regime on one shot, overlaps resolved.

    The windows OVERLAP -- narrow ELMy intervals are nested inside broad
    quiescent spans -- so adding their raw durations double-counts the nested
    time. On shot 163518 the raw quiescent sum is 3830 ms against an exclusive
    3516 ms: a 314 ms error, and one that reads as plausible.

    Every instant is assigned to exactly one regime (the narrowest window
    covering it), so the returned durations sum to the labelled time and the
    remainder is genuinely unlabelled.

    `unlabelled_ms` asserts nothing about the plasma. It is NOT L-mode: the
    source's `MODE_INFO` line "L, LMODE background (not labeled)" means L-mode
    was never marked, not that unmarked time is L-mode. Ramp-up, ramp-down and
    any state the labeller skipped all land here.
    """
    wins = regime_windows(shot, regime_run)
    meta = {r["run_id"]: r for r in runs()}
    rid = regime_run or next(r for r in runs() if _run_kind(r) == KIND_REGIME)["run_id"]
    quiescent = set(_run_meta(meta[rid])["quiescent_classes"])

    edges = sorted({e for w in wins for e in (w["start_ms"], w["end_ms"])})
    exclusive = {}
    for a, b in zip(edges, edges[1:]):
        w = _regime_at(wins, (a + b) / 2.0)
        if w:
            exclusive[w["regime"]] = exclusive.get(w["regime"], 0.0) + (b - a)

    labelled = sum(exclusive.values())
    quiet = sum(v for k, v in exclusive.items() if k in quiescent)
    elmy = labelled - quiet
    span = max(discharge_ms, max(edges) if edges else 0.0)
    return {
        "shot": shot,
        "by_regime_ms": {k: round(v, 1) for k, v in
                         sorted(exclusive.items(), key=lambda kv: -kv[1])},
        "elmy_ms": round(elmy, 1),
        "quiescent_ms": round(quiet, 1),
        "labelled_ms": round(labelled, 1),
        "unlabelled_ms": round(span - labelled, 1),
        "elmy_percent_of_labelled": round(100 * elmy / labelled, 1) if labelled else None,
        "elmy_percent_of_discharge": round(100 * elmy / span, 1) if span else None,
        "overlaps_resolved": "each instant assigned to the narrowest covering window",
        "unlabelled_note": ("asserts nothing -- NOT L-mode; the labeller simply "
                            "marked no regime for this time"),
    }


def elm_phase_at(shot, times, run_id=None):
    """Where each of `times` falls in the ELM cycle, from stored event times.

    This is the primitive that makes a slow diagnostic usable. Thomson
    scattering, CER, ECE and bolometry all sample far slower than ELMs recur, so
    every measurement lands at an arbitrary point in the cycle; averaging them
    together smears out exactly the structure being studied. Phase lets you keep
    only the samples in the part of the cycle you care about.

    Phase follows OMFIT's convention, so results are comparable with the
    facility's own tooling:

        0.0            an ELM has just ended
        0 -> 1         the inter-ELM period, rising to 1 just before the next ELM
        -1 -> 0        during an ELM
        None           undefined -- before the first event or after the last

    `times` is a scalar or any sequence, in **milliseconds**. Nothing here knows
    which diagnostic produced them.

    Choose `run_id` deliberately. The default burst run covers the whole index,
    which is what makes an analysis general; a hand-labelled run covers few
    shots and only the window a person examined, so keying an analysis on it
    restricts that analysis to those shots. Use ground truth to CHECK the event
    times, then use the detector run to do the work -- see the `d3d-elm-phase-analysis`
    skill.
    """
    import numpy as np

    run_id = run_id or _default_run("burst")
    meta = {r["run_id"]: r for r in runs()}
    if _run_kind(meta[run_id]) != KIND_ELM_EVENTS:
        raise ValueError(
            f"run {run_id} holds {_run_kind(meta[run_id])}, not ELM events. "
            f"Phase is defined relative to individual events; a regime window "
            f"is not an event.")

    rows = query_elm_index(
        "SELECT start_time, end_time FROM elm_labels WHERE run_id = ? AND shot = ? "
        "ORDER BY start_time", (run_id, shot))
    if not rows:
        raise ShotNotIndexed(
            f"shot {shot} has no ELM events in run {run_id}, so phase is undefined. "
            f"Check shot_status({shot}) -- the shot may be unanalysed, or analysed "
            f"and genuinely quiet.")

    s = np.array([r["start_time"] for r in rows], float)
    e = np.array([r["end_time"] for r in rows], float)
    t = np.atleast_1d(np.asarray(times, float))

    i = np.searchsorted(s, t, side="right") - 1        # last event starting at/before t
    have_prev = i >= 0
    have_next = (i + 1) < len(s)
    ic = np.clip(i, 0, len(s) - 1)

    prev_start, prev_end = s[ic], e[ic]
    next_start = np.where(have_next, s[np.clip(i + 1, 0, len(s) - 1)], np.nan)
    in_elm = have_prev & (t <= prev_end)

    with np.errstate(invalid="ignore", divide="ignore"):
        inter = next_start - prev_end                  # inter-ELM span
        during = prev_end - prev_start                 # the ELM itself
        ph = np.where(~in_elm & (inter > 0), (t - prev_end) / inter, np.nan)
        ph = np.where(in_elm & (during > 0), (t - prev_end) / during, ph)
        # A zero-length event still has a defined boundary: call it phase 0.
        ph = np.where(in_elm & ~(during > 0), 0.0, ph)
        since = np.where(have_prev, t - prev_end, np.nan)
        until = np.where(have_next, next_start - t, np.nan)

    covered = have_prev & (have_next | in_elm)
    ph = np.where(covered, ph, np.nan)

    def clean(a):
        return [None if not np.isfinite(v) else round(float(v), 4) for v in a]

    return {
        "shot": shot,
        "run_id": run_id,
        "method": _run_meta(meta[run_id])["display_name"],
        "n_times": int(t.size),
        "phase": clean(ph),
        "in_elm": [bool(v) for v in in_elm],
        "ms_since_last_elm": clean(since),
        "ms_until_next_elm": clean(until),
        "covered": [bool(v) for v in covered],
        "n_in_elm": int(in_elm.sum()),
        "n_covered": int(covered.sum()),
        "n_events_used": len(rows),
        "convention": ("0 just after an ELM, rising to 1 just before the next; "
                       "-1 to 0 during an ELM; None outside the event span"),
    }


def select_by_elm_phase(shot, times, phase_range=(0.5, 1.0), run_id=None,
                        min_ms_since_elm=None):
    """Indices of `times` whose ELM phase falls inside `phase_range`.

    The filtering step, kept here so it is not reinvented per analysis. Returns
    the surviving indices plus how many were dropped and why, because "how much
    data did this throw away" is part of the result.

    `phase_range` is a CHOICE, not a default to be trusted: (0.5, 1.0) keeps the
    later half of the inter-ELM period, a common stand-in for a recovered
    pedestal. State the range used in any answer, and show the unfiltered case
    alongside so the effect of the choice is visible.

    `min_ms_since_elm` additionally rejects samples too soon after an event,
    which matters when two closely-spaced events produce a very short inter-ELM
    period whose phase still sweeps 0 to 1.
    """
    ph = elm_phase_at(shot, times, run_id)
    lo, hi = phase_range
    keep, dropped = [], {"in_elm": 0, "outside_phase": 0, "not_covered": 0,
                         "too_soon_after_elm": 0}
    for n, (p, in_elm, cov, since) in enumerate(zip(
            ph["phase"], ph["in_elm"], ph["covered"], ph["ms_since_last_elm"])):
        if not cov or p is None:
            dropped["not_covered"] += 1
        elif in_elm:
            dropped["in_elm"] += 1
        elif not (lo <= p <= hi):
            dropped["outside_phase"] += 1
        elif min_ms_since_elm is not None and (since is None or since < min_ms_since_elm):
            dropped["too_soon_after_elm"] += 1
        else:
            keep.append(n)
    return {
        "shot": shot, "run_id": ph["run_id"], "method": ph["method"],
        "phase_range": [lo, hi], "min_ms_since_elm": min_ms_since_elm,
        "n_times": ph["n_times"], "n_kept": len(keep), "keep_indices": keep,
        "n_dropped": dropped,
        "fraction_kept": round(len(keep) / ph["n_times"], 4) if ph["n_times"] else None,
        "caveat": ("phase_range is a scientific choice; report it, and show the "
                   "unfiltered result alongside"),
    }

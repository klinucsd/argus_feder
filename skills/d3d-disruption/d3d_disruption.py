"""Query the DIII-D disruption index (disruption-py output, stored as sqlite).

Standard library only -- sqlite3 is stdlib, so this runs unchanged in the
argus-feder image, on Colab, and on a laptop. The database is NOT shipped
inside the image; it is located at runtime, same pattern and same folders as
the ELM index.

BACKEND SEAM
------------
Every public function goes through _query(). Today that is a local sqlite
file. When the FEDER lakehouse exists (Iceberg-based, per the co-PI's team)
the intended change is to _query() ALONE -- the function signatures, return
shapes and error types above it stay fixed, so notebooks and stored answers
survive the migration. Do not add SQL to a public function; add it behind
_query().

WHY THE GUARDRAILS ARE CODE
---------------------------
Three columns in this dataset return plausible, wrong numbers rather than
failing (see UNUSABLE in build_disruption_db.py). Prose warnings in a SKILL.md
were tried repeatedly on other skills and did not hold -- the agent reads the
document only when the request looks like the document's topic. So the
constraint lives here, where it cannot be skipped: fetch_samples() raises on
an unusable column instead of returning it.
"""
import os
import sqlite3

_FOLDERS = [
    "~/work/_User-Persistent-Storage_CephBlock_/feder",
    "~/feder_data",
    "~",
    "/content",
]
_FILENAMES = ["disruption.sqlite", "disruption_index.sqlite"]


class ShotNotInIndex(LookupError):
    """Raised when a shot is not present in this slice of the index.

    Deliberately an exception rather than an empty result or a False. "No
    rows for shot X" must never be readable as "shot X did not disrupt" --
    they are different statements and only one of them is supported by an
    index that covers a subset of the archive.
    """


class UnusableParameter(ValueError):
    """Raised when a column known to carry wrong values is requested.

    The value exists and looks reasonable; that is exactly why this raises
    rather than warns. See parameters.caveat for the specific defect.
    """


class PopulationClaimUnsupported(ValueError):
    """Raised when a question needs a representative sample and this is not one.

    The example slice is 20 shots hand-balanced 10 disrupted / 10 not. Rates,
    fractions and frequencies computed from it describe the slice and nothing
    else. Refusing is the correct answer, not a limitation to work around.
    """


def locate_disruption_db():
    """Return the path to the disruption sqlite file, or None if not found."""
    candidates = []
    env_path = os.environ.get("DISRUPTION_DB_PATH")
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
    path = locate_disruption_db()
    if not path:
        searched = ", ".join(
            os.path.expanduser(f"{folder}/{{{'|'.join(_FILENAMES)}}}")
            for folder in _FOLDERS
        )
        raise FileNotFoundError(
            f"Disruption index not found. Searched $DISRUPTION_DB_PATH, then "
            f"{searched}.\nFix: place your copy (either name, "
            f"{' or '.join(_FILENAMES)}) in any of those folders -- on Colab, "
            f"upload it via the file browser into /content."
        )
    # mode=ro so a shared copy cannot be modified by an analysis run; the file
    # is finalized to journal_mode=DELETE at build time so this works without
    # -wal/-shm sidecars present.
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _query(sql, params=()):
    """The backend seam. Returns a list of dicts.

    Replace the body of this function to move to a served backend; leave every
    caller untouched.
    """
    con = _connect()
    try:
        return [dict(r) for r in con.execute(sql, params)]
    finally:
        con.close()


# --------------------------------------------------------------------------
# provenance and coverage
# --------------------------------------------------------------------------

def index_info():
    """What this index contains and which code produced it.

    Always call this before quoting a count -- it states the slice size, which
    is what any 'how many' answer is actually about.
    """
    run = _query("SELECT * FROM ingest_runs ORDER BY run_id LIMIT 1")
    shots = _query(
        "SELECT COUNT(*) AS n_shots, SUM(disrupted) AS n_disrupted,"
        " MIN(shot) AS shot_min, MAX(shot) AS shot_max FROM shots"
    )[0]
    rows = _query("SELECT COUNT(*) AS n FROM disruption_samples")[0]["n"]
    info = dict(run[0]) if run else {}
    info.update(shots)
    info["n_sample_rows"] = rows
    info["is_representative_sample"] = False
    info["coverage_note"] = (
        f"{shots['n_shots']} shots, {shots['n_disrupted']} disrupted. This is a "
        "constructed slice, not a random sample of DIII-D. Rates and fractions "
        "computed from it describe the slice only."
    )
    return info


def parameters(method=None, usable_only=False):
    """The parameter dictionary: units, meaning, producing physics method.

    This is the semantic layer the source files do not carry -- the NetCDF and
    CSV have no units, long names or descriptions on any variable.

    units convention: an explicit unit string; '1' for a dimensionless
    quantity; NULL only when the unit is genuinely unknown.
    """
    sql = "SELECT * FROM parameters"
    clauses, args = [], []
    if method:
        clauses.append("method = ?")
        args.append(method)
    if usable_only:
        clauses.append("usable = 1")
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    return _query(sql + " ORDER BY method, name", tuple(args))


def parameter_info(name):
    """Units, meaning and caveats for one parameter. Raises if unknown."""
    rows = _query("SELECT * FROM parameters WHERE name = ?", (name,))
    if not rows:
        known = [r["name"] for r in _query("SELECT name FROM parameters ORDER BY name")]
        raise KeyError(f"no parameter named {name!r}. Known: {', '.join(known)}")
    return rows[0]


def unusable_parameters():
    """Parameters that return plausible but wrong values, with the reason."""
    return _query(
        "SELECT name, long_name, caveat FROM parameters WHERE usable = 0 ORDER BY name"
    )


# --------------------------------------------------------------------------
# shots
# --------------------------------------------------------------------------

def shots(disrupted=None, shot_min=None, shot_max=None):
    """Shots in the index, optionally filtered. One row per shot."""
    sql = "SELECT * FROM shots"
    clauses, args = [], []
    if disrupted is not None:
        clauses.append("disrupted = ?")
        args.append(1 if disrupted else 0)
    if shot_min is not None:
        clauses.append("shot >= ?")
        args.append(shot_min)
    if shot_max is not None:
        clauses.append("shot <= ?")
        args.append(shot_max)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    return _query(sql + " ORDER BY shot", tuple(args))


def is_indexed(shot):
    return bool(_query("SELECT 1 FROM shots WHERE shot = ?", (shot,)))


def shot_summary(shot):
    """Disruption status and timing for one shot.

    Raises ShotNotInIndex rather than returning a 'not disrupted' answer for a
    shot nobody analysed -- those are different statements.
    """
    rows = _query("SELECT * FROM shots WHERE shot = ?", (shot,))
    if not rows:
        raise ShotNotInIndex(
            f"shot {shot} is not in this index. It has not been run through "
            f"disruption-py here -- which is NOT evidence that it did not "
            f"disrupt. Use shots() to see what is covered."
        )
    r = rows[0]
    r["label_source"] = (
        "time_until_disrupt, from the human-curated d3drdb disruptions table"
    )
    return r


# --------------------------------------------------------------------------
# samples
# --------------------------------------------------------------------------

def fetch_samples(shot, columns=None, t_start=None, t_end=None,
                  time_until_disrupt_max=None, allow_unusable=False):
    """Time-series rows for ONE shot.

    Always scoped to a single shot: the samples table reaches ~17M rows at full
    archive coverage, so there is deliberately no way to select across all
    shots at once.

    columns: parameter names to return, or None for all usable ones.
    time_until_disrupt_max: keep only rows within this many seconds of the
        disruption (disrupted shots only).
    allow_unusable: required to fetch a column flagged usable=0.
    """
    if not is_indexed(shot):
        raise ShotNotInIndex(f"shot {shot} is not in this index.")

    known = {r["name"]: r for r in _query("SELECT * FROM parameters")}
    if columns is None:
        cols = [n for n, r in known.items() if r["usable"]]
    else:
        cols = list(columns)
        for c in cols:
            if c not in known:
                raise KeyError(f"no parameter named {c!r}")
            if not known[c]["usable"] and not allow_unusable:
                raise UnusableParameter(
                    f"{c!r} is flagged unusable: {known[c]['caveat']}\n"
                    f"It returns plausible numbers, which is why this raises "
                    f"rather than warns. Pass allow_unusable=True only if you "
                    f"intend to demonstrate the defect itself."
                )

    select = ", ".join(['"shot"', '"time"'] + [f'"{c}"' for c in cols])
    sql = f"SELECT {select} FROM disruption_samples WHERE shot = ?"
    args = [shot]
    if t_start is not None:
        sql += " AND time >= ?"
        args.append(t_start)
    if t_end is not None:
        sql += " AND time <= ?"
        args.append(t_end)
    if time_until_disrupt_max is not None:
        sql += " AND time_until_disrupt IS NOT NULL AND time_until_disrupt <= ?"
        args.append(time_until_disrupt_max)
    return _query(sql + " ORDER BY time", tuple(args))


def disruption_label(shot, derived=False):
    """The disruption label for a shot.

    Returns the AUTHORITATIVE label (time_until_disrupt, from the curated
    d3drdb table) unless derived=True, which returns disruption-py's own
    current_quench_time estimate instead.

    These disagree -- on the 20-shot example slice, 3 shots (198244, 198643,
    199062) are unlabelled in d3drdb but receive a finite current_quench_time.
    Silently mixing them shifts the class balance from 10/20 to 13/20, so the
    choice is explicit rather than a default.
    """
    s = shot_summary(shot)
    if not derived:
        return {"shot": shot, "disrupted": bool(s["disrupted"]),
                "t_disrupt": s["t_disrupt"], "source": "time_until_disrupt (d3drdb, curated)"}
    rows = _query(
        "SELECT current_quench_time FROM disruption_samples"
        " WHERE shot = ? AND current_quench_time IS NOT NULL LIMIT 1", (shot,))
    return {"shot": shot, "disrupted": bool(rows),
            "t_disrupt": rows[0]["current_quench_time"] if rows else None,
            "source": "current_quench_time (disruption-py, derived from Ip decay)",
            "warning": "derived indicator, not the label; disagrees with the "
                       "curated label on some shots"}


def label_disagreements():
    """Shots where the curated label and the derived indicator disagree."""
    return _query(
        "SELECT s.shot, s.disrupted AS curated_disrupted,"
        " (SELECT COUNT(*) FROM disruption_samples d"
        "  WHERE d.shot = s.shot AND d.current_quench_time IS NOT NULL) > 0"
        "   AS derived_disrupted"
        " FROM shots s"
        " WHERE curated_disrupted <> derived_disrupted ORDER BY s.shot"
    )


# --------------------------------------------------------------------------
# population guard
# --------------------------------------------------------------------------

def disruption_rate():
    """Refuses. The index is a constructed slice, not a sample.

    Present as a function so the refusal is returned by the code rather than
    left to the agent to infer -- asking for a disruption rate is a reasonable
    question that this data cannot answer.
    """
    info = index_info()
    raise PopulationClaimUnsupported(
        f"This index holds {info['n_shots']} shots, {info['n_disrupted']} of them "
        f"disrupted -- deliberately balanced, not drawn at random from DIII-D. "
        f"Any rate computed from it ({info['n_disrupted']}/{info['n_shots']}) "
        f"describes the slice and says nothing about how often DIII-D disrupts. "
        f"For an archive-wide rate you need the d3drdb disruptions table over a "
        f"defined shot population, not this file."
    )

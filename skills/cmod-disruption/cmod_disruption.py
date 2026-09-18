"""Alcator C-Mod disruption index, from MIT's disruption-py output.

Why this is a separate module from the DIII-D one
-------------------------------------------------
The two devices publish 63 parameters each and only 32 share a name. C-Mod has
ion-cyclotron and lower-hybrid heating where DIII-D has neutral beams; DIII-D
carries real-time variants C-Mod has no equivalent for. And nothing joins them:
C-Mod has no shot catalogue, no summaries and no ELM labels in this lakehouse,
so a C-Mod shot reaches nothing a DIII-D shot does.

Two parameters are a trap across the devices
--------------------------------------------
`ip_prog` and `dipprog_dt` are in amps here and in MEGAamps in the DIII-D index
of the same name -- a factor of 1e6, on a column with the same name and a
plausible-looking value. `cross_device_note()` returns the list, and
`fetch_samples()` refuses a cross-device comparison on one unless the caller
says which unit they want. A wrong answer here looks entirely reasonable.

The same upstream defect is why three DIII-D columns are refused there and none
is refused here: flat-top detection tests `|ip_prog| >= 100e3`, which never
fires when ip_prog is order 1. On C-Mod it fires, so `time_domain` carries real
discharge phases and `phase_windows()` can answer when flat-top began -- a
question the DIII-D index cannot answer at all.

Every table reference is schema-qualified. The lakehouse resolves a bare name
against `d3d` first, where `shots` is the full plasma catalogue, so an
unqualified `FROM shots` would answer about the wrong thing entirely.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from d3d_lakehouse import LakehouseError  # noqa: E402,F401
from d3d_lakehouse import query as _query_api  # noqa: E402

DEVICE = "CMOD"


class ShotNotInIndex(LookupError):
    """Raised when a shot is not in this index.

    An exception rather than an empty result: "no rows for shot X" must never
    read as "shot X did not disrupt". The index covers the shots MIT published
    disruption times for, not every C-Mod shot on the origin.
    """


class PopulationClaimUnsupported(ValueError):
    """Raised when a question needs a representative sample and this is not one.

    This index holds the shots in MIT's published file. The C-Mod origin holds
    more; only these carry disruption times. How MIT chose them is not recorded
    here, so a rate computed over them describes that selection and not C-Mod.
    """


class CrossDeviceUnitMismatch(ValueError):
    """Raised when a parameter whose units differ from DIII-D's is used unguarded.

    The value is real and the name matches; that is exactly why this raises
    rather than warns.
    """


def _query(sql, params=()):
    return _query_api(sql, params)


# --------------------------------------------------------------------------
# what this index is
# --------------------------------------------------------------------------

def index_info():
    """What this index contains and which code produced it.

    Call this before quoting any count: it states the selection size, which is
    what a 'how many' answer is actually about.
    """
    run = _query("SELECT * FROM disruption.ingest_runs WHERE tokamak = ? LIMIT 1", (DEVICE,))
    shots = _query(
        "SELECT COUNT(*) AS n_shots, SUM(disrupted) AS n_disrupted,"
        " MIN(shot) AS shot_min, MAX(shot) AS shot_max FROM disruption.cmod_shots"
    )[0]
    rows = _query("SELECT COUNT(*) AS n FROM disruption.cmod_samples")[0]["n"]
    info = dict(run[0]) if run else {}
    info.update(shots)
    info["device"] = DEVICE
    info["n_sample_rows"] = rows
    info["is_representative_sample"] = False
    info["coverage_note"] = (
        f"{shots['n_shots']} shots, {shots['n_disrupted']} with a disruption time. "
        "These are the shots the provider published times for, not every C-Mod "
        "shot. Rates computed over them describe that selection only."
    )
    return info


def parameters(usable_only=False):
    """Every parameter, with its meaning, units and IMAS path where one exists."""
    sql = "SELECT * FROM disruption.cmod_parameters"
    if usable_only:
        sql += " WHERE usable <> 0"
    return _query(sql + " ORDER BY name")


def parameter_info(name):
    """One parameter's meaning, units, IMAS path and any caveat."""
    rows = _query("SELECT * FROM disruption.cmod_parameters WHERE name = ?", (name,))
    if not rows:
        raise LookupError(
            f"no parameter named {name!r} in the C-Mod index; call parameters() "
            f"for the list. Note the DIII-D index uses different names for some "
            f"of the same quantities.")
    return rows[0]


def d3d_equivalent(name=None):
    """The DIII-D parameter this one corresponds to, where one exists.

    Three kinds of answer, and `mapping_source` says which:
      * the same name on both devices
      * a different name for the same quantity, checked against both descriptions
      * a different name confirmed by the package's own maintainers

    A NULL equivalent means the quantity is specific to this device, usually
    because the machines differ in hardware. That is an answer, not a gap.

    Units still are not guaranteed to match even where the quantity does --
    see `cross_device_note()`.
    """
    sql = ("SELECT name, d3d_equivalent, mapping_source, units, long_name"
           " FROM disruption.cmod_parameters")
    if name is not None:
        rows = _query(sql + " WHERE name = ?", (name,))
        if not rows:
            raise LookupError(f"no parameter named {name!r} in the C-Mod index")
        return rows[0]
    return _query(sql + " ORDER BY name")


def cross_device_note():
    """Parameters whose units differ from the DIII-D index of the same name.

    Read this before putting a C-Mod number and a DIII-D number in the same
    sentence, table or ratio.
    """
    return _query(
        "SELECT name, units, caveat FROM disruption.cmod_parameters"
        " WHERE caveat IS NOT NULL ORDER BY name")


def _mismatched():
    return {r["name"] for r in cross_device_note()}


# --------------------------------------------------------------------------
# shots and labels
# --------------------------------------------------------------------------

def shots(disrupted=None):
    """Shots in the index, optionally only those with or without a disruption time."""
    sql = "SELECT * FROM disruption.cmod_shots"
    params = ()
    if disrupted is not None:
        sql += " WHERE disrupted = ?"
        params = (1 if disrupted else 0,)
    return _query(sql + " ORDER BY shot", params)


def is_indexed(shot):
    """Whether this shot is in the index. False means unknown, not 'did not disrupt'."""
    return bool(_query("SELECT 1 FROM disruption.cmod_shots WHERE shot = ?", (shot,)))


def shot_summary(shot):
    """One shot's label, disruption time and sample coverage."""
    rows = _query("SELECT * FROM disruption.cmod_shots WHERE shot = ?", (shot,))
    if not rows:
        raise ShotNotInIndex(
            f"C-Mod shot {shot} is not in this index. That is not a statement "
            f"about whether it disrupted.")
    return rows[0]


def disruption_label(shot):
    """Whether this shot disrupted, and when."""
    s = shot_summary(shot)
    return {"shot": s["shot"], "device": DEVICE,
            "disrupted": bool(s["disrupted"]), "t_disrupt": s["t_disrupt"]}


def disruption_labels(shot_list=None):
    """Labels for a GROUP of shots in one request."""
    if shot_list is None:
        return [{"shot": s["shot"], "device": DEVICE,
                 "disrupted": bool(s["disrupted"]), "t_disrupt": s["t_disrupt"]}
                for s in shots()]
    rows = _query(
        "SELECT * FROM disruption.cmod_shots WHERE shot IN (?) ORDER BY shot",
        (list(shot_list),))
    found = {r["shot"] for r in rows}
    missing = [s for s in shot_list if s not in found]
    out = [{"shot": r["shot"], "device": DEVICE, "disrupted": bool(r["disrupted"]),
            "t_disrupt": r["t_disrupt"]} for r in rows]
    for s in missing:
        out.append({"shot": s, "device": DEVICE, "disrupted": None,
                    "t_disrupt": None, "in_index": False})
    return out


def label_disagreements():
    """Shots where the per-shot label and the per-sample indicator disagree.

    The same audit the DIII-D index supports, over a larger set. A disagreement
    is a finding about the pipeline, not about the shot.
    """
    return _query(
        "SELECT * FROM ("
        "  SELECT s.shot,"
        "         (s.disrupted <> 0) AS labelled_disrupted,"
        "         EXISTS (SELECT 1 FROM disruption.cmod_samples d"
        "                  WHERE d.shot = s.shot"
        "                    AND d.time_until_disrupt IS NOT NULL)"
        "           AS has_time_until_disrupt"
        "  FROM disruption.cmod_shots s"
        ") t"
        " WHERE labelled_disrupted <> has_time_until_disrupt ORDER BY shot")


# --------------------------------------------------------------------------
# samples
# --------------------------------------------------------------------------

def ip_direction(shot_list=None):
    """The sign of the plasma current for each shot: +1 or -1.

    C-Mod ran the current in both directions, so a quantity whose sign follows
    the current is not comparable across shots until it is multiplied by this.
    Loop voltage is the usual case.
    """
    sql = ("SELECT shot, CASE WHEN AVG(ip) < 0 THEN -1 ELSE 1 END AS ip_sign,"
           " AVG(ip) AS mean_ip FROM disruption.cmod_samples"
           " WHERE ip IS NOT NULL")
    params = ()
    if shot_list is not None:
        sql += " AND shot IN (?)"
        params = (list(shot_list),)
    return _query(sql + " GROUP BY shot ORDER BY shot", params)


def fetch_samples(shot, columns=None, cross_device=False, sign_by_ip=()):
    """Time series for one shot.

    `columns` defaults to every parameter. Requesting a parameter whose units
    differ from the DIII-D index raises unless `cross_device=True`, which is the
    caller stating they know the units differ.

    `sign_by_ip` names columns to multiply by this shot's current direction, so
    shots run in opposite directions become comparable. Do this here rather than
    by hand: getting the multiplication the wrong way round mirrors the result
    and inverts the conclusion, while leaving every magnitude looking correct.
    A signed column comes back as `<name>_signed` alongside the raw one.
    """
    if not is_indexed(shot):
        raise ShotNotInIndex(
            f"C-Mod shot {shot} is not in this index. That is not a statement "
            f"about whether it disrupted.")
    sign_by_ip = tuple(sign_by_ip or ())
    if columns is None:
        cols = "*"
    else:
        bad = _mismatched() & set(columns)
        if bad and not cross_device:
            note = {r["name"]: r["caveat"] for r in cross_device_note()}
            raise CrossDeviceUnitMismatch(
                "; ".join(f"{b}: {note[b]}" for b in sorted(bad))
                + ". Pass cross_device=True once you have accounted for it.")
        cols = ", ".join(['"shot"', '"time"'] + ['"%s"' % c for c in columns])
    if sign_by_ip:
        missing = [c for c in sign_by_ip if columns is not None and c not in columns]
        if missing:
            raise ValueError(
                "sign_by_ip names %s, which is not in columns" % ", ".join(missing))
        signed = ", ".join(
            '"%s" * (CASE WHEN x.mean_ip < 0 THEN -1 ELSE 1 END) AS "%s_signed"' % (c, c)
            for c in sign_by_ip)
        return _query(
            "SELECT %s, %s FROM disruption.cmod_samples d,"
            " (SELECT AVG(ip) AS mean_ip FROM disruption.cmod_samples WHERE shot = ?) x"
            " WHERE d.shot = ? ORDER BY d.\"time\"" % (cols.replace('"shot"', 'd."shot"')
                                                       .replace('"time"', 'd."time"'), signed),
            (shot, shot))
    return _query(
        "SELECT %s FROM disruption.cmod_samples WHERE shot = ? ORDER BY \"time\"" % cols,
        (shot,))


def window_before_disruption(shots, ms, columns=("v_loop",), sign_by_ip=()):
    """Samples within `ms` milliseconds of the current quench, windowed in SQL.

    Use this rather than pulling the whole shot and slicing it yourself. The
    comparison against the window edge happens in the database, on the stored
    values, so nothing depends on how a float survives being written to a file
    and read back.

    That matters more than it sounds. The sample at the edge of a 2 ms window is
    stored as 0.00199997..., which is inside the window. Rounded to six decimals
    on its way through a CSV it becomes exactly 0.002, which is outside. A
    quarter of that window's samples disappear, every remaining number stays
    self-consistent, and the statistic shifts by a factor of two.

    Returns one row per sample with `shot`, `time`, `time_until_disrupt` and the
    requested columns, plus `<name>_signed` for anything in `sign_by_ip`.
    """
    shots = list(shots)
    cols = ['d."shot"', 'd."time"', 'd.time_until_disrupt'] + ['d."%s"' % c for c in columns]
    for c in sign_by_ip:
        if c not in columns:
            raise ValueError("sign_by_ip names %s, which is not in columns" % c)
        cols.append('d."%s" * (CASE WHEN x.mean_ip < 0 THEN -1 ELSE 1 END) AS "%s_signed"' % (c, c))
    return _query(
        "SELECT %s FROM disruption.cmod_samples d"
        " JOIN (SELECT shot, AVG(ip) AS mean_ip FROM disruption.cmod_samples"
        "        GROUP BY shot) x ON x.shot = d.shot"
        " WHERE d.shot IN (?) AND d.time_until_disrupt >= 0"
        "   AND d.time_until_disrupt <= ?"
        " ORDER BY d.shot, d.time_until_disrupt" % ", ".join(cols),
        (shots, ms / 1000.0))


# --------------------------------------------------------------------------
# discharge phase -- the capability the DIII-D index does not have
# --------------------------------------------------------------------------

PHASE = {1: "ramp-up", 2: "flat-top", 3: "ramp-down"}


def phase_windows(shot):
    """When each discharge phase began and ended, for one shot.

    `time_domain` carries real phases here, so 'which phase was the shot in when
    it disrupted' and 'when did flat-top begin' are answerable. The DIII-D index
    of the same design cannot answer either: its `time_domain` is constant.
    """
    rows = _query(
        "SELECT time_domain AS phase, MIN(\"time\") AS t_start, MAX(\"time\") AS t_end,"
        " COUNT(*) AS n FROM disruption.cmod_samples"
        " WHERE shot = ? AND time_domain IS NOT NULL"
        " GROUP BY time_domain ORDER BY time_domain", (shot,))
    if not rows:
        if not is_indexed(shot):
            raise ShotNotInIndex(f"C-Mod shot {shot} is not in this index.")
        return []
    for r in rows:
        r["phase_name"] = PHASE.get(int(r["phase"]), "unknown")
    return rows


def phase_at_disruption(shot):
    """Which discharge phase the shot was in when it disrupted, or None."""
    s = shot_summary(shot)
    if not s["disrupted"] or s["t_disrupt"] is None:
        return None
    rows = _query(
        "SELECT time_domain AS phase FROM disruption.cmod_samples"
        " WHERE shot = ? AND time_domain IS NOT NULL"
        " ORDER BY ABS(\"time\" - ?) LIMIT 1", (shot, s["t_disrupt"]))
    if not rows:
        return None
    p = int(rows[0]["phase"])
    return {"shot": shot, "t_disrupt": s["t_disrupt"],
            "phase": p, "phase_name": PHASE.get(p, "unknown")}


def flattop_entry(shot_list=None):
    """Flat-top entry time per shot, with disruption or censoring time.

    The per-shot pair a hazard model needs. Shots with no flat-top sample come
    back with `t_flattop` None rather than being dropped, because 'never reached
    flat-top' is a result.
    """
    sql = ("SELECT s.shot, s.disrupted, s.t_disrupt, s.t_max AS t_last,"
           " MIN(d.\"time\") AS t_flattop"
           " FROM disruption.cmod_shots s"
           " LEFT JOIN disruption.cmod_samples d"
           "   ON d.shot = s.shot AND d.time_domain = 2")
    params = ()
    if shot_list is not None:
        sql += " WHERE s.shot IN (?)"
        params = (list(shot_list),)
    sql += (" GROUP BY s.shot, s.disrupted, s.t_disrupt, s.t_max ORDER BY s.shot")
    out = _query(sql, params)
    for r in out:
        r["disrupted"] = bool(r["disrupted"])
        r["t_event"] = r["t_disrupt"] if r["disrupted"] else r["t_last"]
        r["censored"] = not r["disrupted"]
    return out


# --------------------------------------------------------------------------
# population guard
# --------------------------------------------------------------------------

def disruption_rate():
    """Refuses. This index is the provider's selection, not a sample of C-Mod."""
    info = index_info()
    raise PopulationClaimUnsupported(
        f"This index holds {info['n_shots']} shots, {info['n_disrupted']} with a "
        f"disruption time. They are the shots the provider published times for, "
        f"and the C-Mod origin holds many more. How they were chosen is not "
        f"recorded here, so {info['n_disrupted']}/{info['n_shots']} describes that "
        f"selection and says nothing about how often C-Mod disrupted. An "
        f"archive-wide rate needs a defined shot population, which this is not.")

"""d3d-relational-db helper: query the DIII-D shot-metadata database (d3drdb).

Served over HTTP by the FEDER lakehouse, not from a local file. There is
nothing to download, nothing to place in a folder, and no copy to go stale --
which is the whole reason for the change: the SQLite extract this skill used to
read had to be shipped to every user, and was already drifting from the source.

The endpoint exposes plasma-type shots only, through views that reproduce the
old extract's semantics exactly, so every query in this file and in SKILL.md
means what it always meant. `SELECT COUNT(*) FROM SHOTS WHERE SHOT BETWEEN
190000 AND 195000` returns 3,507 from either source.

Two differences from the retired extract are worth knowing, both improvements:

  * Text values are no longer space-padded. `WHERE topology = 'SNB'` returned
    ZERO rows against the extract, whose values were stored as `'SNB       '`;
    it now returns 35,727. Any code that worked around this with TRIM() can
    stop.
  * The catalogue is a newer dump: 90,644 plasma shots against the extract's
    90,418. Counts over the whole archive differ slightly from figures
    published before 2026-09.

Tables: SHOTS, SHOTS_TYPE, SUMMARIES (plasma-type shots only) + SIGNAL_NAMES,
SIGNAL_INFO (catalog tables, not shot-specific). The two legacy disruption
tables are NOT here -- disruption labels come from a separate index.

Needs outbound network. Set $FEDER_API_URL to point at a different deployment.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from d3d_lakehouse import LakehouseError  # noqa: E402,F401
from d3d_lakehouse import endpoint as _endpoint, query as _query_api  # noqa: E402


def query_d3drdb(sql, params=()):
    """Run a read-only SQL query against d3drdb. Returns a list of dicts.

    Placeholders may be `?` or `%s`, and LIKE matches case-insensitively, so
    SQL written for the old local file runs unchanged.

    Tables available: SHOTS, SHOTS_TYPE, SUMMARIES, SIGNAL_NAMES, SIGNAL_INFO.
    SHOTS/SHOTS_TYPE/SUMMARIES are pre-filtered to plasma-type shots only.

    A result too large to return raises rather than arriving truncated --
    aggregate in SQL (COUNT, AVG, GROUP BY) instead of counting rows here.
    """
    return _query_api(sql, params)


def plasma_shots_in_range(lo, hi):
    """List of plasma shot numbers in [lo, hi]. Every row in SHOTS is already
    plasma-type (pre-filtered), so this is a plain range query, no join needed."""
    rows = query_d3drdb("SELECT SHOT FROM SHOTS WHERE SHOT BETWEEN ? AND ? ORDER BY SHOT", (lo, hi))
    return [r["SHOT"] for r in rows]


def shot_summary(shot):
    """Physics summary for one shot (kappa, ip, pulse_length, etc.) or None if absent."""
    rows = query_d3drdb("SELECT * FROM SUMMARIES WHERE shot = ?", (shot,))
    return rows[0] if rows else None


def _fmt(value):
    """Format one d3drdb value for an answer, without inventing precision."""
    if value is None:
        return "not populated"
    if isinstance(value, str):
        return value.strip() or "not populated"
    if isinstance(value, float):
        if value != value:                       # NaN
            return "not populated"
        if value and (abs(value) >= 1e6 or abs(value) < 1e-3):
            return f"{value:.6g}"
        return f"{value:g}"
    return str(value)


def report_shot_summary(shot, fields):
    """Return the ANSWER TEXT for a shot-summary question -- quote it verbatim.

    Reads each named field straight from the SUMMARIES row and formats it. The
    caller reports this string; it does not restate the numbers in its own
    words. Values written from memory rather than from the row have been wrong
    by 2.7x on this exact table (see SKILL.md), and a wrong scalar in a fluent
    sentence is not detectable by the reader.

    `fields` is the list of column names the question actually asked for.
    Unknown column names are reported as such rather than silently dropped, so
    a typo in a field name cannot look like a missing measurement.
    """
    row = shot_summary(shot)
    if row is None:
        return f"Shot {shot}: no SUMMARIES row in d3drdb."
    lines = [f"Shot {shot} (values read directly from d3drdb SUMMARIES):"]
    for f in fields:
        if f not in row:
            lines.append(f"  {f}: NOT A COLUMN in SUMMARIES")
        else:
            lines.append(f"  {f}: {_fmt(row[f])}")
    return "\n".join(lines)


def explain_signal(tag):
    r"""Return the ANSWER TEXT for 'what does this tag mean' -- quote it verbatim.

    Resolves the tag through the catalog instead of reading meaning off its
    name. Tag names are not self-describing: FS02UPDA is a RAW filterscope
    channel (PMT22:PHOTON_FLUX) where UP is a viewing location and DA is the
    species, but the name invites reading "UPDA" as "updated". An answer that
    guessed exactly that has already been given.

    Says so plainly when the catalog has no entry -- an undocumented signal is
    not the same as a signal whose meaning can be inferred.

    When the tag names a tree (\EFIT01::BT0VAC), rows from OTHER trees are
    labelled as such. The same name often exists in several trees with the
    description attached to only one of them: BT0VAC is documented under EFIT
    and "Unassigned Signal" under EFIT01, so an answer about EFIT01 that quotes
    the EFIT description presents a sibling row's text as the catalog's word on
    the signal asked about. Usually the same quantity; still an inference, and
    the catalog does not say it.
    """
    raw = str(tag).strip()
    want_tree = raw.split("::")[0].lstrip("\\").strip().upper() if "::" in raw else None
    name = raw.lstrip("\\").split("::")[-1].strip()

    rows = search_signal_catalog(name, limit=10)
    exact = [r for r in rows
             if (r["Name"] or "").lstrip("\\").split("::")[-1].upper() == name.upper()]
    hits = exact or rows
    if not hits:
        return (f"{tag}: no entry in the d3drdb signal catalog. The catalog documents "
                f"only a minority of signals, so this does not mean the signal is absent "
                f"from MDSplus -- but its meaning is NOT established. Do not infer it "
                f"from the tag name.")

    def documented(r):
        d = (r["Description"] or "").strip()
        return bool(d) and "unassigned" not in d.lower()

    def block(r, indent):
        pad = " " * indent
        return [f"{pad}Tree        : {r['Tree']}",
                f"{pad}Full_Path   : {r['Full_Path']}",
                f"{pad}Description : {(r['Description'] or '').strip() if documented(r) else 'NOT DOCUMENTED for this tree'}",
                f"{pad}Units       : {r['Units'] if documented(r) else 'not documented'}"]

    lines = [f"{tag} -- from the d3drdb signal catalog:"]
    if want_tree:
        mine = [r for r in hits if (r["Tree"] or "").upper() == want_tree]
        others = [r for r in hits if (r["Tree"] or "").upper() != want_tree]
        if mine:
            lines.append(f"  REQUESTED TREE ({want_tree}):")
            lines += block(mine[0], 4)
        else:
            lines.append(f"  REQUESTED TREE ({want_tree}): no catalog row for this name in this tree.")
        if others:
            lines.append("  SAME NAME IN OTHER TREES -- a different signal record, not the one asked about:")
            for r in others[:3]:
                lines += block(r, 4)
                lines.append("")
        if mine and not documented(mine[0]) and any(documented(r) for r in others):
            src = next(r for r in others if documented(r))
            lines.append(f"  The {want_tree} row carries no description. If you offer the "
                         f"{src['Tree']} description as the likely meaning, say that it comes "
                         f"from a DIFFERENT tree and is unconfirmed for {want_tree}.")
    else:
        for r in hits[:3]:
            lines += block(r, 2)
            lines.append("")
        if len({(r["Tree"] or "") for r in hits}) > 1:
            lines.append("  This name exists in several trees. Say which tree the answer is "
                         "about; do not merge their descriptions.")
    if not exact:
        lines.append("  (no exact name match -- these are keyword matches, state that)")
    return "\n".join(l for l in lines if l != "" or True).rstrip()


def search_signal_catalog(keyword, limit=50):
    """Search SIGNAL_NAMES/SIGNAL_INFO for a keyword in the signal name or description.

    Joined on Group_Id. Most signals have Group_Id=0 ('unassigned', no SIGNAL_INFO
    row) -- only a minority are documented. A miss here doesn't mean the signal
    doesn't exist in MDSplus, only that d3drdb has no catalog entry for it.
    """
    return query_d3drdb(
        """
        SELECT n.Name, n.Tree, n.Full_Path, i.Description, i.Units
        FROM SIGNAL_NAMES n
        LEFT JOIN SIGNAL_INFO i ON n.Group_Id = i.Group_Id
        WHERE n.Name LIKE ? OR i.Description LIKE ?
        LIMIT ?
        """,
        (f"%{keyword}%", f"%{keyword}%", limit),
    )

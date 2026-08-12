"""d3d-relational-db helper: query the trimmed, demo-focused d3drdb subset.

Local SQLite file -- no network, no fdp wrapper needed. Read-only: this is
reference data supplied by GA, never written to.

The file is looked up in each of these folders, in order, under EITHER
filename (`d3drdb.sqlite` or `d3drdb_demo.sqlite`) -- verified 2026-08-02:
different real deployments have used different filenames in different
folders (JupyterHub/NRP: `d3drdb.sqlite`; this dev machine:
`d3drdb_demo.sqlite`), and checking only one filename per folder caused a
real "file not found" that cost a rename to work around. Checking both
everywhere removes that trap entirely:
  1. $D3DRDB_PATH (explicit override -- exact file, not a folder)
  2. ~/work/_User-Persistent-Storage_CephBlock_/feder/  (NRP persistent -- primary)
  3. ~/feder_data/                                      (local dev)
  4. ~                                                   (simple fallback)
  5. /content/                                           (Colab -- upload via the file browser)

On Colab, deliberately upload-only, NOT Google Drive: a Drive mount asks for
a broad OAuth consent grant (real Colab UX, tried 2026-08-02: it also just
failed there with "credential propagation was unsuccessful", a known
flakiness point) -- too high-friction/alarming a first impression for a
domain scientist. Plain upload to `/content/` via the Colab file browser
needs zero code and is immediately found here. Tradeoff accepted: `/content/`
does not survive a session restart, so this needs re-uploading each fresh
Colab session -- deliberately chosen over Drive's persistence for the
simpler, less scary flow.

Contents: SHOTS, SHOTS_TYPE, SUMMARIES (already filtered to plasma-type shots
only) + SIGNAL_NAMES, SIGNAL_INFO (catalog tables, not shot-specific). The two
legacy disruption tables (DISRUPTIONS, disruption_warning) are NOT present --
disruption labels come from a separate labels store, not from here.
"""
import os
import sqlite3

_FOLDERS = [
    "~/work/_User-Persistent-Storage_CephBlock_/feder",
    "~/feder_data",
    "~",
    "/content",
]
_FILENAMES = ["d3drdb.sqlite", "d3drdb_demo.sqlite"]


def locate_d3drdb():
    """Return the path to the d3drdb sqlite file, or None if not found anywhere."""
    candidates = []
    env_path = os.environ.get("D3DRDB_PATH")
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
    path = locate_d3drdb()
    if not path:
        searched = ", ".join(
            os.path.expanduser(f"{folder}/{{{'|'.join(_FILENAMES)}}}") for folder in _FOLDERS
        )
        raise FileNotFoundError(
            f"d3drdb file not found. Searched $D3DRDB_PATH, then {searched}.\n"
            "Fix: place your copy of the file (either name, "
            f"{' or '.join(_FILENAMES)}) in any of those folders -- on "
            "Colab, upload it via the file browser (folder icon, left "
            "sidebar); it lands at /content/ automatically, no code needed. "
            "Note this must be re-uploaded each fresh Colab session."
        )
    # Read-only: this is GA's reference data, never write to it.
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def query_d3drdb(sql, params=()):
    """Run a read-only SQL query against d3drdb. Returns a list of dicts.

    Tables available: SHOTS, SHOTS_TYPE, SUMMARIES, SIGNAL_NAMES, SIGNAL_INFO.
    SHOTS/SHOTS_TYPE/SUMMARIES are pre-filtered to plasma-type shots only.
    """
    con = _connect()
    try:
        con.row_factory = sqlite3.Row
        rows = con.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


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
        if f not in row.keys():
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

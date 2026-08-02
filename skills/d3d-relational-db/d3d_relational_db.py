"""d3d-relational-db helper: query the trimmed, demo-focused d3drdb subset.

Local SQLite file -- no network, no fdp wrapper needed. Read-only: this is
reference data supplied by GA, never written to.

The file is looked up in this order:
  1. $D3DRDB_PATH (explicit override)
  2. ~/work/_User-Persistent-Storage_CephBlock_/feder/d3drdb.sqlite  (NRP persistent -- primary)
  3. ~/feder_data/d3drdb_demo.sqlite                                (local dev)
  4. ~/d3drdb_demo.sqlite                                           (simple fallback)

Contents: SHOTS, SHOTS_TYPE, SUMMARIES (already filtered to plasma-type shots
only) + SIGNAL_NAMES, SIGNAL_INFO (catalog tables, not shot-specific). The two
legacy disruption tables (DISRUPTIONS, disruption_warning) are NOT present --
disruption labels come from a separate labels store, not from here.
"""
import os
import sqlite3


def locate_d3drdb():
    """Return the path to the d3drdb sqlite file, or None if not found anywhere."""
    candidates = []
    env_path = os.environ.get("D3DRDB_PATH")
    if env_path:
        candidates.append(env_path)
    candidates += [
        os.path.expanduser("~/work/_User-Persistent-Storage_CephBlock_/feder/d3drdb.sqlite"),
        os.path.expanduser("~/feder_data/d3drdb_demo.sqlite"),
        os.path.expanduser("~/d3drdb_demo.sqlite"),
    ]
    for p in candidates:
        if p and os.path.exists(p):
            return p
    return None


def _connect():
    path = locate_d3drdb()
    if not path:
        raise FileNotFoundError(
            "d3drdb file not found. Searched $D3DRDB_PATH, "
            "~/work/_User-Persistent-Storage_CephBlock_/feder/d3drdb.sqlite, "
            "~/feder_data/d3drdb_demo.sqlite, ~/d3drdb_demo.sqlite.\n"
            "Fix: upload d3drdb_demo.sqlite to "
            "~/work/_User-Persistent-Storage_CephBlock_/feder/d3drdb.sqlite"
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

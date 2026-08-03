"""IMAS <-> DIII-D terminology lookup.

Pure JSON lookup: no toksearch, no MDSplus, no network. Safe to import and
call in-kernel anywhere, including Colab where toksearch cannot be imported.

The table is extracted from GA's `imas_composer` (Apache-2.0) and every row
records whether it was verified by actually fetching it, and on which shots.
See feder/imas_d3d_mapping/ for the extractor and verification harness.
"""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache

_HERE = os.path.dirname(os.path.abspath(__file__))
_TABLE = os.path.join(_HERE, "imas_d3d_lookup.json")

# What each COCOS transform means. These matter: DIII-D and IMAS use different
# sign/orientation conventions, so a value fetched from DIII-D and presented
# under an IMAS name can be SIGN-FLIPPED unless the transform is applied.
COCOS_MEANING = {
    "PSI": "poloidal flux", "dPSI": "poloidal flux derivative",
    "1/PSI": "inverse poloidal flux", "invPSI": "inverse poloidal flux",
    "F_FPRIME": "F and F' flux-function derivatives",
    "PPRIME": "pressure derivative", "Q": "safety factor",
    "TOR": "toroidal quantity (includes plasma current)",
    "BT": "toroidal field", "IP": "plasma current",
    "F": "toroidal flux function", "POL": "poloidal quantity",
    "BP": "poloidal field",
}


@lru_cache(maxsize=1)
def _load() -> dict:
    with open(_TABLE) as f:
        return json.load(f)


def _norm(p: str) -> str:
    """Normalise an IMAS path for matching.

    Users write array indices (`equilibrium.time_slice[0].global_quantities.ip`)
    but the table stores the structure without them. Strip indices and case.
    """
    return re.sub(r"\[[^\]]*\]", "", (p or "").strip()).strip(".").lower()


def _cocos_fields_for(transform: str | None) -> dict:
    """The COCOS warning payload for a row. Single source of truth.

    Verified 2026-08-03: this used to be inlined in `imas_to_d3d` only, so
    `d3d_to_imas`/`search` returned `cocos_transform` but no `cocos_warning`.
    A caller checking for the warning (as this skill's own example does) got a
    false negative on exactly the fields the warning exists to protect. Every
    function that returns a row must go through here.
    """
    if not transform:
        return {}
    return {
        "cocos_transform": transform,
        "cocos_meaning": COCOS_MEANING.get(transform, ""),
        "cocos_warning": (
            f"Sign convention differs: apply the {transform} COCOS transform. "
            "Serving the raw DIII-D value under this IMAS name can be "
            "sign-flipped."
        ),
    }


def table_info() -> dict:
    """Provenance and coverage of the loaded table. Cite this, don't guess."""
    d = _load()
    return {
        "summary": d["summary"],
        "upstream_commit": d["provenance"]["extraction"]["commit"],
        "upstream_commit_date": d["provenance"]["extraction"]["commit_date"],
        "verification_shots": d["provenance"]["verification_shots"],
        "attribution": d["attribution"]["notice"],
    }


def imas_to_d3d(imas_path: str, shot: int | None = None,
                verified_only: bool = True) -> dict | None:
    """IMAS path -> the DIII-D signal that backs it.

    Returns None if the path is not in the table (say so plainly -- do NOT
    guess a DIII-D name from the IMAS name, they are unrelated vocabularies).

    shot: optional. If given, the result reports whether the mapping was
          verified for that era, because availability changes over the
          machine's history.
    verified_only: when True (default), unverified rows are still returned but
          flagged; nothing is hidden, but `verified` must be checked.
    """
    d = _load()
    want = _norm(imas_path)
    for k, row in d["imas_to_d3d"].items():
        if _norm(k) != want:
            continue
        out = dict(row)
        out["imas_path"] = k
        out.update(_cocos_fields_for(out.get("cocos_transform")))
        if shot is not None:
            ok = out.get("verified_on_shots") or []
            out["verified_for_shot"] = shot in ok
            if ok:
                out["verified_shot_range"] = [min(ok), max(ok)]
        if verified_only and not out.get("verified"):
            out["caution"] = ("This mapping was extracted but never fetched "
                              "successfully; treat it as unconfirmed.")
        return out
    return None


def d3d_to_imas(signal: str, tree: str | None = None) -> list[dict]:
    """DIII-D signal (or fragment) -> the IMAS field(s) it backs.

    Matches on the node path, the PTDATA pointname, or a trailing fragment,
    so both `\\EFIT01::TOP.MEASUREMENTS.CPASMA` and `CPASMA` work.
    """
    d = _load()
    q = (signal or "").strip().lower().lstrip("\\")
    hits = []
    for imas_path, row in d["imas_to_d3d"].items():
        p = (row.get("mds_path") or "").lower().lstrip("\\")
        pt = (row.get("ptdata_pointname") or "").lower()
        if tree and (row.get("tree") or "").lower() != tree.lower():
            continue
        if q and (q in p or (pt and q == pt) or p.endswith(q)):
            hit = {
                "imas_path": imas_path,
                "mds_path": row.get("mds_path"),
                "tree": row.get("tree"),
                "verified": row.get("verified"),
                "verified_on_shots": row.get("verified_on_shots"),
                "confidence": row.get("confidence"),
                "ids": row.get("ids"),
            }
            hit.update(_cocos_fields_for(row.get("cocos_transform")))
            hits.append(hit)
    return sorted(hits, key=lambda h: (not h["verified"], h["imas_path"]))


def search(term: str, limit: int = 20) -> list[dict]:
    """Free-text search across IMAS paths, DIII-D paths and summaries."""
    d = _load()
    q = (term or "").strip().lower()
    if not q:
        return []
    hits = []
    for imas_path, row in d["imas_to_d3d"].items():
        hay = " ".join(str(x) for x in (
            imas_path, row.get("mds_path"), row.get("ptdata_pointname"),
            row.get("summary"), row.get("ids")) if x).lower()
        if q in hay:
            hit = {
                "imas_path": imas_path,
                "mds_path": row.get("mds_path"),
                "tree": row.get("tree"),
                "ids": row.get("ids"),
                "verified": row.get("verified"),
                "verified_on_shots": row.get("verified_on_shots"),
                "confidence": row.get("confidence"),
            }
            hit.update(_cocos_fields_for(row.get("cocos_transform")))
            hits.append(hit)
    hits.sort(key=lambda h: (not h["verified"], len(h["imas_path"])))
    return hits[:limit]


def list_ids(verified_only: bool = False) -> dict[str, int]:
    """Which IMAS systems (IDS) are covered, and how many fields each."""
    d = _load()
    out: dict[str, int] = {}
    for row in d["imas_to_d3d"].values():
        if verified_only and not row.get("verified"):
            continue
        out[row["ids"]] = out.get(row["ids"], 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def cocos_fields() -> list[dict]:
    """Every field whose sign convention differs between DIII-D and IMAS."""
    d = _load()
    return [
        {"imas_path": k, "mds_path": r.get("mds_path"),
         "verified": r.get("verified"),
         **_cocos_fields_for(r["cocos_transform"])}
        for k, r in d["imas_to_d3d"].items() if r.get("cocos_transform")
    ]

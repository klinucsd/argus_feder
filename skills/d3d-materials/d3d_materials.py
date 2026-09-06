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
    sql = ["""SELECT s.name AS sample, o.stage, o.method, o.quantity, o.qualifier,
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
        out.setdefault(r["sample"], []).append(
            {k: r[k] for k in ("method", "stage", "quantity", "qualifier",
                               "value_num", "value_std", "unit")})
    return {k: (v[0] if len(v) == 1 else v) for k, v in out.items()}


def profiles(sample_names, quantity, method=None):
    """Depth-resolved series for a GROUP of samples -> {sample: [points]}.

    Points keep the order they were delivered in, and carry depth when the
    delivery supplied a depth axis.
    """
    rows = observations(sample_names, quantity=quantity, method=method, profile=True)
    out = {}
    for r in rows:
        out.setdefault(r["sample"], []).append(
            {"point_index": r["point_index"], "depth_um": r["depth_um"],
             "value": r["value_num"], "std": r["value_std"], "unit": r["unit"]})
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


def shots_for_samples(sample_names=None, device=None):
    """{sample_name: [shot, ...]} for a GROUP of samples, in one request.

    This is the join to the rest of the lakehouse: the shots come back as plain
    numbers, so they go straight into the disruption, ELM and shot-fetching
    skills. `device` says which machine they are shots of.
    """
    sql = ["""SELECT s.name AS sample, e.device, sh.shot
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
        out.setdefault(r["sample"], []).append(r["shot"])
    return out


def samples_for_shots(shots, device=None):
    """{shot: [sample_name, ...]} -- the reverse join, also in one request.

    Answers "was anything exposed during these shots", for a whole shot list at
    once. A shot with no sample is absent from the result.
    """
    sql = ["""SELECT sh.shot, e.device, s.name AS sample
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
        out.setdefault(r["shot"], []).append(r["sample"])
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
                     a.notes, a.device, a.shot, a.delivery_id,
                     s.name AS sample
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
    url = "%s/materials/artifact/%s" % (_endpoint(), artifact_id)
    headers = {}
    tok = _token()
    if tok:
        headers["Authorization"] = "Bearer %s" % tok
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            name = dest or resp.headers.get_filename() or artifact_id
            if dest and os.path.isdir(dest):
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

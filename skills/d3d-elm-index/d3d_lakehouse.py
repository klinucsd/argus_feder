"""Query the FEDER lakehouse over HTTP, in place of a local SQLite file.

One module, copied verbatim into each skill that needs it, because skills are
installed as self-contained directories under ~/.deepagents/agent/skills/ and
cannot import from each other.

THE MASTER IS `scripts/lakehouse_client/d3d_lakehouse.py`. Edit that one and run
`scripts/sync_lakehouse_client.sh`; never edit a per-skill copy, and never put
the master under `shared/skills/` -- the image copies that whole tree, so a
non-skill directory there is installed as if it were a skill, with no SKILL.md,
and lands in the agent's routing menu.

Two properties matter more than anything else here.

**Result keys are case-insensitive.** PostgreSQL lower-cases unquoted output
column names, so `SELECT SHOT FROM SHOTS` returns the key `shot`. The skills
were written against SQLite, which preserves the declared case, and read
`r["SHOT"]`, `r["Name"]`, `r["Full_Path"]` and so on in eleven places. Rather
than edit eleven call sites -- and every future one the agent writes -- rows
returned here resolve a key in any case.

**Truncation is an error, never a silent short result.** The endpoint caps a
result set and reports `truncated`. Returning the first N rows as though they
were all of them is the exact failure this project keeps finding: a plausible
number with nothing to notice. A truncated result raises instead, and says to
aggregate in SQL.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

# The deployed service. $FEDER_API_URL overrides it -- for a local instance, or
# if the service moves.
DEFAULT_ENDPOINT = "https://sparcal.sdsc.edu/api/v1/FEDER"

# The server's own ceiling. Asking for it means a result is either complete or
# reported as truncated; it can never be quietly clipped at some smaller default.
MAX_ROWS = 50000

TIMEOUT_SECONDS = float(os.environ.get("FEDER_API_TIMEOUT", "60"))

# The FDP token, if this environment has one. The lakehouse may require it for
# the raw d3drdb catalogue; the curated views and both label indexes are
# reachable without. Sent when present so nothing breaks the day the service
# starts asking, and simply omitted when not -- there is no failure here.
_TOKEN_ENV = ("FEDER_API_TOKEN", "FDP_TOKEN", "BEARER_TOKEN")
# Token files that exist but could not be read, so a 401 can say so
# instead of reporting "no token".
_UNREADABLE = []

_TOKEN_FILES = (
    "~/.fdp/token",
    # NRP JupyterHub: /home/jovyan is ephemeral and a pod restart wipes
    # ~/.fdp/token, while this path survives. Looking here too means a restart
    # does not silently break every skill call -- which it did, the first time a
    # pod came up on the endpoint-backed image.
    "~/work/_User-Persistent-Storage_CephBlock_/.fdp/token",
)


def _expiry(token):
    """The token's `exp` claim, or None if it cannot be read.

    Decoded, not verified -- the service does the verifying. This only has to be
    good enough to choose between two copies.
    """
    try:
        import base64                                        # noqa: PLC0415
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload)).get("exp")
    except Exception:                                        # noqa: BLE001
        return None


def bearer_token():
    """The FDP token to present, or None. Never logged, never in error text.

    An environment variable wins outright. Otherwise every candidate FILE is
    read and the one expiring LATEST is used, rather than the first one found.

    That matters on JupyterHub, where two copies routinely exist: `~/.fdp/token`
    is what Pelican reads and is wiped by a pod restart, while the copy under
    persistent storage survives. Taking the first would mean a stale leftover in
    `~/.fdp/token` shadowing a freshly renewed token sitting right beside it --
    presenting as "the database rejected my token" with a good one on disk.
    """
    for var in _TOKEN_ENV:
        v = os.environ.get(var)
        if v and v.strip():
            return v.strip()

    found = []
    for path in _TOKEN_FILES:
        expanded = os.path.expanduser(path)
        try:
            with open(expanded) as fh:
                v = fh.read().strip()
        except PermissionError:
            # Recorded rather than swallowed: a token with the wrong owner or
            # mode otherwise presents as "no token", sending the reader to look
            # for a file that is already there.
            _UNREADABLE.append(expanded)
            continue
        except OSError:
            continue
        if v:
            found.append(v)
    if not found:
        return None
    # -1 for an unreadable expiry, so a decodable token is preferred over one
    # this cannot judge, while still returning something if none can be read.
    return max(found, key=lambda t: (_expiry(t) or -1))


class LakehouseError(RuntimeError):
    """The lakehouse could not answer. The message says why, in those terms."""


class Row(dict):
    """A result row whose keys match in any case.

    `r["SHOT"]`, `r["shot"]` and `r["Shot"]` are the same value. Iteration and
    `.keys()` yield the names PostgreSQL actually returned, so anything printing
    a row shows the real column names.
    """

    def __init__(self, pairs):
        super().__init__(pairs)
        self._lower = {str(k).lower(): k for k in self}

    def __getitem__(self, key):
        try:
            return super().__getitem__(key)
        except KeyError:
            real = self._lower.get(str(key).lower())
            if real is None:
                raise KeyError(
                    f"{key!r} -- this row has {sorted(self)}") from None
            return super().__getitem__(real)

    def __contains__(self, key):
        return (super().__contains__(key)
                or str(key).lower() in self._lower)

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default


def endpoint():
    """Base URL of the lakehouse API, without a trailing slash."""
    return os.environ.get("FEDER_API_URL", DEFAULT_ENDPOINT).rstrip("/")


def _post(path, payload):
    url = f"{endpoint()}{path}"
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    tok = bearer_token()
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        try:
            detail = json.loads(detail).get("detail", detail)
        except Exception:                                        # noqa: BLE001
            pass
        if e.code == 401:
            if _UNREADABLE:
                raise LakehouseError(
                    f"the lakehouse rejected this request, and a token file "
                    f"exists but could not be read: {', '.join(_UNREADABLE)}. "
                    f"Check its owner and mode.") from None
            raise LakehouseError(
                "the lakehouse requires a valid FDP token and this one was not "
                f"accepted: {detail}. Renew it (the same token used for DIII-D "
                "data access through Pelican) and retry.") from None
        if e.code == 403:
            raise LakehouseError(
                f"this data needs a valid FDP token: {detail}") from None
        if e.code == 400:
            # The database rejected the statement -- a query problem, not an
            # outage. Surfaced as-is so the message names the real cause.
            raise LakehouseError(f"query rejected: {detail}") from None
        raise LakehouseError(
            f"lakehouse returned HTTP {e.code} for {url}: "
            f"{str(detail)[:300]}") from None
    except urllib.error.URLError as e:
        raise LakehouseError(
            f"cannot reach the lakehouse at {url}: {e.reason}. The service may "
            f"be down, or this environment may have no outbound network. There "
            f"is no local copy to fall back to -- the data lives only in the "
            f"lakehouse.") from None
    except TimeoutError:
        raise LakehouseError(
            f"the lakehouse did not answer within {TIMEOUT_SECONDS:.0f}s. A "
            f"query over the largest tables can be slow -- narrow it, or raise "
            f"$FEDER_API_TIMEOUT.") from None


def query(sql, params=(), limit=MAX_ROWS):
    """Run one read-only SELECT and return a list of Row.

    `sql` may use either `?` or `%s` placeholders; the service accepts both, and
    treats LIKE case-insensitively as SQLite does. Any rewrite it applies is
    reported and can be inspected with `last_compat_notes()`.
    """
    payload = {"sql": sql, "limit": int(limit)}
    if params:
        payload["params"] = list(params)
    out = _post("/query", payload)

    global _LAST_NOTES
    _LAST_NOTES = out.get("compat_notes") or []

    if out.get("truncated"):
        raise LakehouseError(
            f"the result was truncated at {out.get('row_count'):,} rows, so "
            f"this is NOT the whole answer. Aggregate in SQL (COUNT, AVG, "
            f"GROUP BY) or narrow the range, rather than reporting a partial "
            f"result.")

    names = [c["name"] for c in out.get("columns", [])]
    return [Row(zip(names, r)) for r in out.get("rows", [])]


_LAST_NOTES = []


def last_compat_notes():
    """Statement rewrites the service applied to the most recent query."""
    return list(_LAST_NOTES)


def scalar(sql, params=()):
    """The single value of a one-row, one-column query, or None."""
    rows = query(sql, params, limit=2)
    if not rows:
        return None
    return next(iter(rows[0].values()))


def tables(schema=None):
    """Table names the service exposes, optionally within one schema."""
    sql = ("SELECT table_schema AS schema, table_name AS name, table_type AS type "
           "FROM information_schema.tables WHERE table_schema = "
           + ("?" if schema else "ANY(current_schemas(false))")
           + " ORDER BY 1, 2")
    return query(sql, (schema,) if schema else ())


def columns(table, schema=None):
    """Column names and types of one table."""
    sql = ("SELECT column_name AS name, data_type AS type, is_nullable AS nullable "
           "FROM information_schema.columns WHERE table_name = ?"
           + (" AND table_schema = ?" if schema else "")
           + " ORDER BY ordinal_position")
    return query(sql, (table, schema) if schema else (table,))


def health():
    """What the service holds, or a LakehouseError explaining why not."""
    url = f"{endpoint()}/health"
    tok = bearer_token()
    req = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {tok}"} if tok else {})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:                                       # noqa: BLE001
        raise LakehouseError(f"cannot reach the lakehouse at {url}: {e}") from None

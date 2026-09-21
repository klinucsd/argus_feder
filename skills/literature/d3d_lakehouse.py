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
import re
import time
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

# Env vars holding an EXPIRED token, recorded so a 401 can name the real cause
# instead of leaving the reader hunting a token that is present and valid.
_EXPIRED_ENV = []

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

    An environment variable wins -- but only if it has not EXPIRED. Otherwise
    every candidate FILE is read and the one expiring LATEST is used, rather
    than the first one found.

    That matters on JupyterHub, where two copies routinely exist: `~/.fdp/token`
    is what Pelican reads and is wiped by a pod restart, while the copy under
    persistent storage survives. Taking the first would mean a stale leftover in
    `~/.fdp/token` shadowing a freshly renewed token sitting right beside it --
    presenting as "the database rejected my token" with a good one on disk.

    The expiry check on the env var closes the same hole one level up, and it
    is not hypothetical: BEARER_TOKEN is populated at kernel start from
    `~/.fdp/token`, so a pod whose ephemeral copy had gone stale exported an
    EXPIRED token into the environment, where it shadowed the valid one in
    persistent storage -- the precise failure this function's file handling was
    written to prevent, arriving by the one route that skipped the check.
    An expired env token now steps aside for a valid file token; a valid one
    still wins outright, so an explicit override behaves as before.
    """
    for var in _TOKEN_ENV:
        v = os.environ.get(var)
        if v and v.strip():
            v = v.strip()
            exp = _expiry(v)
            # Undecodable expiry -> trust it, as before: this cannot judge it,
            # and refusing would break any non-JWT token the service accepts.
            if exp is None or exp > time.time():
                return v
            _EXPIRED_ENV.append(var)

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


class _RowKeys:
    """Keys view for `Row`: iterates the real names, matches case-insensitively."""

    __slots__ = ("_row",)

    def __init__(self, row):
        self._row = row

    def __iter__(self):
        return iter(dict.keys(self._row))

    def __len__(self):
        return dict.__len__(self._row)

    def __contains__(self, key):
        return key in self._row          # Row.__contains__, case-insensitive

    def __eq__(self, other):
        try:
            return set(self) == set(other)
        except TypeError:
            return NotImplemented

    def __repr__(self):
        return "dict_keys(%r)" % (list(self),)


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

    def keys(self):
        """The real column names, but membership matches in any case.

        `.keys()` used to hand back a plain dict view, so `"KAPPA" in
        r.keys()` was False while `r["KAPPA"]`, `"KAPPA" in r` and
        `r.get("KAPPA")` all worked. That one inconsistent path is enough to
        make an agent conclude a documented column does not exist -- observed:
        it decided "some column names in the skill doc don't exist", then
        patched its script three times to work around a column that was there
        the whole time.

        Iteration still yields the names the database actually returned, so
        anything printing a row shows the real (lowercase) names.
        """
        return _RowKeys(self)


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
            if _EXPIRED_ENV:
                raise LakehouseError(
                    f"the lakehouse rejected this request. "
                    f"{', '.join(_EXPIRED_ENV)} holds an EXPIRED token and was "
                    f"skipped; no valid token was found in "
                    f"{', '.join(_TOKEN_FILES)} either. On JupyterHub "
                    f"BEARER_TOKEN is set at kernel start from ~/.fdp/token, so "
                    f"refresh that file and restart the kernel (or call "
                    f"reload_pelican()) -- setting the file alone leaves the "
                    f"stale value in the environment.") from None
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


# --------------------------------------------------------------------------
# Result memo
# --------------------------------------------------------------------------
# Every skill here is READ-ONLY against a service that does not change while a
# script runs, and the agent reliably writes loops over shots or times. Those
# loops re-ask identical questions: `compare_on_shot()` issues 17 queries per
# call, `elm_statistics()` nine, and a per-shot helper in a comprehension
# repeats all of them per iteration. Four separate cells stalled on exactly
# that shape in one day -- 6,001 calls for a 1 ms timeline, 7,000 for a range
# membership test -- each looking hung because output stays buffered.
#
# Memoising identical (sql, params) pairs removes the whole class, including
# from agent-written raw SQL, without the agent having to know anything. It is
# deliberately NOT a correctness shortcut: the cap keeps memory bounded, large
# results are not retained, and `clear_cache()` exists for the case where new
# data is ingested inside a live session.
_QUERY_CACHE = {}
_CACHE_MAX_ENTRIES = 256
_CACHE_MAX_ROWS = 5000


def clear_cache():
    """Forget memoised query results. Call after ingesting new data."""
    _QUERY_CACHE.clear()


def cache_info():
    """(entries, cap) -- for checking the memo is behaving."""
    return len(_QUERY_CACHE), _CACHE_MAX_ENTRIES


def _expand_sequences(sql, params):
    """Expand a sequence parameter into one placeholder per element.

    `query("... WHERE shot IN (?)", (shots,))` becomes
    `... WHERE shot IN (?,?,?)` with the shots flattened alongside.

    This exists so that asking about many shots has an obvious one-query
    shape. Without it the natural thing to write is a loop, and a loop is one
    HTTP round trip per shot -- 300 of them on one observed cell, against a
    single query that answered the same question in one.

    Untouched unless a parameter really is a non-string sequence, so every
    existing query takes exactly the path it took before.
    """
    seqs = (list, tuple, set, frozenset, range)
    if not params or not any(isinstance(p, seqs) for p in params):
        return sql, params

    holes = list(re.finditer(r"\?|%s", sql))
    if len(holes) != len(params):
        # Placeholder count and parameter count disagree -- let the service
        # report it rather than guessing which is which here.
        return sql, params

    out, cursor, flat = [], 0, []
    for hole, p in zip(holes, params):
        out.append(sql[cursor:hole.start()])
        token = hole.group(0)
        if isinstance(p, seqs):
            vals = list(p)
            if not vals:
                # `IN ()` is invalid SQL everywhere; NULL matches nothing,
                # which is exactly what an empty list means.
                out.append("NULL")
            else:
                out.append(",".join([token] * len(vals)))
                flat.extend(vals)
        else:
            out.append(token)
            flat.append(p)
        cursor = hole.end()
    out.append(sql[cursor:])
    return "".join(out), tuple(flat)


def query(sql, params=(), limit=MAX_ROWS, cache=True):
    """Run one read-only SELECT and return a list of Row.

    `sql` may use either `?` or `%s` placeholders; the service accepts both, and
    treats LIKE case-insensitively as SQLite does. Any rewrite it applies is
    reported and can be inspected with `last_compat_notes()`.

    Identical (sql, params) pairs are served from an in-process memo; pass
    `cache=False` to force a round trip, or call `clear_cache()`.
    """
    global _LAST_NOTES
    sql, params = _expand_sequences(sql, params)
    key = None
    if cache:
        try:
            key = (sql, tuple(params), int(limit))
        except TypeError:
            key = None                      # unhashable params -> just fetch
        if key is not None and key in _QUERY_CACHE:
            rows, notes = _QUERY_CACHE[key]
            _LAST_NOTES = list(notes)
            return [Row(r.items()) for r in rows]

    payload = {"sql": sql, "limit": int(limit)}
    if params:
        payload["params"] = list(params)
    out = _post("/query", payload)

    _LAST_NOTES = out.get("compat_notes") or []

    if out.get("truncated"):
        raise LakehouseError(
            f"the result was truncated at {out.get('row_count'):,} rows, so "
            f"this is NOT the whole answer. Aggregate in SQL (COUNT, AVG, "
            f"GROUP BY) or narrow the range, rather than reporting a partial "
            f"result.")

    names = [c["name"] for c in out.get("columns", [])]
    rows = [Row(zip(names, r)) for r in out.get("rows", [])]

    # Small results only: a memo that holds a million sample rows would trade
    # one problem for a worse one.
    if key is not None and len(rows) <= _CACHE_MAX_ROWS:
        if len(_QUERY_CACHE) >= _CACHE_MAX_ENTRIES:
            _QUERY_CACHE.pop(next(iter(_QUERY_CACHE)))
        _QUERY_CACHE[key] = (rows, list(_LAST_NOTES))
    return [Row(r.items()) for r in rows]


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

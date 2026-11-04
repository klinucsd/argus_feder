"""Read pipeline provenance from a CMF server.

CMF records what a computational pipeline did: the stages it ran, the code and
parameters each stage used, the artifacts it produced, and how those artifacts
descend from one another. This module reads it. Nothing here writes, by
construction -- the only POST is the authentication call.

Credentials come from the environment, or from a `.env`. The file is looked for
beside the notebook, then in each folder above it, then in the pod's persistent
storage (`~/work/_User-Persistent-Storage_CephBlock_`), then in the home
directory:

    KEYCLOAK_USERNAME   a user account in the server's Keycloak realm
    KEYCLOAK_PASSWORD

Authorisation is per user: the server decides what a caller may read from the
role in that caller's own token. There is no shared account to fall back on, so
a notebook that cannot find credentials reports that rather than reading
somebody else's view of the server.

The access token is short-lived, so every call checks its age and
re-authenticates rather than carrying one token through a long session.

Each function returns whole objects for a pipeline rather than one field at a
time. Ask for a pipeline once and read what you need from the result; calling a
per-field accessor in a loop turns one question into dozens of HTTP round trips.
"""
from __future__ import annotations

import base64
import json
import os
import pathlib
import time
import urllib.error
import urllib.request

DEFAULT_BASE = "http://awesome.sdsc.edu:8089/api"
DEFAULT_CLIENT_ID = "d3dsearch"

# The access token is valid for a few minutes. Refresh well before it lapses so
# a request never sets out with a credential that dies in flight.
_TOKEN_TTL = 240

_state = {"token": None, "at": 0.0}


class CMFUnavailable(RuntimeError):
    """The CMF server could not be reached or would not authenticate."""


class CMFForbidden(RuntimeError):
    """The server refused this read for this user.

    This is an answer, not a malfunction: authorisation is per user, so a
    pipeline another user can read may be closed to this one. Report it as the
    result rather than retrying or working around it.
    """


def base_url() -> str:
    return os.environ.get("FEDER_CMF_URL", DEFAULT_BASE).rstrip("/")


# Accepted credential variable names, in order of preference. The first pair is
# the convention; the second is what the knowledge-graph proxy already uses, so
# an environment configured for that one works here too.
_CREDENTIAL_NAMES = (("KEYCLOAK_USERNAME", "KEYCLOAK_PASSWORD"),
                     ("FEDER_KG_USERNAME", "FEDER_KG_PASSWORD"))


def _read_dotenv():
    """Values from a `.env` beside the notebook, or above it.

    A notebook written for a reader carries no setup cell, so the credentials
    have to be found rather than assigned. Only the names this module needs are
    read, the file is never written, and anything already in the environment
    wins over the file.
    """
    wanted = {n for pair in _CREDENTIAL_NAMES for n in pair} | {"KEYCLOAK_URL",
                                                                "FEDER_CMF_URL"}
    found = {}
    here = pathlib.Path(os.environ.get("FEDER_DOTENV_DIR", os.getcwd())).resolve()
    # The notebook's own folder and everything above it, then the pod's
    # persistent storage. A credential belongs in persistent storage because
    # the home directory does not survive the pod -- the same reason the
    # pelican token is kept there -- and the notebook is not always underneath
    # it, so walking up from the notebook alone would miss it.
    home = pathlib.Path.home()
    search = [here, *here.parents,
              home / "work" / "_User-Persistent-Storage_CephBlock_",
              home]
    seen = set()
    for folder in search:
        if folder in seen:
            continue
        seen.add(folder)
        candidate = folder / ".env"
        if not candidate.is_file():
            continue
        try:
            for line in candidate.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                if key in wanted and key not in found:
                    found[key] = value.strip().strip('"').strip("'")
        except OSError:
            continue
        if found:
            break
    return found


def _credentials():
    for user_var, password_var in _CREDENTIAL_NAMES:
        user, password = os.environ.get(user_var), os.environ.get(password_var)
        if user and password:
            return user, password
    env = _read_dotenv()
    for user_var, password_var in _CREDENTIAL_NAMES:
        if env.get(user_var) and env.get(password_var):
            return env[user_var], env[password_var]
    raise CMFUnavailable(
        "No CMF credentials found. Set KEYCLOAK_USERNAME and KEYCLOAK_PASSWORD "
        "in the environment, or put them in a .env beside the notebook. "
        "Authorisation is per user, so there is no shared credential to fall "
        "back on -- report this rather than reading as somebody else.")


def _call(path, body=None, token=None, timeout=90):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base_url() + path, data=data,
                                 method="POST" if data else "GET")
    req.add_header("Accept", "application/json")
    if data:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raw = e.read().decode()[:500]
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw
    except Exception as e:
        raise CMFUnavailable(f"{type(e).__name__} reaching {base_url()}: {e}")


def token(force: bool = False) -> str:
    """A current access token, re-authenticating when the cached one is stale."""
    if _state["token"] and not force and time.time() - _state["at"] < _TOKEN_TTL:
        return _state["token"]
    user, password = _credentials()
    status, res = _call("/v1/auth/token",
                        body={"grant_type": "password",
                              "client_id": os.environ.get("KEYCLOAK_CLIENT_ID",
                                                          DEFAULT_CLIENT_ID),
                              "username": user, "password": password})
    if status != 200:
        used = next((pair[0] for pair in _CREDENTIAL_NAMES
                     if os.environ.get(pair[0])), _CREDENTIAL_NAMES[0][0])
        raise CMFUnavailable(
            f"CMF authentication failed (HTTP {status}). The credentials were "
            f"found but the server rejected them: check KEYCLOAK_USERNAME and "
            f"KEYCLOAK_PASSWORD against the server's Keycloak realm "
            f"(the username in use came from {used}).")
    data = res.get("data") or {}
    tok = data.get("access_token")
    if not tok:
        raise CMFUnavailable("CMF returned no access token.")
    _state["token"], _state["at"] = tok, time.time()
    return tok


def whoami() -> dict:
    """Who the server thinks we are, and which roles the token carries.

    Read this before reporting that something is absent: a short list of
    pipelines may mean a narrow role rather than an empty server.
    """
    tok = token()
    payload = tok.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    claims = json.loads(base64.urlsafe_b64decode(payload))
    status, res = _call("/v1/auth/status", token=tok)
    status_data = (res or {}).get("data") if isinstance(res, dict) else {}
    return {"username": claims.get("preferred_username"),
            "client": claims.get("azp"),
            "realm": claims.get("iss"),
            "realm_roles": (claims.get("realm_access") or {}).get("roles", []),
            "resource_roles": claims.get("resource_access") or {},
            "token_seconds_remaining": max(0, claims.get("exp", 0) - int(time.time())),
            "server_says": status_data}


def _get(path):
    status, res = _call(path, token=token())
    if status == 401:
        status, res = _call(path, token=token(force=True))
    if status == 403:
        raise CMFForbidden(f"The server refused {path} for this user.")
    if status != 200:
        raise CMFUnavailable(f"HTTP {status} from {path}: "
                             f"{json.dumps(res)[:200] if isinstance(res, dict) else res}")
    if isinstance(res, dict) and "data" in res:
        return res["data"]
    return res


def pipelines() -> list:
    """Every pipeline name this user may see. Start here; do not guess a name."""
    names = _get("/v1/pipelines")
    if isinstance(names, dict):
        names = names.get("pipelines", [])
    return list(names)


def _flatten_properties(record: dict) -> dict:
    """Lift `custom_properties_x` keys to `x`, dropping the ones with no value.

    Providers record their own property names, so never assume a particular one
    is present: read what the returned dictionary actually has.
    """
    out = {}
    for key, value in record.items():
        if key.startswith("custom_properties_"):
            name = key[len("custom_properties_"):]
            if value not in (None, "", [], {}):
                out[name] = value
    return out


def executions(name: str) -> list:
    """One entry per stage run, with its parameters flattened into `properties`."""
    rows = _get(f"/v1/pipelines/{name}/executions")
    out = []
    for r in rows or []:
        out.append({
            "id": r.get("id"),
            "stage": r.get("Context_Type") or r.get("Execution_type_name"),
            "uuid": r.get("Execution_uuid"),
            "git_repo": r.get("Git_Repo"),
            "git_start_commit": r.get("Git_Start_Commit"),
            "git_end_commit": r.get("Git_End_Commit"),
            "properties": _flatten_properties(r),
        })
    return sorted(out, key=lambda e: e.get("id") or 0)


def artifacts(name: str) -> list:
    """Every artifact, with its type, hash, location and recorded metrics.

    A `Metrics` artifact carries its numbers in `properties`. A `Dataset` or
    `Environment` artifact carries a location and a hash but NOT its contents --
    CMF stores references, never bytes.
    """
    rows = _get(f"/v1/pipelines/{name}/artifacts")
    out = []
    for r in rows or []:
        out.append({
            "id": r.get("id"),
            "name": r.get("name"),
            "type": r.get("type"),
            "hash": r.get("Commit") or r.get("uri"),
            "location": r.get("url"),
            "properties": _flatten_properties(r),
        })
    return sorted(out, key=lambda a: a.get("id") or 0)


def lineage(name: str) -> dict:
    """How the artifacts descend from one another, by the views the server offers.

    The server exposes more than one lineage view and they do not always agree:
    one may come back empty while another renders the same pipeline correctly.
    Read `artifacts` first and treat an empty view as a gap in that view, not as
    a pipeline without lineage.
    """
    out = {}
    for label, path in (("artifacts", f"/v1/pipelines/{name}/artifacts/lineage"),
                        ("artifact_executions",
                         f"/v1/pipelines/{name}/artifact-executions/lineage"),
                        ("hierarchical", f"/v1/pipelines/{name}/hierarchical-lineage")):
        try:
            out[label] = _get(path)
        except (CMFUnavailable, CMFForbidden) as e:
            out[label] = {"unavailable": str(e)}
    return out


def pipeline(name: str) -> dict:
    """Everything about one pipeline, in one call. Prefer this over the pieces."""
    stages = _get(f"/v1/pipelines/{name}/stages")
    if isinstance(stages, dict):
        stages = stages.get("stages", [])
    return {"name": name,
            "stages": list(stages),
            "executions": executions(name),
            "artifacts": artifacts(name),
            "lineage": lineage(name)}


def overview() -> list:
    """A short summary of every visible pipeline: stages, counts, parameters seen.

    One call for the whole server. Use it to answer "what work exists" without
    fetching each pipeline separately.
    """
    rows = []
    for name in pipelines():
        try:
            ex = executions(name)
            ar = artifacts(name)
        except CMFForbidden as e:
            rows.append({"name": name, "forbidden": str(e)})
            continue
        seen = sorted({k for e in ex for k in e["properties"]})
        rows.append({
            "name": name,
            "stages": [e["stage"] for e in ex],
            "n_executions": len(ex),
            "n_artifacts": len(ar),
            "artifact_types": sorted({a["type"] for a in ar if a.get("type")}),
            "property_names": seen,
        })
    return rows


def metrics(name: str) -> dict:
    """The recorded numbers, keyed by artifact name.

    These are what a stage chose to record about its own run. They describe the
    run, not whether its result is correct.
    """
    return {a["name"]: a["properties"]
            for a in artifacts(name)
            if a.get("type") == "Metrics" and a["properties"]}


def find_by_hash(digest: str) -> list:
    """Where a file came from, given its hash. Searches every visible pipeline."""
    digest = digest.strip().lower()
    hits = []
    for name in pipelines():
        try:
            for a in artifacts(name):
                h = (a.get("hash") or "").lower()
                if h and (h == digest or digest in h or h in digest):
                    hits.append({"pipeline": name, **a})
        except CMFForbidden:
            continue
    return hits


def parameters_table(names=None) -> list:
    """Every stage's parameters across pipelines, one row per stage.

    Built for comparison: to explain why two results differ, line up their rows
    and look for the parameter that is not the same.
    """
    rows = []
    for name in (names if names is not None else pipelines()):
        try:
            for e in executions(name):
                rows.append({"pipeline": name, "stage": e["stage"],
                             "commit": (e.get("git_start_commit") or "")[:12],
                             **e["properties"]})
        except CMFForbidden:
            continue
    return rows

"""The papers attached to a dataset.

A dataset sometimes arrives with the publications behind it -- the references
its proposal cites, the method papers it depends on. This reaches them.

It is deliberately ignorant of any particular dataset. Everything is addressed
by a `scope`, a (scope_type, scope_id) pair that the dataset's own skill knows
how to produce. That is why one literature layer serves every dataset instead
of each dataset growing its own.

    import literature as lit

    scope = mat.literature_scope()              # the dataset's skill says where
    lit.works(scope)                            # what papers came with it
    lit.get_chunks("does the layer block the fuel", scope)

WHAT THIS IS FOR, AND WHAT IT IS NOT FOR. A paper explains why an experiment
was designed the way it was, and what other groups found. It is context for
interpretation. Every number in an answer still comes from the dataset: a paper
reports somebody else's experiment, on their material, in their machine.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from d3d_lakehouse import LakehouseError  # noqa: E402,F401
from d3d_lakehouse import _post as _api_post  # noqa: E402
from d3d_lakehouse import endpoint  # noqa: E402,F401


class NoLiteratureForScope(LookupError):
    """No papers are attached to this dataset.

    An exception rather than an empty list: "no chunks" must never be read as
    "the literature says nothing about it".
    """


def works(scope=None):
    """The papers attached to a dataset -- bibliography only, no text.

    `scope` is (scope_type, scope_id) from the dataset's own skill. Omit it to
    list every catalogued work.

    Answers "what did this dataset come with", which is a different question
    from "what do those papers say". Ask this first when a question is about
    provenance or coverage; ask `get_chunks` when it is about content.
    """
    path = "/literature/works"
    if scope:
        path += "?scope_type=%s&scope_id=%s" % (scope[0], scope[1])
    # The route is a GET; _post is POST-only, so go through the same client's
    # request plumbing by way of a small local call.
    return _get(path).get("works", [])


def _get(path):
    import json
    import urllib.request
    from d3d_lakehouse import bearer_token
    req = urllib.request.Request(
        endpoint() + path,
        headers={"Accept": "application/json",
                 "Authorization": "Bearer %s" % (bearer_token() or "")})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read().decode())
    except Exception as e:                                       # noqa: BLE001
        raise LakehouseError("literature request failed: %s: %s"
                             % (type(e).__name__, e)) from None


def get_chunks(query, scope=None, k=5, mode="hybrid"):
    """The passages of the attached papers that bear on a question.

    Ask in ordinary words. This is not a regex and not SQL: "does pre-loading
    the metal with one gas change how much fuel it keeps" works, and finds the
    right paper even when it shares no words with the text.

    Two searches run and are merged. One embeds the question and matches
    meaning, which is what crosses a vocabulary gap. The other is exact-term
    search, which is what catches jargon a paraphrase would blur. Neither alone
    is reliable: on a paraphrased question the exact-term half can return a
    confidently wrong paper.

    Returns a dict with `chunks`, each carrying:

        work_id, section, page_from, page_to, text, citation, score

    `citation` is assembled by the server from the catalogue. Quote it as it
    stands; do not rebuild it from the text, because a year or a volume retyped
    is a year or a volume that can be wrong.

    `note` is set when something degraded -- most often that the semantic half
    was unavailable and the answer is exact-term only. Read it: an answer built
    on half the retrieval is worth saying so.

    Raises NoLiteratureForScope when the dataset has no papers attached, rather
    than returning an empty list that reads like "nothing found".
    """
    if not query or not str(query).strip():
        raise ValueError("query is empty; ask a question in words")
    payload = {"query": str(query), "k": int(k), "mode": mode}
    if scope:
        payload["scope"] = [str(scope[0]), str(scope[1])]
    out = _api_post("/literature/get_chunks", payload)
    note = (out or {}).get("note") or ""
    if not out.get("chunks") and "no works are attached" in note:
        raise NoLiteratureForScope(
            "no papers are attached to %r. That is not a statement about what "
            "the literature says; this dataset simply has none catalogued." % (scope,))
    return out


def quote_check(chunks, text):
    """Does this wording actually appear in one of the chunks you were given?

    Use it before attributing a quotation. A near-miss -- a word changed, a
    clause dropped -- reads as a quotation and is not one, and nothing else in
    an answer will reveal it.

    Returns the matching chunk, or None.
    """
    needle = " ".join(str(text).split())
    for c in (chunks or {}).get("chunks", chunks if isinstance(chunks, list) else []):
        if needle and needle in " ".join(c.get("text", "").split()):
            return c
    return None

---
name: literature
description: "Read the published papers attached to a dataset: the references a delivery's proposal cites, the method papers behind it. Ask a question in ordinary words and get back the few most relevant passages, each with its page and a ready-made citation. Use when a question asks WHY an experiment was designed a certain way, what a cited paper actually found, or how a result compares with published work. The measurements themselves come from the dataset's own skill, never from here."
license: Apache-2.0
compatibility: standard library only; runs in the image, on Colab, or locally
metadata:
  version: "1.0"
---

# literature -- the papers that came with a dataset

```python
import sys, os
sys.path.insert(0, os.path.expanduser("~/.deepagents/agent/skills/literature"))
import literature as lit
```

## A scope says which dataset's papers to read

Papers belong to the dataset they arrived with. A scope is the pair that names
it, and the dataset's own skill produces it:

```python
scope = mat.literature_scope()          # the dataset's skill knows its own scope
lit.works(scope)                        # what papers came with it
lit.get_chunks("does the layer block the fuel", scope)
```

Passing the scope keeps searches inside the right dataset's papers. Omitting it
searches everything catalogued, which is rarely what a question about one
dataset means.

`get_chunks` raises `NoLiteratureForScope` when a dataset has no papers, rather
than returning an empty list. "No chunks" must never be read as "the literature
says nothing about it".

## Ask in words, not in patterns

```python
lit.get_chunks("does pre-loading the metal with one gas change how much fuel it keeps")
```

That is a real query and it finds the right paper, though it shares no words
with the paper's title. Two searches run behind it: one matches meaning, one
matches exact terms, and the results are merged. Ask the question the way a
person would ask it.

Keep `k` small. Five passages is usually plenty and the answer is better for
having read them than for having skimmed twenty.

## What comes back, and how to use it

`get_chunks` returns a dict, and the passages are under `chunks`. Real output,
trimmed:

```python
r = lit.get_chunks("does helium block deuterium", scope, k=1)
```
```json
{
  "chunks": [
    {
      "work_id": "baldwin_2017",
      "chunk_no": 1,
      "section": "1 Introduction (1)",
      "page_from": 2,
      "page_to": 2,
      "text": "1. Introduction\nThere is a growing consensus [1] that future ...",
      "citation": "M.J. Baldwin and R.P. Doerner (2017) Hydrogen isotope tran ...",
      "score": 0.03306
    }
  ],
  "mode": "hybrid",
  "note": null
}
```

So iterate `r["chunks"]`, not `r`.

**Quote the `citation` as it stands.** The server assembles it from the
catalogue. Rebuilding one by reading the paper means retyping a year or a
volume, and a retyped number is one that can be wrong while looking right.

**Say which paper a claim comes from, in the same sentence as the claim.** A
paper reports somebody else's experiment, in their machine, on their material.
A finding from another device is context; it is not evidence about the dataset
in hand, and a sentence that does not say whose result it is invites the reader
to assume the wrong one.

**Check a quotation before attributing it:**

```python
hit = lit.quote_check(chunks, "the exact wording you are about to quote")
```

It returns the chunk the wording appears in, or None. A near-miss -- one word
changed, a clause dropped -- still reads as a quotation, and nothing else in an
answer reveals it.

**Read `note`.** It is set when retrieval degraded, most often when the
semantic half was unavailable and only exact-term search ran. An answer built
on half the retrieval is worth saying so.

## The search ranks, it does not filter

Whenever any papers are attached, `get_chunks` returns its k best passages.
There is no "nothing found": if the papers never considered the question, the
result is the closest thing they contain, returned with the same confident
shape as a direct answer.

`score` will not tell you which case you are in. It fuses the two rankings, so
it records where a passage placed, not whether it is relevant, and the top
passage scores about the same either way. In a measured check the top passage
for an unrelated question scored 0.0328 where a well-matched question's scored
0.0333 -- a difference that means nothing.

So the passages decide, not the score. Read them, and ask of each one: **does
this support a specific sentence I am writing?** Cite it when it does, in that
sentence.

Leave it out when it merely shares a subject. A passage on the same material,
the same machine or the same physics that does not speak to the question adds a
citation the reader can check and find beside the point, which costs more than
the passage was ever worth.

Finding nothing usable is an ordinary outcome and needs no remark. Write the
answer from the data and say nothing about the literature -- reporting a search
that came back empty tells the reader about the tooling, when they asked about
the measurements.

## The boundary that matters

Literature is context for interpretation. **Every number in an answer comes
from the dataset**, through the dataset's own skill.

A paper can say what mechanism was proposed, what a prior experiment measured,
what conditions a result held under. It cannot say what this dataset's samples
did. When a paper and the data appear to disagree, that is a finding worth
reporting as one -- not a reason to prefer either.

## The API

```python
lit.works(scope=None)                   # bibliography only, no text
lit.get_chunks(query, scope=None, k=5, mode="hybrid")
lit.quote_check(chunks, text)           # does this wording really appear?
```

`mode` is `hybrid` by default, which is what you want. `lexical` is exact-term
only and `semantic` is meaning only; both exist for diagnosis, and on a
paraphrased question `lexical` alone can return a confidently wrong paper.

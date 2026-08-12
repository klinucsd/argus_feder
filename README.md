# ARGUS-FEDER

Ask questions about DIII-D fusion data in plain English — either on Google
Colab, needing nothing but a browser and an LLM API key, or on JupyterHub
using the prebuilt image.

## Quick start

Pick a notebook from [Examples](#examples) below and open it in Colab, then
run the cells in order. You'll need:
- An API key for any supported LLM provider (NRP, OpenAI, Anthropic, ...)
- A DIII-D Pelican access token

Both are added as Colab Secrets — instructions are in the notebook.

## Examples

Each example comes in two forms. The **JupyterHub** notebook is the source: it
assumes ARGUS, TokSearch and the DIII-D skills are already installed, as they
are in the `kaiucsd/argus-feder` image. The **Colab** variant is the same
notebook plus an install bootstrap, so a recipient can just hit *Run all*.

Both variants ask byte-for-byte identical `%%ask` questions, so the two
environments can be compared directly. Both are saved with their real outputs
— you can read what ARGUS answered without running anything.

### Pelican data access, metadata, and PTDATA

ARGUS answering plain-English questions about DIII-D through four different
access paths: resolving a physics concept to the right MDSplus signal with no
symbol name given, querying the shot-metadata database, fetching from PTDATA
(a separate raw-digitizer source), and looking up signal meanings, MDSplus
paths and IMAS names.

[![JupyterHub notebook](https://raw.githubusercontent.com/klinucsd/argus_feder/main/assets/jupyterhub-badge.svg)](examples/jupyterhub/argus_feder_pelican_database_ptdata_jupyterhub.ipynb)
[![Open in Colab](https://raw.githubusercontent.com/klinucsd/argus_feder/main/assets/colab-badge.svg)](https://colab.research.google.com/github/klinucsd/argus_feder/blob/main/examples/colab/argus_feder_pelican_database_ptdata_colab.ipynb)

### FEDER ELM competency questions

FEDER's ELM competency questions answered in plain English, from a stored index
of ELM labels: what each detector defines as an ELM and at which parameters
(Q2), which D-alpha filterscope channels a shot has and at what sampling rate
(Q5, Q7, Q9), where two detectors and a domain expert disagree on the same
discharge (Q12), when the plasma was ELMing and when ELM activity was absent
(Q3), and what a candidate ELM training set would contain (Q4, Q11).

The notebook also asks questions the list does not cover, and two whose correct
answer is a refusal — a shot nobody has analysed, and a population statistic the
sample cannot support. A confident number in either case would be a failure, not
a success.

[![JupyterHub notebook](https://raw.githubusercontent.com/klinucsd/argus_feder/main/assets/jupyterhub-badge.svg)](examples/jupyterhub/argus_feder_elm_index_jupyterhub.ipynb)
[![Open in Colab](https://raw.githubusercontent.com/klinucsd/argus_feder/main/assets/colab-badge.svg)](https://colab.research.google.com/github/klinucsd/argus_feder/blob/main/examples/colab/argus_feder_elm_index_colab.ipynb)

### Sorting measurements by where they fall in the ELM cycle

An analysis rather than a question: ARGUS uses stored ELM event times to sort
Thomson scattering measurements by where they fall in the ELM cycle, then shows
what an average over everything hides. Thomson samples on its own clock — about
eight times faster than the ELMs, but unsynchronised with them — so each profile
lands at an arbitrary point in the cycle, and the naive average blends
crash-phase and recovered plasma into a state the discharge never holds. The
notebook picks a suitable discharge from the stored labels, checks the event
times against a domain expert's before trusting them, and reports where in the
plasma the ELM actually reaches.

[![JupyterHub notebook](https://raw.githubusercontent.com/klinucsd/argus_feder/main/assets/jupyterhub-badge.svg)](examples/jupyterhub/argus_feder_elm_phase_analysis_jupyterhub.ipynb)
[![Open in Colab](https://raw.githubusercontent.com/klinucsd/argus_feder/main/assets/colab-badge.svg)](https://colab.research.google.com/github/klinucsd/argus_feder/blob/main/examples/colab/argus_feder_elm_phase_analysis_colab.ipynb)

### IMAS ↔ DIII-D terminology

Translating between IMAS — the device-neutral standard vocabulary used across
fusion machines and by ITER — and DIII-D's own historical signal names, in both
directions. The mapping is extracted from GA's
[`imas_composer`](https://github.com/GA-FDP/imas_composer) (Apache-2.0) and every
entry was checked by actually fetching it across shots spanning more than two
decades of machine operation. The notebook also exercises what a plain name-pair
table gets wrong: sign conventions that differ between the two vocabularies,
availability that changes over the machine's history, fields whose provenance is
incomplete, and mistyped input.

[![JupyterHub notebook](https://raw.githubusercontent.com/klinucsd/argus_feder/main/assets/jupyterhub-badge.svg)](examples/jupyterhub/argus_feder_imas_d3d_jupyterhub.ipynb)
[![Open in Colab](https://raw.githubusercontent.com/klinucsd/argus_feder/main/assets/colab-badge.svg)](https://colab.research.google.com/github/klinucsd/argus_feder/blob/main/examples/colab/argus_feder_imas_d3d_colab.ipynb)

## Running on JupyterHub

The JupyterHub notebooks need no install step — use the prebuilt image:

```
kaiucsd/argus-feder:0.1.4
```

Supply two credentials at runtime (neither is baked into the image):
- `NRP_API_KEY` — in the environment or a `.env` in the working directory
- A DIII-D Pelican token at
  `~/work/_User-Persistent-Storage_CephBlock_/.fdp/token` (survives pod
  restarts; `~/.fdp/token` also works but is wiped when the pod recycles).
  If the kernel was already running when you added it, call
  `reload_pelican()` — no restart needed.

## What this is

ARGUS-FEDER combines [ARGUS](https://github.com/klinucsd/sage) (a
notebook-native natural-language science agent) with DIII-D data access via
[TokSearch](https://github.com/GA-FDP/toksearch) and GA's Pelican mirror.
Ask a question in a `%%ask` cell; ARGUS writes and runs the code to answer it
against real DIII-D shot data.

## Maintainers

`install.py` and `skills/` are the source of truth for what gets installed
into a Colab session — see comments in `install.py` for the reasoning behind
non-obvious steps (e.g. why `fdp` is installed as its own step, separate from
`fdp-d3d`).

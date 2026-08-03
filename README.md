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

[JupyterHub notebook](examples/jupyterhub/argus_feder_pelican_database_ptdata_jupyterhub.ipynb)
&nbsp;·&nbsp;
[![Open in Colab](https://raw.githubusercontent.com/klinucsd/argus_feder/main/assets/colab-badge-large.svg)](https://colab.research.google.com/github/klinucsd/argus_feder/blob/main/examples/colab/argus_feder_pelican_database_ptdata_colab.ipynb)

### FEDER competency questions (Q5, Q7, Q9) and interactive charts

FEDER's ELM data-discovery competency questions answered in plain English —
which D-alpha filterscope pointnames exist and where each lives (Q5), which
shots in a range have the filterscope signal archived (Q7), and whether the
sampling rate resolves individual ELMs (Q9). Also demonstrates the opt-in
zoomable Plotly chart, needed to see individual ELM spikes in a ~400,000-point
trace, and a proof-of-concept aggregation query across a shot range.

[JupyterHub notebook](examples/jupyterhub/argus_feder_q5_q7_q9_jupyterhub.ipynb)
&nbsp;·&nbsp;
[![Open in Colab](https://raw.githubusercontent.com/klinucsd/argus_feder/main/assets/colab-badge-large.svg)](https://colab.research.google.com/github/klinucsd/argus_feder/blob/main/examples/colab/argus_feder_q5_q7_q9_colab.ipynb)

## Running on JupyterHub

The JupyterHub notebooks need no install step — use the prebuilt image:

```
kaiucsd/argus-feder:0.1.1-rc2
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

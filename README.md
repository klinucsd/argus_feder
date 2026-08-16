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

### Building a training cohort for a published ELM-forecasting study

A research task set by someone else.
[Teo et al. (2026)](https://arxiv.org/abs/2604.06508) train a neural network
to forecast the first ELM after the L-H transition, and state their own
principal limitation twice: the dataset is too small to quantify performance, and
identifying which discharges are relevant for training is a necessary next step.
They used 26 discharges. In six plain-English questions and no code, ARGUS
establishes what labels exist and who produced them, characterises the
distribution of first-ELM times, assembles a candidate cohort of 4,873
discharges, interrogates an anomaly in its own data, grounds one case in the raw
D-alpha signal, and states what the cohort cannot support — including that it
cannot reproduce the original study, because nothing in the data locates the
L-H transition.

[![JupyterHub notebook](https://raw.githubusercontent.com/klinucsd/argus_feder/main/assets/jupyterhub-badge.svg)](examples/jupyterhub/argus_feder_elm_forecast_cohort_jupyterhub.ipynb)
[![Open in Colab](https://raw.githubusercontent.com/klinucsd/argus_feder/main/assets/colab-badge.svg)](https://colab.research.google.com/github/klinucsd/argus_feder/blob/main/examples/colab/argus_feder_elm_forecast_cohort_colab.ipynb)

### Testing a published claim: do turbulence precursors precede an ELM?

A complete study rather than a query. Joung et al. (*Nucl. Fusion* **64**,
066038, 2024) train a network to predict ELM onset from beam emission
spectroscopy and report that pedestal turbulence in the 15–150 kHz band rises
before the crash. The claim underneath the network is a measurement, so it can
be tested directly — here against ELM labels from a detector with recorded
provenance, on discharges nobody curated for the purpose.

Reaching BES at all is most of the difficulty: the `bes` MDSplus tree holds no
waveforms, the 64 channels live in a different data source under names the tree
encodes as a template, and which of them sit at the pedestal changes between
shots. In seven plain-English questions and no code, ARGUS locates the data,
picks the edge channels, filters to the band, averages over every labelled ELM,
quantifies the result, rebuilds the analysis with a strictly causal estimator to
show the method did not manufacture its own answer, and states what the result
cannot support.

The last two questions are the ones worth reading. Asked whether its power
estimate might be using data from after the point it reports, the agent measured
the original estimator's look-ahead by impulse injection — 0.30 ms on one
deployment and 0.32 ms on the other, arrived at independently — and redid the
analysis causally. Over the two runs it also retracted a figure it had already
reported, replaced a statistic after showing a few loud events dominated it, and
walked one of its own claims back to p = 0.09.

The two deployments were asked byte-identical questions and did not return the
same study. Both find no systematic precursor in the ensemble average. One then
bounds what its design could have detected at all; the other runs a per-ELM
census and finds an intermittent rise on roughly a tenth of ELMs, significant
against a false-alarm null. Neither is a correction of the other, and the
divergence is legible only because the questions were identical.

[![JupyterHub notebook](https://raw.githubusercontent.com/klinucsd/argus_feder/main/assets/jupyterhub-badge.svg)](examples/jupyterhub/argus_feder_bes_elm_precursor_jupyterhub.ipynb)
[![Open in Colab](https://raw.githubusercontent.com/klinucsd/argus_feder/main/assets/colab-badge.svg)](https://colab.research.google.com/github/klinucsd/argus_feder/blob/main/examples/colab/argus_feder_bes_elm_precursor_colab.ipynb)

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
kaiucsd/argus-feder:0.1.5
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

# ARGUS-FEDER

Ask questions about DIII-D fusion data in plain English, on JupyterHub using
the prebuilt image.

## Quick start

Pick a notebook from [Examples](#examples) below and open it on JupyterHub
with the `kaiucsd/argus-feder` image, then run the cells in order. You'll
need:
- An API key for any supported LLM provider (NRP, OpenAI, Anthropic, ...)
- A DIII-D Pelican access token

Instructions for supplying both are in the notebook.

## Examples

Each example comes in two forms. The **JupyterHub** notebook is the source: it
assumes ARGUS, TokSearch and the DIII-D skills are already installed, as they
are in the `kaiucsd/argus-feder` image. The **Colab** variant is the same
notebook plus an install bootstrap, so a recipient can just hit *Run all*.

> **Colab is temporarily unavailable.** Google Colab moved its runtime to Python 3.13, and
> the `ga-fdp` conda channel has no Python 3.13 build of TokSearch yet, so the install step
> fails. The Colab links are commented out until a build is published. The **JupyterHub**
> notebooks below are unaffected and run normally.

Both variants ask byte-for-byte identical `%%ask` questions, so the two
environments can be compared directly. Both are saved with their real outputs
— you can read what ARGUS answered without running anything.

---

## Data access and terminology

Getting at DIII-D data, and mapping between naming conventions.

### Pelican data access, metadata, and PTDATA

ARGUS answering plain-English questions about DIII-D through four different
access paths: resolving a physics concept to the right MDSplus signal with no
symbol name given, querying the shot-metadata database, fetching from PTDATA
(a separate raw-digitizer source), and looking up signal meanings, MDSplus
paths and IMAS names.

[![JupyterHub notebook](https://raw.githubusercontent.com/klinucsd/argus_feder/main/assets/jupyterhub-badge.svg)](examples/jupyterhub/argus_feder_pelican_database_ptdata_jupyterhub.ipynb)
<!-- COLAB TEMPORARILY DISABLED [![Open in Colab](https://raw.githubusercontent.com/klinucsd/argus_feder/main/assets/colab-badge.svg)](https://colab.research.google.com/github/klinucsd/argus_feder/blob/main/examples/colab/argus_feder_pelican_database_ptdata_colab.ipynb) -->

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
<!-- COLAB TEMPORARILY DISABLED [![Open in Colab](https://raw.githubusercontent.com/klinucsd/argus_feder/main/assets/colab-badge.svg)](https://colab.research.google.com/github/klinucsd/argus_feder/blob/main/examples/colab/argus_feder_imas_d3d_colab.ipynb) -->

---

## ELM studies

Working from a stored index of ELM labels, from competency questions to reproducing a published result.

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
<!-- COLAB TEMPORARILY DISABLED [![Open in Colab](https://raw.githubusercontent.com/klinucsd/argus_feder/main/assets/colab-badge.svg)](https://colab.research.google.com/github/klinucsd/argus_feder/blob/main/examples/colab/argus_feder_elm_index_colab.ipynb) -->

### Sorting measurements by where they fall in the ELM cycle

An analysis rather than a question: ARGUS uses stored ELM event times to sort
Thomson scattering measurements by where they fall in the ELM cycle, then shows
what an average over everything hides. Thomson samples on its own clock — a few
times faster than the ELMs, but unsynchronised with them — so each profile
lands at an arbitrary point in the cycle, and the naive average blends
crash-phase and recovered plasma into a state the discharge never holds. The
notebook picks a suitable discharge from the stored labels, checks the event
times against a domain expert's before trusting them, and reports where in the
plasma the ELM actually reaches.

[![JupyterHub notebook](https://raw.githubusercontent.com/klinucsd/argus_feder/main/assets/jupyterhub-badge.svg)](examples/jupyterhub/argus_feder_elm_phase_analysis_jupyterhub.ipynb)
<!-- COLAB TEMPORARILY DISABLED [![Open in Colab](https://raw.githubusercontent.com/klinucsd/argus_feder/main/assets/colab-badge.svg)](https://colab.research.google.com/github/klinucsd/argus_feder/blob/main/examples/colab/argus_feder_elm_phase_analysis_colab.ipynb) -->

### Building a training cohort for a published ELM-forecasting study

A research task set by someone else.
[Teo et al. (2026)](https://arxiv.org/abs/2604.06508) train a neural network
to forecast the first ELM after the L-H transition, and state their own
principal limitation twice: the dataset is too small to quantify performance, and
identifying which discharges are relevant for training is a necessary next step.
They used 26 discharges. In six plain-English questions and no code, ARGUS
establishes what labels exist and who produced them, characterises the
distribution of first-ELM times, assembles a candidate cohort of 4,869
discharges, interrogates an anomaly in its own data, grounds one case in the raw
D-alpha signal, and states what the cohort cannot support — including that it
cannot reproduce the original study, because nothing in the data locates the
L-H transition.

[![JupyterHub notebook](https://raw.githubusercontent.com/klinucsd/argus_feder/main/assets/jupyterhub-badge.svg)](examples/jupyterhub/argus_feder_elm_forecast_cohort_jupyterhub.ipynb)
<!-- COLAB TEMPORARILY DISABLED [![Open in Colab](https://raw.githubusercontent.com/klinucsd/argus_feder/main/assets/colab-badge.svg)](https://colab.research.google.com/github/klinucsd/argus_feder/blob/main/examples/colab/argus_feder_elm_forecast_cohort_colab.ipynb) -->

### Testing a published claim: do turbulence precursors precede an ELM?

A complete study rather than a query. Joung et al. (*Nucl. Fusion* **64**,
066038, 2024) report that pedestal turbulence in the 15–150 kHz band rises
before an ELM crash. That is a measurement, so it can be tested directly. In
seven plain-English questions and no code, ARGUS finds the BES waveforms — the
`bes` MDSplus tree holds none, and the 64 channels live in another source under
a templated name — picks the edge channels, filters to the band, averages over
every labelled ELM, and states what the result cannot support.

The last two questions are the ones worth reading. Asked whether its estimate
might be using data from after the point it reports, the agent measured its own
look-ahead by impulse injection — 0.30 ms on one deployment, 0.32 ms on the
other, arrived at independently — and redid the analysis causally. Both
deployments find no systematic precursor in the ensemble average; one then
bounds what its design could have detected at all, the other finds an
intermittent rise on about a tenth of ELMs against a false-alarm null.

[![JupyterHub notebook](https://raw.githubusercontent.com/klinucsd/argus_feder/main/assets/jupyterhub-badge.svg)](examples/jupyterhub/argus_feder_bes_elm_precursor_jupyterhub.ipynb)
<!-- COLAB TEMPORARILY DISABLED [![Open in Colab](https://raw.githubusercontent.com/klinucsd/argus_feder/main/assets/colab-badge.svg)](https://colab.research.google.com/github/klinucsd/argus_feder/blob/main/examples/colab/argus_feder_bes_elm_precursor_colab.ipynb) -->

---

## Disruption studies

Working from stored disruption indexes — DIII-D and Alcator C-Mod — from an
introduction through competency questions to a research pass, and a
reproduction of a published figure. The index files these notebooks read are
provided separately rather than held in this repo.

### Getting started with DIII-D disruption data

A disruption is a sudden, uncontrolled collapse of the plasma current —
tolerable on a research device, damaging on a power plant, and predicting one
early enough to act is an open problem. This notebook introduces a stored index
of twenty DIII-D shots (ten that disrupted, ten that did not) run through
[disruption-py](https://github.com/MIT-PSFC/disruption-py), the MIT-PSFC
disruption-warning code, with every signal fetched over the Fusion Data
Platform. Eight plain-English questions cover what the data contains, what each
of the 63 parameters means and in what units, what a disruption looks like in
the traces, and how disrupted and non-disrupted shots differ.

The last two questions are about limits rather than results. The source files
carry **no units and no descriptions on any variable**, so the meaning of a
column lives in the index rather than the data; and three parameters return
plausible but wrong values, which the skill blocks rather than warns about. A
question asking what fraction of DIII-D shots disrupt is answered by declining:
twenty shots balanced ten and ten is a constructed slice, not a sample.

[![JupyterHub notebook](https://raw.githubusercontent.com/klinucsd/argus_feder/main/assets/jupyterhub-badge.svg)](examples/jupyterhub/argus_feder_disruption_basics_jupyterhub.ipynb)
<!-- COLAB TEMPORARILY DISABLED [![Open in Colab](https://raw.githubusercontent.com/klinucsd/argus_feder/main/assets/colab-badge.svg)](https://colab.research.google.com/github/klinucsd/argus_feder/blob/main/examples/colab/argus_feder_disruption_basics_colab.ipynb) -->

### Answering GA's disruption competency questions

General Atomics' competency-question set splits into an ELM half and a
disruption half; this works through the disruption half (Q14–Q27). Some
questions are answerable now — which pipeline produced a label and at what
commit, which quantities are disruption precursors and in what units, whether
the two disruption indicators agree. Some are answerable for one pipeline only,
because GA's questions assume three and we have run one. And a campaign
disruption rate is answered correctly by refusing: twenty shots balanced ten
and ten is a constructed slice, not a sample.

An Alcator C-Mod index has since been added, built by the same code, and it
moves the line. The discharge phase at each disruption — which DIII-D cannot
report, because a programmed current recorded in the wrong unit leaves the
column meant to answer it constant on every row — C-Mod resolves for all but
one of its disrupted shots. That same unit error turns out to be what makes two
identically named columns differ between the machines by a factor of a million.
Two further questions ask what the machines share, and the more interesting
answer is that their indexes disagree with themselves in opposite directions:
on one the indicators dispute whether a shot disrupted, on the other whether
the data exist. A second device is not a second pipeline, though — both indexes
come from one release of one code, so agreement between them is evidence about
the code rather than about the plasma.

[![JupyterHub notebook](https://raw.githubusercontent.com/klinucsd/argus_feder/main/assets/jupyterhub-badge.svg)](examples/jupyterhub/argus_feder_disruption_competency_jupyterhub.ipynb)
<!-- COLAB TEMPORARILY DISABLED [![Open in Colab](https://raw.githubusercontent.com/klinucsd/argus_feder/main/assets/colab-badge.svg)](https://colab.research.google.com/github/klinucsd/argus_feder/blob/main/examples/colab/argus_feder_disruption_competency_colab.ipynb) -->

### Disruption precursors: what a 20-shot slice can and cannot show

A research pass over the same disruption index, at the level of questions that
decide whether a prediction study is worth building on this data: when precursors
become visible before the current quench, which signals actually discriminate
disrupted from non-disrupted shots, whether the locked mode is a multi-second
warning or a final-100 ms event, and what an alarm threshold would cost in false
alarms.

Several answers are negative, and the notebook reports them as such: no parameter
separates the two classes at p < 0.05 with ten shots per class, and the largest
AUCs belong to parameters that are statistically pure noise. It also separates the
apparent discriminators that are real physics from those that are artifacts of how
the disruption label is defined.

[![JupyterHub notebook](https://raw.githubusercontent.com/klinucsd/argus_feder/main/assets/jupyterhub-badge.svg)](examples/jupyterhub/argus_feder_disruption_research_jupyterhub.ipynb)

### Loop voltage before a disruption, in Alcator C-Mod

A disrupting plasma cools before it loses its current, and the loop voltage is
where the rising resistance shows up. Figure 1 of Montes et al, *Nuclear Fusion*
**59** 096015 (2019) puts that on one panel: loop voltage over the final 250 ms
before the current quench, for C-Mod shots that disrupted out of flat-top,
against the flat-top voltage of shots that did not. This notebook rebuilds it
from a stored C-Mod index, produced by the same MIT-PSFC code as the DIII-D one.
C-Mod ran its current in both directions, so each shot's voltage has to be signed
by its own current first — thirty-five of the ninety-four ran reversed.

The second question is about limits. The pre-quench shift is modest, the large
jump in the final milliseconds is the current already collapsing rather than a
warning of it, and the index holds the shots its provider published times for,
so nothing here describes how often C-Mod disrupts.

[![JupyterHub notebook](https://raw.githubusercontent.com/klinucsd/argus_feder/main/assets/jupyterhub-badge.svg)](examples/jupyterhub/argus_feder_cmod_vloop_disruption_jupyterhub.ipynb)

## Plasma-facing materials

### Tungsten in the divertor: what the plasma did to it

Tungsten armours the DIII-D divertor and is the leading candidate for ITER. Helium
restructures its surface and deuterium implants into it, so whether the first
changes the second is a reactor safety question. Samples pre-exposed to helium in a
linear device, and others not, were mounted on DiMES through real DIII-D discharges
and analysed afterwards. The notebook works across the sample record and the
discharge archive together, joined by the shot numbers each exposure carries.

Several questions rebuild a recorded condition from the raw measurements behind it —
temperature at the sample, heat flux from the infrared exports, the camera's intra-
to inter-ELM brightness ratio from the archive's D-alpha filterscope — and two
reproduce the record only under a restriction that has to be found first. Where the
sample record and the ELM index disagree about a campaign's confinement regime, the
notebook settles it from the traces, and the closing question separates what the
record establishes from what it only suggests.

[![JupyterHub notebook](https://raw.githubusercontent.com/klinucsd/argus_feder/main/assets/jupyterhub-badge.svg)](examples/jupyterhub/argus_feder_materials_d3d_jupyterhub.ipynb)

### Where the deuterium sits: a carbon film, or the tungsten?

Retained fuel is the number a reactor designer cares about, and the samples did not
come back as clean tungsten — DIII-D's walls carry carbon, and it deposits on
whatever is exposed. Deuterium held in a carbon film behaves nothing like deuterium
trapped in tungsten, so the same measured inventory means two different things
depending on where it sits. Five questions test whether the delivery can tell.

The answer is partly negative and the notebook says so: the deep band is settled as
tungsten-resident, the other three-quarters is pinned only to "above half a micron",
and the closing question works out the depth resolution a measurement would need to
close the gap — about a hundred times finer than anything in the delivery.

[![JupyterHub notebook](https://raw.githubusercontent.com/klinucsd/argus_feder/main/assets/jupyterhub-badge.svg)](examples/jupyterhub/argus_feder_materials_carbon_jupyterhub.ipynb)

### Does a helium bubble layer change how tungsten survives a tokamak?

A burning plasma makes helium, so the tungsten facing one is tungsten with a bubble
layer already in it. Coupons pre-exposed to helium in a linear device were mounted on
DiMES beside coupons that were not, and all of them saw the same DIII-D discharges —
a design built to isolate what that layer does to erosion, morphology and fuel
retention. The notebook assembles the dataset and then tries to carry the comparison
out.

Two of its findings are structural rather than physical. The coupons that entered the
tokamak carry no imaging of their own, so the record of their initial surface runs
through a sibling implanted in the same run — a link in the experiment's design, not
in the sample table. And the helium-free controls do not come back helium-free, which
narrows the contrast the experiment was built around.

[![JupyterHub notebook](https://raw.githubusercontent.com/klinucsd/argus_feder/main/assets/jupyterhub-badge.svg)](examples/jupyterhub/argus_feder_materials_helium_jupyterhub.ipynb)

### Does helium in the surface make tungsten hold more deuterium, or less?

Whether a helium layer traps fuel or blocks it decides how much tritium a reactor
wall keeps, so the sign of the effect matters more than its size. The same coupon
set answers it, and the answer is not one number: helium at 800 K lowers retention
under an ELMy H-mode plasma and raises it under L-mode, while helium at 600 K
raises it under both.

Three further questions test how far that survives. The three techniques do not
measure the same quantity — they reach different depths and report in different
representations — so each is read on its own terms rather than pooled or ranked,
and where they diverge the divergence is itself the result: helium moves
deuterium toward the surface as much as it changes how much is held, so a
measurement integrating to a different depth returns a different number. The
coupons exposed in L-mode retained more deuterium than their H-mode counterparts
by both areal techniques, in every matched pair, though the two campaigns
differed in seven recorded conditions, so the effect belongs to the campaigns
rather than to confinement mode alone. The closing question asks what the set
collectively supports and what it cannot settle: with one coupon per condition
the differences belong to these coupons rather than to tungsten, and the coupon
temperature during exposure — the quantity the retention physics turns on — was
never measured.

[![JupyterHub notebook](https://raw.githubusercontent.com/klinucsd/argus_feder/main/assets/jupyterhub-badge.svg)](examples/jupyterhub/argus_feder_materials_he_effect_v4_jupyterhub.ipynb)
<!-- superseded, kept in the repo but unlinked: examples/jupyterhub/argus_feder_materials_he_effect_jupyterhub.ipynb, examples/jupyterhub/argus_feder_materials_he_effect_v2_jupyterhub.ipynb, examples/jupyterhub/argus_feder_materials_he_effect_v3_jupyterhub.ipynb -->

## Running on JupyterHub

The JupyterHub notebooks need no install step — use the prebuilt image:

```
kaiucsd/argus-feder:0.1.7
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

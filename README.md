# ARGUS-FEDER

Ask questions about DIII-D fusion data in plain English, running entirely on
Google Colab — no account or software install needed beyond a browser and an
LLM API key.

## Quick start

Open [`argus_feder_colab.ipynb`](argus_feder_colab.ipynb) in Colab and run
the cells in order. You'll need:
- An API key for any supported LLM provider (NRP, OpenAI, Anthropic, ...)
- A DIII-D Pelican access token

Both are added as Colab Secrets — instructions are in the notebook.

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

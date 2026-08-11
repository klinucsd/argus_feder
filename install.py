"""ARGUS-FEDER Colab installer.

Run AFTER the environment-preparation cell (condacolab) has already restarted
your session once. This installs, silently unless something goes wrong:
  1. DIII-D data access (TokSearch + Pelican)
  2. Your Pelican token, from the Colab Secret named FDP_TOKEN
  3. The ARGUS agent (%%ask)
  4. The DIII-D skills (fetch signals, look up shot metadata, query the
     stored ELM label index, phase-filter a diagnostic against ELM timing)

If anything fails, this prints a clear, specific message naming exactly
what's wrong -- no silent failures.
"""
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO_RAW = "https://raw.githubusercontent.com/klinucsd/argus_feder/main"


def _step(msg):
    print(f"  • {msg}")


def _run_with_heartbeat(cmd, heartbeat_secs=10):
    """Run cmd, printing a '.' roughly every heartbeat_secs so a slow step
    (mamba installs can take over a minute) never looks like it died."""
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    while proc.poll() is None:
        time.sleep(heartbeat_secs)
        print(".", end="", flush=True)
    print()
    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, cmd)


print("Setting up ARGUS-FEDER...")

# ---------------------------------------------------------------------------
# Step 1: DIII-D data access
# ---------------------------------------------------------------------------
try:
    import toksearch  # noqa: F401
except ImportError:
    try:
        subprocess.run(["mamba", "--version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        raise RuntimeError(
            "conda/mamba not found. Run the environment-preparation cell "
            "above FIRST (it restarts your session once) before running "
            "this cell."
        )
    _step("Installing DIII-D data access (~1-2 min, one-time)")
    # fdp installed as its OWN step, after toksearch/fdp-d3d: combining all three
    # in one `mamba install` non-deterministically keeps the old fdp-d3d wrapper
    # instead of the real fdp CLI. Verified 2026-08-01/02 -- keep this split.
    print("    ", end="", flush=True)
    _run_with_heartbeat(
        ["mamba", "install", "-y", "-q", "-c", "ga-fdp", "-c", "conda-forge",
         "toksearch", "fdp-d3d"]
    )
    print("    ", end="", flush=True)
    _run_with_heartbeat(
        ["mamba", "install", "-y", "-q", "-c", "ga-fdp", "-c", "conda-forge", "fdp"]
    )
_step("DIII-D data access ready")

# ---------------------------------------------------------------------------
# Step 2: Pelican token
# ---------------------------------------------------------------------------
try:
    from google.colab import userdata
    token = userdata.get("FDP_TOKEN")
except ImportError:
    token = os.environ.get("FDP_TOKEN")
except Exception:
    token = None

if not token:
    raise RuntimeError(
        "Pelican token not found. Add a Colab Secret named FDP_TOKEN "
        "(click the \U0001F511 icon in the left sidebar → 'Add new "
        "secret' → toggle 'Notebook access' on), then re-run this cell."
    )
os.environ["BEARER_TOKEN"] = token
Path("/root/.fdp").mkdir(exist_ok=True)
Path("/root/.fdp/token").write_text(token)
_step("Pelican token loaded")

# ---------------------------------------------------------------------------
# Step 3: ARGUS agent
# ---------------------------------------------------------------------------
_step("Installing the ARGUS agent (~1 min the first time)")
exec(
    urllib.request.urlopen(
        "https://raw.githubusercontent.com/klinucsd/sage/main/argus_colab/install.py"
    ).read().decode(),
    globals(),
)

# ---------------------------------------------------------------------------
# Step 4: DIII-D skills
# ---------------------------------------------------------------------------
skills_dir = Path.home() / ".deepagents" / "agent" / "skills"
for skill_name, files in {
    "d3d-shot-fetcher": ["SKILL.md"],
    "d3d-filterscopes": ["SKILL.md"],
    "d3d-relational-db": ["SKILL.md", "d3d_relational_db.py"],
    "signal-zoom": ["SKILL.md", "signal_zoom_colab.py"],
    "d3d-imas-terms": ["SKILL.md", "d3d_imas_terms.py", "imas_d3d_lookup.json"],
    "d3d-elm-index": ["SKILL.md", "d3d_elm_index.py"],
    "d3d-elm-phase-analysis": ["SKILL.md"],
}.items():
    dest = skills_dir / skill_name
    dest.mkdir(parents=True, exist_ok=True)
    for fname in files:
        content = urllib.request.urlopen(f"{REPO_RAW}/skills/{skill_name}/{fname}").read()
        (dest / fname).write_bytes(content)
_step("DIII-D skills installed")

print("\nARGUS-FEDER is ready. Ask a question in plain English with a %%ask cell.")

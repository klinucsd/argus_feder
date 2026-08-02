"""ARGUS-FEDER Colab installer.

Run AFTER the environment-preparation cell (condacolab) has already restarted
your session once. This installs, silently unless something goes wrong:
  1. DIII-D data access (TokSearch + Pelican)
  2. Your Pelican token, from the Colab Secret named FDP_TOKEN
  3. The ARGUS agent (%%ask)
  4. The DIII-D skills (fetch signals, look up shot metadata)

If anything fails, this prints a clear, specific message naming exactly
what's wrong -- no silent failures.
"""
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

REPO_RAW = "https://raw.githubusercontent.com/klinucsd/argus_feder/main"


def _step(msg):
    print(f"  • {msg}")


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
    _step("Installing DIII-D data access (~1-2 min, one-time)...")
    # fdp installed as its OWN step, after toksearch/fdp-d3d: combining all three
    # in one `mamba install` non-deterministically keeps the old fdp-d3d wrapper
    # instead of the real fdp CLI. Verified 2026-08-01/02 -- keep this split.
    subprocess.check_call(
        ["mamba", "install", "-y", "-q", "-c", "ga-fdp", "-c", "conda-forge",
         "toksearch", "fdp-d3d"],
        stdout=subprocess.DEVNULL,
    )
    subprocess.check_call(
        ["mamba", "install", "-y", "-q", "-c", "ga-fdp", "-c", "conda-forge", "fdp"],
        stdout=subprocess.DEVNULL,
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
_step("Installing the ARGUS agent...")
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
    "d3d-relational-db": ["SKILL.md", "d3d_relational_db.py"],
}.items():
    dest = skills_dir / skill_name
    dest.mkdir(parents=True, exist_ok=True)
    for fname in files:
        content = urllib.request.urlopen(f"{REPO_RAW}/skills/{skill_name}/{fname}").read()
        (dest / fname).write_bytes(content)
_step("DIII-D skills installed")

print("\nARGUS-FEDER is ready. Ask a question in plain English with a %%ask cell.")

# %% [markdown]
# # Stage 0–2, interactively
#
# A plain `.py` file with `# %%` cell markers. VS Code runs it cell-by-cell in
# the Interactive Window (Shift+Enter), exactly like a notebook — but it is
# plain text, so git diffs are readable, nothing is stored in the file, and a
# cell that prints a token cannot leak it into the repository.
#
# Run from the repository root. Select the `.venv` interpreter first:
# Ctrl+Shift+P → "Python: Select Interpreter".

# %%
import os
import sys
from pathlib import Path

ROOT = Path.cwd()
if ROOT.name == "notebooks":
    ROOT = ROOT.parent
    os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
print("working from:", ROOT)

# %% [markdown]
# ## Checkpoint 0 — token loads, and is not in git

# %%
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("ENTSOE_TOKEN")
print("token loaded:", bool(token), "| length:", len(token or ""))
assert token, "paste the token into .env — see RUNBOOK Pre-flight"

# %% [markdown]
# ## Stage 1 — one pull, one zone, one year
#
# DE-LU, 2025. The client stores the response as a new file in
# `raw/A75/<eic>/2025/` (or its `_failed/` folder when it is not data), never
# overwriting an earlier one, appends a row to `raw/manifest.csv`, hashes the
# body and redacts the token in the logged URL.

# %%
from src.ingest.entsoe_client import generation_per_type

row = generation_per_type("10Y1001A1001A82H", 2025, token)
row

# %% [markdown]
# ### Checkpoint 1
# Accepted (status 200, rejected 0) · the stored file is over 1 MB · the token
# appears nowhere in the manifest · a second pull returns the same data.

# %%
assert not row["rejected"], (
    f"NOT ACCEPTED — HTTP {row['http_status']}. The response is kept at "
    f"{row['path']}: open it, it states why."
)
xml_path = ROOT / row["path"]          # raw/A75/<eic>/2025/<retrieved>_<sha8>.xml
size_mb = xml_path.stat().st_size / 1_048_576
print(f"{xml_path.name}: {size_mb:.2f} MB", "OK" if size_mb > 1 else "TOO SMALL — open the XML and look")

# Search for the token itself. The old check demanded ***REDACTED*** in every
# row, and SMARD rows carry no token to redact, so it halted on a false alarm.
manifest_text = (ROOT / "raw" / "manifest.csv").read_text(encoding="utf-8")
assert token not in manifest_text, "TOKEN IN MANIFEST — stop and fix before committing"
print("token absent from the manifest | revision:", row["revision"] or "not stated")

# %% [markdown]
# Re-run the pull. A closed historical year should return the same DATA, but
# the file hash cannot show that: every response carries a fresh mRID and
# createdDateTime, so identical data hashes differently (README, "What the
# manifest hash does and does not tell you"). raw/ keeps both retrievals, so
# compare them on disk from the first TimeSeries onward.

# %%
row2 = generation_per_type("10Y1001A1001A82H", 2025, token)
assert not row2["rejected"], f"second pull NOT ACCEPTED — HTTP {row2['http_status']}"
a = xml_path.read_bytes()
b = (ROOT / row2["path"]).read_bytes()
same = a.split(b"<TimeSeries>", 1)[-1] == b.split(b"<TimeSeries>", 1)[-1]
print("same data in both pulls:", same, "| revisions:", row["revision"], row2["revision"])

# %% [markdown]
# ## Stage 2 — parse, and check the two traps

# %%
from src.transform.entsoe_parse import parse
from src.checks.validate import check_stage2_parse, check_stage2_direction

parsed = parse(xml_path.read_text(encoding="utf-8"))
print("rows parsed:", len(parsed))
print(check_stage2_parse(parsed))
print(check_stage2_direction(parsed))

# %% [markdown]
# Sanity on magnitude: one day of DE-LU generation should land in the low
# millions of MWh. Orders of magnitude out means a MAW→MWh units error.

# %%
from collections import defaultdict

by_day = defaultdict(float)
for r in parsed:
    if r["direction"] == "generation":
        by_day[str(r["ts_utc"])[:10]] += r["mwh"]
sample = sorted(by_day.items())[:3]
for d, v in sample:
    print(d, f"{v:,.0f} MWh")

# %% [markdown]
# ## Checkpoint 2, by hand
# Pick an A03 series with few stated points and confirm the value carries
# forward until the next stated one. This is the trap a naive parser fails
# silently, so look at it once with your own eyes.

# %%
psr_counts = defaultdict(int)
for r in parsed:
    psr_counts[r["psr"]] += 1
for psr, n in sorted(psr_counts.items(), key=lambda kv: kv[1])[:5]:
    print(psr, n, "rows")

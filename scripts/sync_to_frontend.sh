#!/usr/bin/env bash
# sync_to_frontend.sh
#
# Copies pre-computed pipeline artifacts from the Python repo's exporter
# output directory into the React dashboard repo's public/data/.
#
# Pre-condition: the exporter must already have run. This script does NOT
# regenerate data. Run `python scripts/export_dashboard_data.py` first.
#
# Policy:
#   - Overwrites destination files without confirmation (build-artifact pipeline).
#   - Does NOT auto-commit in the React repo — staging/commit is manual.
#   - Exits non-zero if any expected source file or the waveforms/ dir is missing.
#
# Note: markdown rendering on the React side (Day 4) will use
#   react-markdown + remark-gfm. Do not install those packages here.

set -euo pipefail

SRC_DIR="/Users/Sterdb/spo2-eval-pipeline/data/export"
DST_DIR="/Users/Sterdb/pm-private/spo2-eval-dashboard/public/data"

JSON_FILES=(
  "pipeline-summary.json"
  "coverage-breakdown.json"
  "eval-scores.json"
  "handoffs-samples.json"
  "hl7-messages.json"
  "rules-discovered.json"
  "traces-meta.json"
)

WAVEFORMS_SUBDIR="waveforms"

# --- Pre-flight checks --------------------------------------------------

if [[ ! -d "$SRC_DIR" ]]; then
  echo "ERROR: source directory not found: $SRC_DIR" >&2
  echo "Run 'python scripts/export_dashboard_data.py' first." >&2
  exit 1
fi

if [[ ! -d "$DST_DIR" ]]; then
  echo "ERROR: destination directory not found: $DST_DIR" >&2
  exit 1
fi

missing=()
for f in "${JSON_FILES[@]}"; do
  [[ -f "$SRC_DIR/$f" ]] || missing+=("$f")
done
if [[ ! -d "$SRC_DIR/$WAVEFORMS_SUBDIR" ]]; then
  missing+=("$WAVEFORMS_SUBDIR/")
fi

if (( ${#missing[@]} > 0 )); then
  echo "ERROR: missing in $SRC_DIR:" >&2
  for m in "${missing[@]}"; do echo "  - $m" >&2; done
  exit 1
fi

# --- Copy JSON files ----------------------------------------------------

echo "Syncing $SRC_DIR -> $DST_DIR"
echo ""
echo "JSON files:"
for f in "${JSON_FILES[@]}"; do
  cp -f "$SRC_DIR/$f" "$DST_DIR/$f"
  size=$(wc -c < "$DST_DIR/$f" | tr -d ' ')
  printf "  %-30s %10s bytes\n" "$f" "$size"
done

# --- Copy waveforms directory ------------------------------------------

echo ""
echo "Waveforms:"
mkdir -p "$DST_DIR/$WAVEFORMS_SUBDIR"
# Remove stale waveforms first so deleted traces don't linger.
find "$DST_DIR/$WAVEFORMS_SUBDIR" -maxdepth 1 -type f -name '*.json' -delete

wf_count=0
wf_bytes=0
for src in "$SRC_DIR/$WAVEFORMS_SUBDIR"/*.json; do
  [[ -f "$src" ]] || continue
  cp -f "$src" "$DST_DIR/$WAVEFORMS_SUBDIR/"
  wf_count=$(( wf_count + 1 ))
  wf_bytes=$(( wf_bytes + $(wc -c < "$src" | tr -d ' ') ))
done
printf "  %d files, %d bytes total\n" "$wf_count" "$wf_bytes"

echo ""
echo "Done. Review with: git -C $(dirname "$DST_DIR")/.. status"

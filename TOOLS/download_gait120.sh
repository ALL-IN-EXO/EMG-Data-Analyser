#!/usr/bin/env bash
# =============================================================================
# download_gait120.sh
#
# Download the Gait120 comprehensive human locomotion & EMG dataset from
# Springer Nature Figshare and extract subjects into a single merged directory.
#
#   Article  : https://springernature.figshare.com/articles/dataset/
#              Comprehensive_Human_Locomotion_and_Electromyography_Dataset_Gait120/27677016
#   API ID   : 27677016
#
#   10 packs shipped, each covering 10 subjects (S001–S100 total):
#     Pack 1   Gait120_001_to_010.zip   S001–S010   ~1.45 GB compressed
#     Pack 2   Gait120_011_to_020.zip   S011–S020   ~1.42 GB
#     Pack 3   Gait120_021_to_030.zip   S021–S030   ~1.37 GB
#     Pack 4   Gait120_031_to_040.zip   S031–S040   ~1.37 GB
#     Pack 5   Gait120_041_to_050.zip   S041–S050   ~1.35 GB
#     Pack 6   Gait120_051_to_060.zip   S051–S060   ~1.34 GB
#     Pack 7   Gait120_061_to_070.zip   S061–S070   ~1.42 GB
#     Pack 8   Gait120_071_to_080.zip   S071–S080   ~1.35 GB
#     Pack 9   Gait120_081_to_090.zip   S081–S090   ~1.38 GB
#     Pack 10  Gait120_091_to_100.zip   S091–S100   ~1.41 GB
#
#   After extraction every SXxx/ folder is merged into a single flat directory:
#     <dest>/S001/  <dest>/S002/  …  <dest>/S100/
#
# Works on:
#   * Ubuntu / Debian / Fedora (bash)
#   * macOS (system bash 3.2 or brew bash)
#   * Windows via Git Bash, MSYS2, or WSL
#
# Requirements:
#   * bash >= 3.2
#   * curl  (preferred) OR wget
#   * unzip
#   * python3   (no extra pip packages — only used to parse JSON)
#
# Usage:
#   ./download_gait120.sh                          # all packs → ../Dataset/Gait120
#   ./download_gait120.sh --dest /data/Gait120
#   ./download_gait120.sh --packs 1                # only pack 1 (S001–S010)
#   ./download_gait120.sh --packs 1,2,3            # packs 1-3 (S001–S030)
#   ./download_gait120.sh --keep-zips              # don't delete ZIPs after extract
#   ./download_gait120.sh --list-only              # dry-run: show file list, no download
# =============================================================================

set -euo pipefail

# ---------- defaults ---------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_DEST="${SCRIPT_DIR}/../Dataset/Gait120"

DEST=""
PACKS_FILTER="all"
KEEP_ZIPS=0
LIST_ONLY=0

ARTICLE_ID="27677016"
API_BASE="https://api.figshare.com/v2/articles"

# ---------- CLI parsing ------------------------------------------------------

print_help() {
  sed -n '2,/^# ===/p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dest)       DEST="$2"; shift 2 ;;
    --dest=*)     DEST="${1#*=}"; shift ;;
    --packs)      PACKS_FILTER="$2"; shift 2 ;;
    --packs=*)    PACKS_FILTER="${1#*=}"; shift ;;
    --keep-zips)  KEEP_ZIPS=1; shift ;;
    --list-only)  LIST_ONLY=1; shift ;;
    -h|--help)    print_help; exit 0 ;;
    --)           shift; break ;;
    -*) echo "unknown flag: $1" >&2; exit 2 ;;
    *)  if [[ -z "$DEST" ]]; then DEST="$1"; shift
        else echo "unexpected argument: $1" >&2; exit 2
        fi ;;
  esac
done

DEST="${DEST:-$DEFAULT_DEST}"

# ---------- dependency checks ------------------------------------------------

need() {
  command -v "$1" >/dev/null 2>&1 \
    || { echo "error: '$1' not found in PATH." >&2; return 1; }
}

if command -v curl >/dev/null 2>&1; then
  DL=curl
elif command -v wget >/dev/null 2>&1; then
  DL=wget
else
  echo "error: need 'curl' or 'wget' to download." >&2
  exit 1
fi
need unzip   || exit 1
need python3 || exit 1

# ---------- platform helpers -------------------------------------------------

abspath() {
  local p="$1"
  if [[ -d "$p" ]]; then (cd "$p" && pwd)
  else local d; d="$(cd "$(dirname "$p")" && pwd)"; echo "$d/$(basename "$p")"
  fi
}

hr_size() {
  local b="$1"
  awk -v b="$b" 'BEGIN {
    split("B KB MB GB TB", u); s=1
    while (b>=1024 && s<5) { b/=1024; s++ }
    printf "%.1f %s", b, u[s]
  }'
}

fetch() {
  local url="$1" out="$2"
  if [[ "$DL" == curl ]]; then
    curl -fL --retry 5 --retry-delay 3 --continue-at - \
         --progress-bar -o "$out" "$url"
  else
    wget -c --tries=5 --waitretry=3 --show-progress -q -O "$out" "$url"
  fi
}

fetch_stdout() {
  local url="$1"
  if [[ "$DL" == curl ]]; then
    curl -fsSL --retry 5 --retry-delay 3 "$url"
  else
    wget -q --tries=5 --waitretry=3 -O - "$url"
  fi
}

# ---------- pack filter ------------------------------------------------------

# Given a filename like "Gait120_031_to_040.zip", extract the pack number (4).
filename_to_pack_num() {
  local fname="$1"                    # e.g. Gait120_031_to_040.zip
  local start                         # e.g. 031
  start="$(echo "$fname" | sed -n 's/.*Gait120_\([0-9]\{3\}\)_to_[0-9]\{3\}\.zip/\1/p')"
  if [[ -z "$start" ]]; then echo 0; return; fi
  # strip leading zeros → decimal
  echo $(( 10#$start / 10 + 1 ))
}

pack_is_wanted() {
  local num="$1"
  [[ "$PACKS_FILTER" == "all" ]] && return 0
  case ",${PACKS_FILTER}," in *",${num},"*) return 0 ;; esac
  return 1
}

# ---------- main -------------------------------------------------------------

mkdir -p "$DEST"
DEST="$(abspath "$DEST")"
DL_DIR="${DEST}/_downloads"
mkdir -p "$DL_DIR"

echo "Destination : $DEST"
echo "Cache dir   : $DL_DIR"
echo "Downloader  : $DL"
echo "Packs       : $PACKS_FILTER"
[[ $LIST_ONLY -eq 1 ]] && echo "MODE        : list-only (no download)"
echo

# Fetch file list from Figshare API
META_JSON="${DL_DIR}/figshare_files.json"
echo "Fetching file list from Figshare API (article ${ARTICLE_ID})..."
fetch_stdout "${API_BASE}/${ARTICLE_ID}/files" > "$META_JSON"

# Parse JSON → TSV: filename \t size \t download_url
TSV="$(python3 - "$META_JSON" <<'PY'
import json, sys
with open(sys.argv[1], "r", encoding="utf-8") as f:
    data = json.load(f)
for item in data:
    name = item.get("name") or item.get("filename") or ""
    size = item.get("size") or 0
    dl   = item.get("download_url") or ""
    if name and dl:
        print(f"{name}\t{size}\t{dl}")
PY
)"

if [[ -z "$TSV" ]]; then
  echo "error: Figshare file list is empty. Inspect $META_JSON" >&2
  exit 1
fi

echo "Files in article ${ARTICLE_ID}:"
echo

TOTAL_BYTES=0

while IFS=$'\t' read -r fname fsize furl; do
  [[ -z "$fname" ]] && continue

  pack_num="$(filename_to_pack_num "$fname")"
  if ! pack_is_wanted "$pack_num"; then
    printf "  [skip]  %-35s (pack %2d, excluded by --packs)\n" "$fname" "$pack_num"
    continue
  fi

  TOTAL_BYTES=$(( TOTAL_BYTES + fsize ))
  out="${DL_DIR}/${fname}"

  if [[ $LIST_ONLY -eq 1 ]]; then
    printf "  [list]  %-35s  pack %2d  %s\n" "$fname" "$pack_num" "$(hr_size "$fsize")"
    continue
  fi

  # Resume or skip
  if [[ -f "$out" ]]; then
    have=$(stat -c%s "$out" 2>/dev/null || stat -f%z "$out" 2>/dev/null || echo 0)
    if [[ "$have" == "$fsize" && "$fsize" != "0" ]]; then
      printf "  [skip]  %-35s (%s, already complete)\n" "$fname" "$(hr_size "$fsize")"
      continue
    fi
    printf "  [resume]%-35s (%s / %s)\n" "$fname" "$(hr_size "$have")" "$(hr_size "$fsize")"
  else
    printf "  [get]   %-35s (%s)\n" "$fname" "$(hr_size "$fsize")"
  fi

  fetch "$furl" "$out"
done <<< "$TSV"

echo
[[ $LIST_ONLY -eq 1 ]] && {
  echo "Total announced: $(hr_size "$TOTAL_BYTES")"
  echo "list-only mode — stopping before extraction."
  exit 0
}

echo "Total download size: $(hr_size "$TOTAL_BYTES")"
echo

# ---------- extract & merge --------------------------------------------------

echo "==[ extract & merge ]==========================================="
echo

for zpath in "$DL_DIR"/Gait120_*.zip; do
  [[ -e "$zpath" ]] || continue
  base="$(basename "$zpath")"           # e.g. Gait120_001_to_010.zip
  stem="${base%.zip}"                   # Gait120_001_to_010

  pack_num="$(filename_to_pack_num "$base")"
  pack_is_wanted "$pack_num" || continue

  # Extract into a temp staging area
  stage="${DL_DIR}/_stage_${stem}"

  # Check if subjects from this pack are already extracted in DEST
  # Determine the subject range from the filename (e.g. 001_to_010 → S001…S010)
  range_start="$(echo "$stem" | sed -n 's/Gait120_\([0-9]\{3\}\)_to_[0-9]\{3\}/\1/p')"
  range_end="$(echo "$stem"   | sed -n 's/Gait120_[0-9]\{3\}_to_\([0-9]\{3\}\)/\1/p')"
  first_subj="S${range_start}"

  if [[ -d "${DEST}/${first_subj}" && -n "$(ls -A "${DEST}/${first_subj}" 2>/dev/null || true)" ]]; then
    echo "  [skip]  ${stem} — ${first_subj} already present in destination."
    continue
  fi

  echo "  [unzip] ${base} → staging ..."
  rm -rf "$stage"
  mkdir -p "$stage"
  unzip -q -o "$zpath" -d "$stage"

  # Locate the subjects: the ZIP may extract into Gait120_xxx_to_xxx/ or directly
  src_dir="$stage"
  if [[ -d "${stage}/${stem}" ]]; then
    src_dir="${stage}/${stem}"
  fi

  echo "  [merge] S${range_start}–S${range_end} → ${DEST}/"
  for subj_dir in "${src_dir}"/S*/; do
    [[ -d "$subj_dir" ]] || continue
    subj="$(basename "$subj_dir")"
    if [[ -d "${DEST}/${subj}" && -n "$(ls -A "${DEST}/${subj}" 2>/dev/null || true)" ]]; then
      echo "    [skip] ${subj} already present"
    else
      cp -r "$subj_dir" "${DEST}/${subj}"
      echo "    [ok]   ${subj}"
    fi
  done

  rm -rf "$stage"
done

# ---------- cleanup ----------------------------------------------------------

if [[ $KEEP_ZIPS -eq 0 ]]; then
  echo
  echo "Removing cached ZIPs under ${DL_DIR} (use --keep-zips to preserve)..."
  find "$DL_DIR" -maxdepth 1 -type f -name 'Gait120_*.zip' -delete
  rm -f "${DL_DIR}/figshare_files.json"
  rmdir "$DL_DIR" 2>/dev/null || true
fi

# ---------- summary ----------------------------------------------------------

echo
echo "Done. Merged dataset layout:"
echo "  ${DEST}/"
find "$DEST" -mindepth 1 -maxdepth 1 | sort | sed 's|^|    |'

n_subj=$(find "$DEST" -mindepth 1 -maxdepth 1 -type d -name 'S[0-9]*' | wc -l | tr -d ' ')
echo
echo "Subjects extracted: ${n_subj}"
echo "Tip: point the EMG analyser Page 4 to this directory."

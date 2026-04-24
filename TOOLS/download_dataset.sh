#!/usr/bin/env bash
# =============================================================================
# download_dataset.sh
#
# Download the Camargo 2021 lower-limb biomechanics / EMG dataset (3 parts)
# from Mendeley Data, extract every ABxx.zip, and merge all subjects into one
# flat directory.
#
#   Part 1/3  doi:10.17632/fcgm3chfff.1    AB06..AB14
#   Part 2/3  doi:10.17632/k9kvm5tn3f.1    AB15..AB23 (approx)
#   Part 3/3  doi:10.17632/jj3r5f9pnf.1    AB24..AB30 (approx)
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
#   * python3   (only used as a portable JSON parser — no extra pip packages)
#
# Usage:
#   ./download_dataset.sh                          # default dest: ../Dataset/Camargo2021
#   ./download_dataset.sh --dest /data/Camargo
#   ./download_dataset.sh --dest ./foo --parts 1,3 # only parts 1 and 3
#   ./download_dataset.sh --keep-zips              # keep raw ABxx.zip after extract
#   ./download_dataset.sh --list-only              # dry-run: print what would download
# =============================================================================

set -euo pipefail

# ---------- defaults ---------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_DEST="${SCRIPT_DIR}/../Dataset/Camargo2021"

DEST=""
PARTS_FILTER="1,2,3"
KEEP_ZIPS=0
LIST_ONLY=0

# Mendeley dataset IDs and version numbers.
#   format:  label|dataset_id|version
DATASETS=(
  "part1|fcgm3chfff|1"
  "part2|k9kvm5tn3f|1"
  "part3|jj3r5f9pnf|1"
)

API_BASE="https://data.mendeley.com/public-api/datasets"

# ---------- CLI parsing ------------------------------------------------------

print_help() {
  sed -n '2,/^# ===/p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dest)       DEST="$2"; shift 2 ;;
    --dest=*)     DEST="${1#*=}"; shift ;;
    --parts)      PARTS_FILTER="$2"; shift 2 ;;
    --parts=*)    PARTS_FILTER="${1#*=}"; shift ;;
    --keep-zips)  KEEP_ZIPS=1; shift ;;
    --list-only)  LIST_ONLY=1; shift ;;
    -h|--help)    print_help; exit 0 ;;
    --)           shift; break ;;
    -*) echo "unknown flag: $1" >&2; exit 2 ;;
    *)  if [[ -z "$DEST" ]]; then DEST="$1"; shift
        else echo "unexpected arg: $1" >&2; exit 2
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

# ---------- platform bits ----------------------------------------------------

# realpath replacement that works on macOS default bash
abspath() {
  local p="$1"
  if [[ -d "$p" ]]; then (cd "$p" && pwd); else
    local d; d="$(cd "$(dirname "$p")" && pwd)"; echo "$d/$(basename "$p")"
  fi
}

# human-readable size
hr_size() {
  local b="$1"
  awk -v b="$b" 'BEGIN {
    split("B KB MB GB TB", u);
    s=1; while (b>=1024 && s<5) { b/=1024; s++ }
    printf "%.1f %s", b, u[s];
  }'
}

# fetch a URL to a file with resume support
fetch() {
  local url="$1" out="$2"
  if [[ "$DL" == curl ]]; then
    curl -fL --retry 5 --retry-delay 3 --continue-at - \
         --progress-bar -o "$out" "$url"
  else
    wget -c --tries=5 --waitretry=3 --show-progress -q -O "$out" "$url"
  fi
}

# fetch a URL to stdout (for small JSON payloads)
fetch_stdout() {
  local url="$1"
  if [[ "$DL" == curl ]]; then
    curl -fsSL --retry 5 --retry-delay 3 "$url"
  else
    wget -q --tries=5 --waitretry=3 -O - "$url"
  fi
}

# ---------- parts filter -----------------------------------------------------

part_is_wanted() {
  local want="$1"                                 # "part1"
  local n="${want#part}"
  case ",${PARTS_FILTER}," in *",${n},"*) return 0 ;; esac
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
echo "Parts       : $PARTS_FILTER"
[[ $LIST_ONLY -eq 1 ]] && echo "MODE        : list-only (no download)"
echo

TOTAL_BYTES=0

for entry in "${DATASETS[@]}"; do
  IFS='|' read -r label ds_id version <<< "$entry"
  part_is_wanted "$label" || { echo "[$label] skipped by --parts filter."; continue; }

  echo "==[ $label  id=$ds_id  v=$version ]============================"
  list_url="${API_BASE}/${ds_id}/files?folder_id=root&version=${version}"
  meta_json="${DL_DIR}/${label}_files.json"

  echo "  listing files ..."
  fetch_stdout "$list_url" > "$meta_json"

  # Parse JSON into TSV:  filename \t size \t download_url
  tsv="$(python3 - "$meta_json" <<'PY'
import json, sys
with open(sys.argv[1], "r", encoding="utf-8") as f:
    data = json.load(f)
for item in data:
    name = item.get("filename") or item.get("name") or ""
    size = item.get("size") or (item.get("content_details") or {}).get("size") or 0
    dl   = item.get("download_url") \
        or (item.get("content_details") or {}).get("download_url") \
        or ""
    if name and dl:
        print(f"{name}\t{size}\t{dl}")
PY
)"

  if [[ -z "$tsv" ]]; then
    echo "  error: file list for $label is empty. Inspect $meta_json"
    exit 1
  fi

  # Loop lines
  while IFS=$'\t' read -r fname fsize furl; do
    [[ -z "$fname" ]] && continue
    TOTAL_BYTES=$(( TOTAL_BYTES + fsize ))
    out="${DL_DIR}/${label}__${fname}"

    if [[ $LIST_ONLY -eq 1 ]]; then
      printf "  [list] %-14s %s (%s)\n" "$label" "$fname" "$(hr_size "$fsize")"
      continue
    fi

    if [[ -f "$out" ]]; then
      have=$(stat -c%s "$out" 2>/dev/null || stat -f%z "$out" 2>/dev/null || echo 0)
      if [[ "$have" == "$fsize" && "$fsize" != "0" ]]; then
        printf "  [skip]  %-28s (%s, already downloaded)\n" "$fname" "$(hr_size "$fsize")"
        continue
      fi
      printf "  [resume]%-28s (%s / %s)\n" "$fname" \
             "$(hr_size "$have")" "$(hr_size "$fsize")"
    else
      printf "  [get]   %-28s (%s)\n" "$fname" "$(hr_size "$fsize")"
    fi

    fetch "$furl" "$out"
  done <<< "$tsv"
done

echo
echo "Total announced by Mendeley: $(hr_size "$TOTAL_BYTES")"
[[ $LIST_ONLY -eq 1 ]] && { echo "list-only mode: stopping before extract."; exit 0; }

# ---------- extract & merge --------------------------------------------------

echo
echo "==[ extract & merge ]==========================================="

EXTRACTED_ANY=0

for zpath in "$DL_DIR"/*.zip; do
  [[ -e "$zpath" ]] || continue
  base="$(basename "$zpath")"              # e.g. "part1__AB06.zip" or "part1__scripts.zip"
  label="${base%%__*}"                     # "part1"
  rest="${base#*__}"                       # "AB06.zip"
  stem="${rest%.zip}"                      # "AB06"

  case "$stem" in
    AB*)
      target="$DEST/$stem"
      if [[ -d "$target" && -n "$(ls -A "$target" 2>/dev/null || true)" ]]; then
        echo "  [skip]  $stem already extracted."
      else
        echo "  [unzip] $stem  ← $base"
        unzip -q -o "$zpath" -d "$DEST"
        # Some archives wrap contents in a nested ABxx/ABxx/ folder — flatten if so.
        if [[ -d "$target/$stem" && ! -e "$target/$stem/$stem" ]]; then
          # only flatten if target has exactly one child named ABxx and nothing else
          child_count=$(find "$target" -mindepth 1 -maxdepth 1 | wc -l | tr -d ' ')
          if [[ "$child_count" == "1" ]]; then
            tmp="${target}.__tmp__"
            mv "$target/$stem" "$tmp"
            rmdir "$target"
            mv "$tmp" "$target"
          fi
        fi
        EXTRACTED_ANY=1
      fi
      ;;
    scripts)
      tgt="$DEST/scripts_${label}"
      if [[ -d "$tgt" && -n "$(ls -A "$tgt" 2>/dev/null || true)" ]]; then
        echo "  [skip]  scripts ($label) already extracted."
      else
        echo "  [unzip] scripts ($label) → scripts_${label}/"
        mkdir -p "$tgt"
        unzip -q -o "$zpath" -d "$tgt"
        EXTRACTED_ANY=1
      fi
      ;;
    *)
      # unknown zip — extract into a labelled subfolder, don't pollute root
      tgt="$DEST/misc_${label}_${stem}"
      echo "  [unzip] $stem (misc) → $(basename "$tgt")/"
      mkdir -p "$tgt"
      unzip -q -o "$zpath" -d "$tgt"
      EXTRACTED_ANY=1
      ;;
  esac
done

# Copy non-zip artifacts (README.txt, SubjectInfo.mat) with part suffix.
for f in "$DL_DIR"/*; do
  [[ -f "$f" ]] || continue
  base="$(basename "$f")"
  case "$base" in *.zip|*_files.json) continue ;; esac
  label="${base%%__*}"
  rest="${base#*__}"
  stem="${rest%.*}"
  ext="${rest##*.}"
  # For README.txt from part1, install as README.txt; part2/3 get suffixed.
  if [[ "$rest" == "README.txt" ]]; then
    if [[ "$label" == "part1" ]]; then
      cp -f "$f" "$DEST/README.txt"
    else
      cp -f "$f" "$DEST/README_${label}.txt"
    fi
  else
    # Generic: preserve filename, suffix with part if collision.
    dst="$DEST/$rest"
    if [[ -e "$dst" ]]; then dst="$DEST/${stem}_${label}.${ext}"; fi
    cp -f "$f" "$dst"
  fi
done

# ---------- cleanup ----------------------------------------------------------

if [[ $KEEP_ZIPS -eq 0 ]]; then
  echo
  echo "Removing cached ZIPs under $DL_DIR (use --keep-zips to preserve)..."
  find "$DL_DIR" -maxdepth 1 -type f -name '*.zip' -delete
  # Drop the _downloads dir entirely if now empty except for file lists
  find "$DL_DIR" -maxdepth 1 -type f -name '*_files.json' -delete || true
  rmdir "$DL_DIR" 2>/dev/null || true
fi

# ---------- summary ----------------------------------------------------------

echo
echo "Done. Merged dataset layout:"
echo "  $DEST/"
find "$DEST" -mindepth 1 -maxdepth 1 -print | sort | sed 's|^|    |'

# Quick sanity count
n_subj=$(find "$DEST" -mindepth 1 -maxdepth 1 -type d -name 'AB*' | wc -l | tr -d ' ')
echo
echo "Subjects found: $n_subj"
echo "Tip: point the EMG analyser --root flag at this directory."

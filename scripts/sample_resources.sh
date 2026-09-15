#!/usr/bin/env bash
# Sample per-container CPU/memory and host available memory while a stress
# scenario runs, so the campaign can chart resource ceilings and so the
# operator (human or agent) has a live trail to check against the "abort if
# available memory drops too low" rule in the stress-testing policy.
#
# Usage: scripts/sample_resources.sh <project-name> <out-csv> <stop-file> [interval-seconds]
# Write anything to <stop-file> to end the loop on its next tick.
set -euo pipefail

project_name="${1:?project name required}"
out_csv="${2:?output csv path required}"
stop_file="${3:?stop file path required}"
interval="${4:-5}"

mkdir -p "$(dirname "$out_csv")"
echo "timestamp,available_memory_mb,container,cpu_percent,mem_usage,mem_percent" > "$out_csv"

while [[ ! -e "$stop_file" ]]; do
  timestamp="$(date +%s)"
  available_mb="$(awk '/MemAvailable/ {print int($2/1024)}' /proc/meminfo)"
  docker stats --no-stream --format '{{.Name}},{{.CPUPerc}},{{.MemUsage}},{{.MemPerc}}' \
  | { grep "^${project_name}-" || true; } \
  | while IFS=, read -r name cpu mem_usage mem_percent; do
      echo "${timestamp},${available_mb},${name},${cpu},${mem_usage},${mem_percent}" >> "$out_csv"
    done
  sleep "$interval"
done

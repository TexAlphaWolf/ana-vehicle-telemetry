#!/usr/bin/env bash
# End to end inside the image (read-only root, no capabilities, no network): a synthetic log and its truth are written to a
# volume, validated, analysed and scored, the report is rebuilt from its JSON, the two implementations are compared, and the
# benchmark runs small. Needs Docker. Usage: tools/docker_e2e.sh [image]
set -euo pipefail
IMAGE="${1:-vtel}"
VOL="vtel-e2e-$$"
TMP="$(mktemp -d)"
trap 'docker volume rm -f "$VOL" >/dev/null 2>&1 || true; rm -rf "$TMP"' EXIT

[ "$(docker run --rm --entrypoint id "$IMAGE" -u)" != 0 ]   # not root
docker volume create "$VOL" >/dev/null
docker run --rm --user 0 -v "$VOL":/data --entrypoint chown "$IMAGE" 10001 /data

RUN=(docker run --rm --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges --network none -v "$VOL":/data "$IMAGE")
cat_file() { docker run --rm --entrypoint cat -v "$VOL":/data "$IMAGE" "$1" > "$2"; }

out="$("${RUN[@]}" generate -o /data/drive.csv --truth /data/truth.json --days 3 --seed 4)"
grep -q 'written: /data/drive.csv' <<<"$out"
out="$("${RUN[@]}" validate /data/drive.csv)"
grep -q '^ok: .* samples from 2026-03-02T.*channels: speed, rpm, throttle, load, coolant, fuel' <<<"$out"

out="$("${RUN[@]}" analyze /data/drive.csv --truth /data/truth.json --out /data/out)"
grep -q '^/data/drive.csv: .* samples, .* trips' <<<"$out"
grep -q 'against the truth: .* trips matched' <<<"$out"
grep -q ', 0 false alarms$' <<<"$out"
cat_file /data/out/report.json "$TMP/report.json"
grep -q '"kind": "report"' "$TMP/report.json"
cat_file /data/out/report.md "$TMP/report.md"
"${RUN[@]}" render /data/out/report.json -o /data/out/again.md >/dev/null
cat_file /data/out/again.md "$TMP/again.md"
cmp "$TMP/again.md" "$TMP/report.md"                              # the report is rebuilt exactly from the JSON
cat_file /data/out/summary.png "$TMP/summary.png"
[ "$(head -c 4 "$TMP/summary.png" | tail -c 3)" = "PNG" ]

out="$("${RUN[@]}" analyze)"                                      # the demo log, built inside the container
grep -q '^demo drive log (synthetic, 14 days, seed 1): 52,542 samples, 27 trips, ' <<<"$out"

out="$("${RUN[@]}" verify --draws 5)"
grep -q '^6 of 6 comparisons agree with the literal implementation' <<<"$out"

"${RUN[@]}" bench --sizes 2000,5000 --repeat 1 --draws 3 --ref-samples 2000 --seeds 3 --out /data/bench >/dev/null
cat_file /data/bench/bench.json "$TMP/bench.json"
grep -q '"ok": true' "$TMP/bench.json"

set +e; "${RUN[@]}" validate /data/nope.csv >/dev/null 2>&1; rc=$?; set -e   # a missing file is exit code 2
[ "$rc" = 2 ]
echo "docker end-to-end: OK"

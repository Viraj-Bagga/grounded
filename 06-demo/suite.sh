#!/usr/bin/env bash
# The full check suite for 06-demo: the offline self-tests, then every
# no-argument ui_check mode, one at a time, the same set as the 2026-09-20
# final regression.
#
#   bash 06-demo/suite.sh OUTDIR
#
# Needs llama-server on 8080, the field app on 8770 (or FIELD_URL) and base on
# 8781. regions installs the India pack from the distribution node on 8790
# when this device does not have it yet, so start the node too
# (python 07-distribute/server.py). packs, phone (needs --lan), reread and
# review take arguments and are not part of it. rules runs last, because it
# reads the assessments the other modes leave behind.
#
# Two things from claude.md are built in rather than remembered:
#   - both llama-server slots must be idle before a live mode starts, because a
#     slot left PROCESSING makes the compare beat wait 300 s for nothing;
#   - drop is re-run alone when it fails in the suite, because it is the known
#     flake that passes on its own. Both results are printed, and the summary
#     says which one counted.
#
# Exit code is the number of failing steps.

set -u
cd "$(dirname "$0")/.." || exit 99
OUT=${1:?usage: bash 06-demo/suite.sh OUTDIR}
mkdir -p "$OUT"
LOG="$OUT/suite.txt"
PY=.venv/bin/python
LLAMA=${LLAMA_URL:-http://127.0.0.1:8080}
failed=()

say() { echo "$*" | tee -a "$LOG"; }

slots_idle() {
  curl -s "$LLAMA/slots" | "$PY" -c \
    "import json,sys; s=json.load(sys.stdin); sys.exit(0 if not any(x['is_processing'] for x in s) else 1)" 2>/dev/null
}

wait_idle() {
  for _ in $(seq 1 120); do slots_idle && return 0; sleep 1; done
  say "  llama-server still has a slot PROCESSING after 120 s: restart it before trusting anything below"
  return 1
}

: > "$LOG"
say "$(date '+%Y-%m-%d %H:%M:%S') 06-demo full suite"
say "field ${FIELD_URL:-http://127.0.0.1:8770}   base 8781   llama $LLAMA   node 8790 $(curl -s -m 3 -o /dev/null -w '%{http_code}' http://127.0.0.1:8790/packs | sed 's/^200$/up/;s/^000$/DOWN/')"
say "build $(git rev-parse --short HEAD)$(git diff --quiet -- 06-demo || echo ', 06-demo has uncommitted changes')"
say ""
say "=== offline self-tests"
for t in 06-demo/caseload.py 06-demo/selftest_profile_text.py 02-pairs/guards.py \
         02-pairs/escalation.py 02-pairs/selftest_validator.py 03-model/qlora_config.py; do
  if res=$("$PY" "$t" 2>&1); then
    say "  ok    $t   $(echo "$res" | tail -1)"
  else
    say "  FAIL  $t"; echo "$res" | tail -20 | tee -a "$LOG"; failed+=("$t")
  fi
done

for mode in shots people guards flow compare two-tabs drop regions voice queue sync base rules; do
  say ""
  say "=== $mode  $(date +%H:%M:%S)"
  wait_idle
  node 06-demo/ui_check.mjs "$mode" "$OUT/$mode" 2>&1 | tee -a "$LOG"
  code=${PIPESTATUS[0]}
  if [ "$code" -ne 0 ] && [ "$mode" = drop ]; then
    say "  drop failed in the suite; re-running it alone, as claude.md says, before counting it"
    wait_idle
    node 06-demo/ui_check.mjs drop "$OUT/drop-alone" 2>&1 | tee -a "$LOG"
    alone=${PIPESTATUS[0]}
    say "  drop alone exit $alone"
    [ "$alone" -eq 0 ] && { say "  counted: the known suite flake, not a failure"; code=0; }
  fi
  say "=== $mode exit $code  $(date +%H:%M:%S)"
  [ "$code" -ne 0 ] && failed+=("$mode")
done

say ""
say "check lines: $(grep -c '^PASS' "$LOG") PASS, $(grep -c '^FAIL' "$LOG") FAIL (a drop re-run adds its own)"
if [ ${#failed[@]} -eq 0 ]; then
  say "SUITE PASSED: 6 self-tests, 13 modes."
else
  say "SUITE FAILED: ${failed[*]}"
fi
exit ${#failed[@]}

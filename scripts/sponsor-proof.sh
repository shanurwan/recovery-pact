#!/usr/bin/env bash
# Sponsor-integration experiments: what Meterless and Zetaris each change, measured.
#
# Every experiment changes one thing against a baseline and is validated from its
# raw traces. Results land in evals/results/<label>/ next to the published benchmark.
#
#   M  meterless-nightshift  all 8 incidents x3 through Meterless Nightshift (signed receipts,
#                            routing, overhead)
#   M  hmem-control          incidents A and E x3, each repeated with memory off and then on
#   M  poisoned-memory       incident B x3 with a forged "verified: killing the settlement
#                            worked" memory planted in H-MEM
#   Z  zetaris-outage        all 8 incidents x3, Zetaris unreachable, no local fallback
#   Z  zetaris-partial       incidents A and G x3, only the change calendar unreachable
#   Z  zetaris-freshness     incident A: registry edited in the source system between runs
#
# Zetaris and H-MEM experiments call Nemotron 3 Ultra on the NVIDIA API directly, the same
# as the published ultra-benchmark, so the sponsor component is the only variable.
# meterless-nightshift goes through Nightshift: METERLESS_BASE_URL and a token in
# ~/.rp-ns-token are required.
#
#   bash scripts/sponsor-proof.sh                 # everything
#   bash scripts/sponsor-proof.sh meterless-nightshift zetaris-outage
set -uo pipefail
cd "$(dirname "$0")/.."

FILES=(-f compose.yaml)
[ "${ZETARIS:-1}" = 1 ] && FILES+=(-f compose.zetaris.yaml)
SHA=$(git rev-parse HEAD 2>/dev/null || echo unknown)
NS_URL=${METERLESS_BASE_URL:-http://192.168.100.19:18089}
NS=(-e AI_PROVIDER=meterless -e METERLESS_BASE_URL="$NS_URL" -e METERLESS_RUNTIME_TOKEN="$(cat ~/.rp-ns-token 2>/dev/null)"
    -e METERLESS_MODEL=meterless/deep -e INFERENCE_MODE=nemotron)
DIRECT=(-e AI_PROVIDER=nvidia -e INFERENCE_MODE=nemotron)
run() { docker compose "${FILES[@]}" exec -T -e BENCH_GIT_SHA="$SHA" "$@"; }

exp() {
  local label=$1; shift
  echo "== $label ($(date -u +%H:%M:%S) UTC)"
  rm -rf "evals/results/$label"
  run "$@" 2>&1 | grep -v '^\s*$' > "evals/results/$label.log"
  local rc=${PIPESTATUS[0]}
  tail -4 "evals/results/$label.log"
  echo "== $label exit $rc ($(date -u +%H:%M:%S) UTC)"
}

ALL=(zetaris-freshness zetaris-partial zetaris-outage hmem-control poisoned-memory meterless-nightshift)
for e in "${@:-${ALL[@]}}"; do
  case $e in
    meterless-nightshift)
      exp $e "${NS[@]}" api python -u -m app.evals.run --label $e --arms pact --no-encores --repeats 3 ;;
    hmem-control)
      exp $e "${DIRECT[@]}" api python -u -m app.evals.run --label $e --arms pact --scenarios A,E --repeats 3 --encore-control ;;
    poisoned-memory)
      exp $e "${DIRECT[@]}" api python -u -m app.evals.run --label $e --arms pact --scenarios B --no-encores --repeats 3 \
        --seed-memory evals/experiments/poisoned-memory.json ;;
    zetaris-outage)
      exp $e "${DIRECT[@]}" -e BUSINESS_FALLBACK=false -e BUSINESS_OUTAGE=all \
        api python -u -m app.evals.run --label $e --arms pact --no-encores --repeats 3 ;;
    zetaris-partial)
      exp $e "${DIRECT[@]}" -e BUSINESS_FALLBACK=false -e BUSINESS_OUTAGE=calendar \
        api python -u -m app.evals.run --label $e --arms pact --scenarios A,G --no-encores --repeats 3 ;;
    zetaris-freshness)
      exp $e "${DIRECT[@]}" api python -u -m app.evals.freshness --label $e --repeats 2 ;;
    *) echo "unknown experiment $e"; exit 2 ;;
  esac
done

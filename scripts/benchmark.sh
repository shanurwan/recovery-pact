#!/usr/bin/env bash
# Reproduce the RecoveryPact benchmark: preflight -> run -> validate.
#
#   bash scripts/benchmark.sh                      # replay mode, no API key needed
#   INFERENCE_MODE=nemotron bash scripts/benchmark.sh --repeats 3   # live Nemotron
#   ZETARIS=1 bash scripts/benchmark.sh            # with live Zetaris (run scripts/zetaris-setup.sh first)
#
# Extra arguments go to the harness (python -m app.evals.run --help).
set -euo pipefail
cd "$(dirname "$0")/.."

LABEL=${LABEL:-repro-$(date -u +%Y%m%d-%H%M%S)}
MODE=${INFERENCE_MODE:-replay}
FILES=(-f compose.yaml)
[ "${ZETARIS:-0}" = 1 ] && FILES+=(-f compose.zetaris.yaml)
SHA=$(git rev-parse HEAD 2>/dev/null || echo unknown)
EXEC=(docker compose "${FILES[@]}" exec -T -e INFERENCE_MODE="$MODE" -e BENCH_GIT_SHA="$SHA" api)

echo "== preflight ($MODE)"
"${EXEC[@]}" python -m app.evals.preflight

echo "== benchmark -> evals/results/$LABEL"
"${EXEC[@]}" python -u -m app.evals.run --label "$LABEL" "$@"

echo "== independent validation"
"${EXEC[@]}" python -m app.evals.validate "evals/results/$LABEL" --against-env
echo "Results: evals/results/$LABEL/summary.md"

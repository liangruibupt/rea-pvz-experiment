#!/usr/bin/env bash
# Score all 12 blinded submissions on the full 16-scenario suite, 3 at a time.
set -u
E=/home/ubuntu/workspace/rea-pvz-experiment/evaluation-20261028
S=/home/ubuntu/workspace/rea-pvz-experiment/operator/evaluator/score.py
SUITE=/home/ubuntu/workspace/rea-pvz-experiment/operator/scenario-suite
mkdir -p "$E/results"
score_one() {
    d="$1"; n=$(basename "$d")
    python3 "$S" --suite-root "$SUITE" --candidate-command "$d/submission/bin/run-scenario" \
        --candidate-cwd "$d/submission" --out "$E/results/$n.json" > "$E/results/$n.log" 2>&1
    echo "$n rc=$?" >> "$E/results/progress.txt"
}
export -f score_one; export E S SUITE
ls -d "$E"/blind/rep* | xargs -P 3 -I{} bash -c 'score_one {}'
echo ALL_DONE >> "$E/results/progress.txt"

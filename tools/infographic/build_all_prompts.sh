#!/usr/bin/env bash
# 全 14 枚のプロンプトを spec + layout から組み立て直す。
# spec を更新したあとに実行し、prompts/*.txt を現行の内容へ揃える。
set -euo pipefail

cd "$(dirname "$0")/../.."
BASE=tools/infographic

build() { python3 "$BASE/build_prompt.py" "$BASE/specs/$1" "$2" "$BASE/layouts/$3" "$BASE/prompts/$4"; }

build concept.json      initial-concept   initial-concept.txt   01-initial-concept.txt
build concept.json      lean-canvas       lean-canvas.txt       02-lean-canvas.txt
build concept.json      inception-deck    inception-deck.txt    03-inception-deck.txt
build requirements.json prd               prd.txt               04-prd.txt
python3 "$BASE/build_grid_prompt.py" --out "$BASE/prompts/05-user-story-map.txt"
build requirements.json roadmap           roadmap.txt           06-roadmap.txt
build design.json       design            design.txt            07-design.txt
build design.json       doc-relations     doc-relations.txt     08-doc-relations.txt
build extra1.json       adr-map           adr-map.txt           09-adr-map.txt
build extra1.json       gem-score         gem-score.txt         10-gem-score.txt
build extra2.json       testing           testing.txt           11-testing-strategy.txt
build extra2.json       cloudflare        cloudflare.txt        12-cloudflare.txt
build extra3.json       ops-rules         ops-rules.txt         13-ops-rules.txt
build extra4.json       architecture-flow architecture-flow.txt 14-architecture-flow.txt

#!/usr/bin/env bash
# Project-scoped OpenMinion config for any OpenAI-compatible endpoint.
# Usage: OPENAI_COMPATIBLE_API_KEY=... ./scripts_setup.sh https://api.deepseek.com deepseek-flash
set -euo pipefail
BASE_URL="${1:?base url}"; MODEL="${2:?model id}"
export OPENMINION_HOME="$PWD" OPENMINION_DATA_ROOT="$PWD/.openminion"
openminion setup --provider custom-openai-compatible --api-format openai-compatible \
  --base-url "$BASE_URL" --model "$MODEL" --no-chat
openminion doctor --check-turn --json > .openminion/doctor.json || true
python -c "import json;print(json.load(open('.openminion/doctor.json'))['summary'])"

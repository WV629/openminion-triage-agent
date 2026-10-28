# OpenMinion Triage Agent

A small, repeatable maintainer workflow built on the **OpenMinion 0.1 Python SDK** for Cortensor Hackathon #5:
point it at any public GitHub repo and it produces a **triage report** (suggested labels, priority, reasons,
items needing maintainer attention) plus **draft release notes** from recently merged PRs — and it asks a
**human for approval before writing anything**.

## OpenMinion SDK workflow

| Step | OpenMinion building block | What happens |
|---|---|---|
| 1. Triage | `Agent` + `@tool` + `output_type` + `session_id` | `triager` calls `list_recent_issues`, `list_recent_pulls`, `previous_triage` (read-only, idempotent tools) and returns a pydantic-validated `TriageReport`. Session id is per repo (`triage-<owner>-<repo>`), so repeat runs continue the same session. |
| 2. Release notes | `subagent()` (delegation) | a bounded `release-writer` subagent drafts grouped Markdown release notes from merged PRs. |
| 3. Publish | `@tool(dangerous=True)` + `approval_callback` + `forced_tools` | `publisher` must call `save_outputs`; OpenMinion routes the dangerous call through the approval callback (interactive y/N, or `--auto-approve yes|no`). Nothing is written if denied. |
| 4. Memory | `previous_triage` tool + local state | the last run's labels/priorities are stored in `state/<repo>.json` (only after approval) and fed back so unchanged items are not re-escalated. |
| 5. Diagnostics | `AgentRunResult` (`run_id`, `run_state`, `stats`), `ProviderError`, `TurnTimeoutError`, `openminion doctor` | every run writes `out/<repo>-<ts>/diagnostics.json` with per-step run ids, token/latency stats, and the tool-call trace. |

## Setup

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# any OpenAI-compatible endpoint; key read from env, never stored in the repo
export OPENAI_COMPATIBLE_API_KEY=...            # your DeepSeek key
./scripts_setup.sh https://api.deepseek.com deepseek-flash   # tested model: DeepSeek-V4.1-Flash
```

Cortensor Portal works the same way (`openminion setup --provider cortensor-portal --model oss-20b --no-chat` with `CORTENSOR_API_KEY`).

## Run

```bash
export OPENMINION_HOME="$PWD" OPENMINION_DATA_ROOT="$PWD/.openminion"
python -m triage_agent.cli openminion/openminion --days 14 --limit 15          # asks before writing
python -m triage_agent.cli openminion/openminion --auto-approve yes            # non-interactive demo
```

Optional `GITHUB_TOKEN` raises the GitHub API rate limit (unauthenticated: 60 req/h). The agent only reads GitHub.

Outputs: `out/<repo>-<timestamp>/triage_report.md`, `triage_report.json`, `diagnostics.json`.

Sample real runs against `openminion/openminion` are in [`examples/`](examples/):
`run1-first/` (no memory), `run2-memory/` (memory loaded), `memory_comparison.json`, and SDK probes in `probes/`.

### Real-run results (2026-10-28, DeepSeek `deepseek-flash`)
| | Run 1 (fresh) | Run 2 (memory) |
|---|---|---|
| Items triaged | 9 issues + 10 PRs = 19 | 19 |
| Tool calls | `list_recent_issues`, `list_recent_pulls`, `previous_triage` (0 prior items) | same, 19 prior items loaded |
| Changes vs. previous run | — | 18 unchanged, 1 priority bump (#460 P3→P2), 0 new, nothing re-escalated |
| Approval | `save_outputs` approved via callback → 3 files written | same |
| Wall time | ~2.5 min | ~2.5 min |
| Cost | ≈ ¥0.07 (≈ $0.01) per run (DeepSeek balance delta; all attempts + probes together ¥0.31) | |

## Building Blocks Tested
Full repro steps for every issue are in [FINDINGS.md](FINDINGS.md); a ready-to-apply fix for F8/F9/F10 is in
[`patches/`](patches/).

| Building block | Used for | Verdict | Findings |
|---|---|---|---|
| `Agent` + `instructions` | triager, formatter, publisher | ✅ works; instructions reach the model under `[IDENTITY]`, but are diluted by a ~4.9k-token runtime prompt | F8 |
| `@tool` | 3 read tools + 1 write tool | ⚠️ default scope makes every tool confirmation-gated; needs `min_scope="READ_ONLY"` | F7 |
| `output_type` (pydantic) | `TriageReport` | ⚠️ schema never sent to the model; prose/foreign JSON; error masks real cause | F8, F10, F11 |
| Freshness verification (runtime) | implicit on "last N days" | ❌ discards user-tool evidence and replaces the answer with a refusal | F9 |
| `subagent()` | release-notes writer | ✅ isolated session, stats returned | — |
| `@tool(dangerous=True)` + `approval_callback` | human gate on writes | ✅ approve and deny both verified; denied tool body never runs | — |
| `forced_tools` | publisher must save | ✅ (soft: not a provider `tool_choice`) | F13 |
| Sessions / local memory tool | repeat runs | ✅ second run skips unchanged items | F11 (session id lost on failure) |
| `AgentRunResult.stats` | token/latency diagnostics | ⚠️ under-counts internal + retried provider calls | F12 |
| `ProviderError` | error handling | ⚠️ quota reported as AUTH_ERROR | F1 |
| Setup CLI / `doctor` | project config | ⚠️ minor rough edges | F2, F4, F5 |
| Demo/echo provider | credential-free testing | ⚠️ ignores tools/forced tools | F3, F6 |
| Custom OpenAI-compatible provider → DeepSeek | model | ✅ works; one wasted 400 per internal call on thinking models | F12 |

## What We Learned
- **Tools and the approval gate are the strongest part of 0.1.** Once a tool is visible, the dangerous-tool path is
  exactly what a maintainer bot needs: the callback receives tool name + args + an approval id, a `False` cleanly
  blocks execution, and the model reports the denial instead of retrying.
- **The policy layer is stricter than the docs suggest.** A plain `@tool` is treated as a local *write* and silently
  needs confirmation; without a callback the run still says `completed`. Mark read tools `min_scope="READ_ONLY"`.
- **Structured output is validation, not generation.** `output_type` is only checked after the reply, the schema never
  reaches the model, and the runtime prefixes replies with the agent id. Put the schema in your instructions *and*
  keep a bounded repair turn — with DeepSeek-Flash the repair turn was what actually produced valid JSON.
- **The runtime has opinions you inherit.** A freshness verifier can overwrite a correct, tool-grounded answer with a
  refusal if your tool output lacks a recognised date key. Returning `retrieved_at` in tool results fixes it.
- **Measure on the wire.** Wire capture showed 5 HTTP requests (two 400s) for a one-line turn that `stats` counts as
  one LLM call; budget from provider-side numbers, not `stats`. Real cost here was still tiny: ≈ ¥0.07 per full run.
- **Memory is simplest as an explicit tool.** Feeding last run's labels back through a read-only `previous_triage`
  tool made the second run stable (18/19 unchanged, 0 re-escalations) without depending on session internals.

## Dependencies & license
OpenMinion (Apache-2.0), pydantic, Python stdlib. GitHub public REST API (read-only).

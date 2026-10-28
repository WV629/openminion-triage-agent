# STATUS — Cortensor Hackathon #5 entry (OpenMinion Triage Agent)

Updated: 2026-10-28 19:20 CST
Deadline: **2026-12-19 07:59 UTC** (= 2026-12-19 15:59 CST; DoraHacks https://dorahacks.io/hackathon/2418/detail)

## Project
GitHub issue/PR triage + draft release notes agent on OpenMinion 0.1 SDK, with human approval before any write.

## Done (2026-10-28)
- Model: DeepSeek official API `https://api.deepseek.com`, model **`deepseek-flash`** (DeepSeek-V4.1-Flash; user asked for flash only — no pro model).
  Key = Hark vault secret "DeepSeek API key", bound as Hark service `deepseek` and injected on the wire; config only holds `api_key_env: OPENAI_COMPATIBLE_API_KEY`. Key not in repo, logs or diagnostics.
- Real end-to-end runs on `openminion/openminion` (19 items): run 1 fresh, run 2 with memory (18/19 unchanged, 0 new, nothing re-escalated). Artifacts in `examples/`.
- Verified: tool calls, subagent delegation, structured output (via repair turn), approval_callback approve + deny, forced_tools, memory across runs.
- FINDINGS.md: F1–F13 (new: F7 default tool scope needs confirmation, F8 output_type schema never sent, F9 freshness verifier drops user-tool evidence, F10 masked validation error, F11 agent-id prefix + lost run facts, F12 DeepSeek forced tool_choice 400s + stats undercount, F13 forced_tools soft).
- Fix patch for F8/F9/F10: `patches/0001-output-schema-validation-error-freshness-user-tools.patch` (applied locally to `upstream-openminion/`; run 2 used the patched SDK, run 1 the unpatched one). Passes upstream tests `tests/api/test_agent.py` (37) + `tests/brain/test_freshness_enforcement.py`, `test_tgcr_verifier_contract.py` (19); full suite not run, no new regression tests written yet.
- README "Building Blocks Tested" + "What We Learned" written.
- Pushed to PRIVATE repo (see below), 23 files, tree identical to local HEAD.
- Cost: ≈ ¥0.07 (≈ $0.01) per full run; whole session incl. failed attempts/probes ¥0.31. DeepSeek balance left ≈ ¥17.88.

## Repo
**https://github.com/WV629/openminion-triage-agent** — PRIVATE (verified via API 2026-10-28). Keep private until the submission repo is announced.
Hark GitHub App installed on WV629 (installation 176151824, selected repos) so Hark can git-push. Local repo history differs from GitHub's (first files went up via web upload); push from a fresh clone, not with `git push` from this dir.

## Left to do
- 1–5 min demo video (screen-record `python -m triage_agent.cli openminion/openminion` + show approval prompt and examples/).
- Add regression tests for the patch and run the full upstream suite before offering it upstream.
- When the Hackathon #5 submission repo is announced: make repo public (needs user OK) → PR to it. Likely target pattern: https://github.com/cortensor/community-projects (Hackathon #4 used it), unconfirmed.
- Optional bonus: file F7/F8/F9 as OpenMinion issues + PR the patch (needs user OK).
- Optional: try provider `response_format` for structured output; exercise `TurnTimeoutError` with a tiny timeout.

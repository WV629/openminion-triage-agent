# FINDINGS — OpenMinion 0.1 building blocks (bugs & rough edges)

Environment: Linux x86_64, Python 3.12.15, OpenMinion installed editable from
`github.com/openminion/openminion` main @ `f0fcfd8` (2026-10-28), `openminion --version` = 0.1.14.
Model endpoints: F1–F6 found with the Infron router (`https://llm.onerouter.pro/v1`, `deepseek/deepseek-v4-flash`);
F7–F13 found in real runs against **DeepSeek's own API** (`https://api.deepseek.com`, model `deepseek-flash` = DeepSeek-V4.1-Flash,
OpenMinion preset `custom-openai-compatible`), 2026-10-28.
No secrets appear below; request IDs truncated.

Status legend: **confirmed** (reproduced), **suspected** (seen once / needs more checking).

---

## F1 — Quota/credit exhaustion is reported as an authentication failure — confirmed
- **Block:** models / provider error mapping, diagnostics (`doctor --check-turn`)
- **Repro:**
  1. `openminion setup --provider custom-openai-compatible --api-format openai-compatible --base-url https://llm.onerouter.pro/v1 --model deepseek/deepseek-v4-flash --no-chat` with a *valid* key on an account with $0 credit.
  2. `Agent(config_path=".openminion/agents.json").run("Say OK")` or `openminion doctor --check-turn --json`.
- **Expected:** a quota/billing class (e.g. `QUOTA_EXCEEDED` / `RATE_LIMIT`) and a hint to top up, since the key itself authenticated.
- **Actual:** `ProviderError.code == "AUTH_ERROR"`, message "The configured model provider rejected authentication for this turn … Check the provider credentials". `details` correctly carry `status_code: 403`, `upstream_code: "insufficient_user_quota"`. Doctor check `agent.turn_smoke` shows the same AUTH_ERROR.
- **Impact:** sends users to rotate a working key. `upstream_code` is already parsed, so mapping `insufficient_user_quota` / `insufficient_quota` → quota class looks cheap.

## F2 — `setup --provider openai --base-url …` silently accepted — confirmed
- **Block:** models / setup CLI
- **Repro:** `OPENAI_API_KEY=x openminion setup --provider openai --base-url https://llm.onerouter.pro/v1 --model deepseek/deepseek-v4-flash --no-chat`
- **Expected:** `--help` says `--base-url` is "for custom provider presets that require one", so either reject it for `openai` or warn.
- **Actual:** saved without warning; the connection is labelled "OpenAI" while `provider_identity` says `model_family: deepseek, service_vendor: unknown`. Works at runtime, but the label/readiness output misleads.

## F3 — Echo/demo provider silently ignores `forced_tools` and reports `completed` — confirmed
- **Block:** tools, agent execution (demo mode)
- **Repro:** `openminion config init --provider echo`; then
  `Agent(tools=[save_outputs], forced_tools=["save_outputs"]).run("save", approval_callback=cb)` where `save_outputs` is `@tool(dangerous=True)`.
- **Expected:** either the forced tool runs (so plumbing like approval callbacks can be tested credential-free), or a warning/error that forced tools are unsupported in demo mode.
- **Actual:** `run_state="completed"`, `stats.tool_calls=0`, the tool and the approval callback never fire, no warning. Makes the credential-free tour unable to exercise tools/approval and can hide bugs in CI.

## F4 — Fresh project always fails/warns `doctor` on identity bundle — confirmed
- **Block:** diagnostics / setup
- **Repro:** fresh dir, `OPENMINION_HOME=$PWD OPENMINION_DATA_ROOT=$PWD/.openminion`, run `setup` (custom-openai-compatible) then `openminion doctor --check-turn --json`.
- **Expected:** a config produced by `setup` is doctor-clean apart from provider reachability.
- **Actual:** `identity.bundle` WARN "Identity profile is missing … for agent 'openminion'" (root `.openminion/identity/agents/openminion` not found). `setup` could create the default profile, or doctor could downgrade it to INFO for the default agent. Also `security.untrusted_content.boundary_posture` WARN on a default config.

## F5 — `doctor --json` is noisy on stderr — confirmed (minor)
- **Repro:** `openminion doctor --check-turn --json 2>err.txt` → ~78 `INFO openminion.modules.tool.bootstrap: … registered via REGISTRAR` lines on stderr. stdout JSON is clean and parseable (good).
- **Expected:** INFO bootstrap logs suppressed unless `-v` when `--json` is used.

## F6 — Structured-output failure under demo provider surfaces as a raw pydantic error — confirmed (minor)
- **Repro:** echo config, `Agent(output_type=TriageReport).run(...)` → `AgentOutputValidationError: … Invalid JSON: expected value at line 1 column 1 … input_value='openminion: Triage repos... (thinking=minimal)'`.
- **Expected:** demo mode either skips structured validation or the error says "demo provider does not produce structured output".

---

## F7 — A plain `@tool` needs human confirmation even when `idempotent=True` — confirmed
- **Block:** tools / action policy
- **Repro:** `examples/probes/default_tool_scope_needs_confirmation.txt`
  ```python
  @tool(idempotent=True)
  def get_weather(city: str) -> str: ...
  Agent(tools=[get_weather]).run("What's the weather in Paris? Use the tool.")   # no approval_callback
  ```
- **Expected:** a pure/idempotent function runs without a prompt. `derive_tool_risk_spec()` even computes `default_confirm=False` for an idempotent WRITE_SAFE tool.
- **Actual:** `_decorate()` gives every user tool `min_scope_default="WRITE_SAFE"` → risk class `write`; `PolicyService._confirm_reason()` never reads `RiskSpec.default_confirm`, so `ENFORCE_SAFE_CONFIRM` fires. Without a callback the run ends `run_state="completed"`, `tool_calls=0`, and `.text` is the confirmation prompt ("Policy confirmation required… Reply exactly yes…"). With `output_type` set this surfaces only as an unrelated `AgentOutputValidationError`.
- **Workaround:** `@tool(min_scope="READ_ONLY")` for read tools (used in `triage_agent/cli.py`).
- **Suggested fix:** honour `default_confirm` in `_confirm_reason`, or default `@tool(idempotent=True)` to READ_ONLY; and return a non-`completed` run_state (e.g. `awaiting_confirmation`) when a confirmation is pending in SDK mode.

## F8 — `Agent(output_type=Model)` never tells the model about the schema — confirmed (fix patch prepared)
- **Block:** structured output
- **Repro:** read `Agent._build_payload()` in `src/openminion/api/agent.py`: `output_type` is not sent (no `response_format`, no schema in the system prompt); it is only used in `_coerce_output()` after the reply. With `instructions="Return only JSON"` and no schema, DeepSeek invented its own fields (`report_version`, `repository`, `window`…) → validation error.
- **Expected:** the schema reaches the model (system prompt contract or provider `response_format`/`json_schema`).
- **Fix patch:** `patches/0001-output-schema-validation-error-freshness-user-tools.patch` appends the JSON Schema to `override_system_prompt` when `output_type` is a pydantic model.
- **Note:** even with the schema in the system prompt (our instructions already contained it), `deepseek-flash` behind OpenMinion's ~4.9k-token runtime prompt still returned its own JSON shape in 4/4 triage runs (the last one on the patched SDK). The agent recovers with one bounded tool-less "format-repair" turn, which validated in 2 of 3 runs (the failure was masked by F10). Real fix probably needs provider `response_format` support.

## F9 — Freshness verifier throws away results from caller-supplied tools — confirmed (fix patch prepared)
- **Block:** runtime verification (freshness), tools
- **Repro:** `examples/probes/freshness_verifier_discards_user_tool.txt` — `@tool get_weather` returns `{"city":"Paris","temp_c":21}`, the tool runs (`tool_calls=1`), yet the final answer is replaced by *"I couldn't provide a grounded current weather answer because Missing weather-domain live-data evidence…; Missing exact-date evidence…. Please retry with live data available…"*. Same for our triage prompt "last 14 days" (domain `other`, exact-date obligation).
- **Cause:** `_has_freshness_domain_evidence()` only accepts a built-in tool whose id equals the domain (`weather`), never offered to this agent; `_has_dated_evidence()` only accepts specific keys (`retrieved_at`, `date`, …) inside dict outputs.
- **Also:** the message has doubled punctuation ("answer.;" and "answer..").
- **Workaround:** tools return dicts with a `retrieved_at` timestamp.
- **Fix patch:** same patch file — successful non-built-in tool results count as domain evidence; reasons are joined without the extra periods.

## F10 — Structured-output error hides the real schema error — confirmed (fix patch prepared)
- **Block:** structured output / errors
- **Repro:** model replies `openminion: {"items":[…]}` where the JSON is valid but misses a required field. `_coerce_output` first fails on the whole text ("Invalid JSON: expected value at line 1 column 1"), then extracts the JSON, which fails schema validation — but that second error is swallowed and the first one is raised.
- **Expected:** the field-level error of the extracted JSON (e.g. `repo: Field required`).
- **Fix patch:** same patch file re-raises the inner `ValidationError`.

## F11 — Reply body is prefixed with the agent id, and `AgentOutputValidationError` drops run facts — confirmed
- `AgentRunResult.text` is always `"openminion: …"` (the config's agent id, not `Agent(name=...)`), e.g. `'openminion: OK'` for "Reply with exactly: OK". Breaks exact-match checks and is why every structured reply needs JSON extraction.
- When `output_type` validation fails the exception carries only `raw_text`/`validation_error`: the turn's `run_id`, `session_id`, `stats` (tokens) are lost, so the costliest step (triage, ~70–85 s with 3 tool calls) is missing from our diagnostics. Suggest attaching the `AgentRunResult` (minus `output`) to the exception.

## F12 — DeepSeek thinking models: every internal structured call costs a wasted 400 — confirmed
- **Block:** models / provider compatibility (custom-openai-compatible → `https://api.deepseek.com`, `deepseek-flash`)
- **Repro:** `examples/probes/approval_deny_forced_tools.json` (wire capture). Internal classifier/structured calls send `tool_choice={"type":"function","function":{"name":"submit_output"}}`; DeepSeek answers **400 "Thinking mode does not support this tool_choice"**; OpenMinion silently retries with `tool_choice:"auto"`. A one-line "What is 2+2?" turn made 5 HTTP requests (2 of them 400s) while `stats.llm_calls == 1`.
- **Impact:** extra latency on every turn; `stats` under-reports real provider calls, so cost accounting from `AgentRunResult.stats` is low.
- **Suggested fix:** learn per-model that forced tool_choice is unsupported (or disable thinking for internal classifier calls), and count retried/internal calls in stats.

## F13 — `forced_tools` is not sent as a provider tool_choice — observation
- `Agent(forced_tools=["delete_report"])` sent `tool_choice:"auto"` on the wire; the model called the tool anyway, so the forcing is runtime-level (prompt/retry), not provider-level. Not necessarily a bug, but worth documenting: `forced_tools` is a soft guarantee on providers where forced tool_choice works.

---

## Verified with a real model (DeepSeek `deepseek-flash`, 2026-10-28)
| Check | Result | Evidence |
|---|---|---|
| Tool calling (`@tool`, dict returns) | ✅ 3 tools called per run (after F7/F9 workarounds) | `examples/run*/diagnostics.json` `tool_trace` |
| `output_type` (pydantic) | ⚠️ model ignores schema (F8); 1 repair turn validated in 2/3 runs | `steps[].structured_output`, `format-repair` |
| `subagent()` delegation | ✅ `release-writer` ran in its own session id, stats returned | `steps[step=release-writer]` |
| `@tool(dangerous=True)` + `approval_callback` approve | ✅ callback got `(tool_name, args, approval_id)`; tool wrote files | `approvals[]`, `publish.written` |
| `approval_callback` deny | ✅ callback invoked, tool body **not** executed, reply "Confirmation denied. The action was not run." | `examples/probes/approval_deny_forced_tools.json` |
| `forced_tools` | ✅ publisher always called `save_outputs` (soft forcing, F13) | run logs |
| Memory/state across runs | ✅ run 2 loaded 19 prior items; 18/19 unchanged, 0 new, nothing re-escalated | `examples/memory_comparison.json` |
| Session reuse (`session_id=triage-<repo>`) | ⚠️ passed both runs, but not provable from results: the triage step's `session_id` is lost when validation fails (F11) | — |
| `ProviderError` mapping | ✅ (F1, earlier, quota → AUTH_ERROR) | above |
| `TurnTimeoutError` | not exercised (no timeouts hit at 240 s) | — |

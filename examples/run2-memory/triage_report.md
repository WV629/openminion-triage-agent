# Triage report — openminion/openminion



| # | Kind | Priority | Labels | Title |
|---|---|---|---|---|
| [#437](https://github.com/openminion/openminion/issues/437) | issue | P1 | bug, area:runtime, area:sessions, status:awaiting-release | `APIRuntime` does not start with `storage.backend: postgres` |
| [#448](https://github.com/openminion/openminion/issues/448) | issue | P1 | bug, area:runtime, area:approvals, area:identity, status:contributor-in-progress | Identity hard constraint `NEVER write memory records` bypassed by a turn's own terminal capture |
| [#449](https://github.com/openminion/openminion/issues/449) | issue | P1 | bug, area:runtime, area:scheduling, status:contributor-in-progress | Backend without atomic capture: consolidation runs re-extract up to `batch_limit` and add one pending intent per run |
| [#458](https://github.com/openminion/openminion/pull/458) | pr | P1 | area:runtime, area:sessions | Start `APIRuntime` with PostgreSQL runtime storage |
| [#463](https://github.com/openminion/openminion/pull/463) | pr | P1 | area:runtime, area:scheduling | Preserve trusted consolidation context |
| [#435](https://github.com/openminion/openminion/issues/435) | issue | P2 | bug, area:sdk, area:tools, status:awaiting-release | [0.1.12] @tool arguments typed as a Pydantic model or dataclass reach the function as a plain dict |
| [#446](https://github.com/openminion/openminion/issues/446) | issue | P2 | bug, area:runtime, area:sessions, status:contributor-in-progress | PostgreSQL: `storage migrate` modules share one `alembic_version`, runtime storage then fails on `sessions` |
| [#447](https://github.com/openminion/openminion/issues/447) | issue | P2 | bug, area:runtime, status:contributor-in-progress | `APIRuntime` start that fails after storage is built closes nothing |
| [#455](https://github.com/openminion/openminion/pull/455) | pr | P2 | release | Prepare OpenMinion 0.1.14 |
| [#456](https://github.com/openminion/openminion/issues/456) | issue | P2 | bug, area:runtime, area:scheduling, status:awaiting-release | Scheduled memory consolidation turn captures itself: gateway drops the `memory_consolidation_job` marker |
| [#457](https://github.com/openminion/openminion/pull/457) | pr | P2 | area:runtime, status:needs-review | Report the migration error in `storage migrate` entries |
| [#459](https://github.com/openminion/openminion/pull/459) | pr | P2 | release | Release OpenMinion 0.1.14 |
| [#460](https://github.com/openminion/openminion/pull/460) | pr | P2 | release | Include backup guidance in OpenMinion 0.1.14 |
| [#450](https://github.com/openminion/openminion/issues/450) | issue | P3 | bug, area:runtime, status:awaiting-release | `python -m openminion.modules.storage` exits 0 when storagectl's `main()` returns 2 |
| [#451](https://github.com/openminion/openminion/pull/451) | pr | P3 | area:runtime | Exit `python -m openminion.modules.storage` with the status that `main()` returns |
| [#452](https://github.com/openminion/openminion/issues/452) | issue | P3 | documentation, area:runtime, status:awaiting-release | Upgrade guide: `storage backup` refuses 10 of 17 SQLite files; turn-start reset writes legacy working-state shape |
| [#453](https://github.com/openminion/openminion/pull/453) | pr | P3 | documentation | Document runtime home backups and the typed save boundary |
| [#461](https://github.com/openminion/openminion/pull/461) | pr | P3 | release | Publish OpenMinion 0.1.14 runtime metadata |
| [#462](https://github.com/openminion/openminion/pull/462) | pr | P3 | release | Back-merge OpenMinion 0.1.14 runtime metadata |

## Why

- #437: Fix merged as PR #458 (2026-10-28T10:01:26Z); holding P1 until 0.1.14 release verifies postgres startup.
- #449: Still the highest-impact runtime defect: unbounded extraction requests and growing pending intent set.
- #448: Policy-enforcement bypass on a security-relevant write path; no linked fix PR yet.
- #456: Fix merged as PR #463; label already reflects fix-merged-awaiting-release.
- #446: Split out of #437; independent of the runtime startup fix.
- #447: Resource-leak on failed start; lifecycle close path only wired for constructed runtimes.
- #435: PR #455 release notes claim typed @tool argument preservation is in the 0.1.14 line; verify before closing.
- #450: Fix merged as PR #451; narrow exit-code correctness, low user impact.
- #452: Docs fix merged as PR #453 (plus release-carried #460).
- #457: Only open PR; fixes silent `status: error` with no message in migration reports. Ready for review.
- #463: Closes the self-capture path in #456; landed after the prior triage run.
- #458: Resolves the reported failure in #437; postgres startup verification still owed.
- #451: Addresses #450.
- #453: Documentation-only; addresses #452.
- #455: Version bump and changelog for the 0.1.14 line.
- #459: dev to main promotion; carries the time-tool freshness change.
- #460: Cherry-picks #453 guidance into the release line.
- #461: Automated runtime metadata publication.
- #462: Keeps main/dev runtime publication trees identical.

---

# Draft release notes

openminion: ### Features
- Preserve trusted consolidation context (#463)
- Start `APIRuntime` with PostgreSQL runtime storage (#458)

### Fixes
- Exit `python -m openminion.modules.storage` with the status that `main()` returns (#451)

### Docs & Chores
- Document runtime home backups and the typed save boundary (#453)
- Include backup guidance in OpenMinion 0.1.14 (#460)
- Prepare OpenMinion 0.1.14 (#455)
- Release OpenMinion 0.1.14 (#459)
- Publish OpenMinion 0.1.14 runtime metadata (#461)
- Back-merge OpenMinion 0.1.14 runtime metadata (#462)

**Highlights:** OpenMinion 0.1.14 ships with PostgreSQL-backed `APIRuntime`, trusted consolidation context, documented backup guidance, and a corrected storage module exit status.

"""Repeatable GitHub triage workflow built on the OpenMinion 0.1 Python SDK.

Pipeline (one run):
  1. triager Agent (tools + structured output + per-repo session)
       - tools: list_recent_issues, list_recent_pulls, previous_triage (local memory)
       - output_type=TriageReport (pydantic-validated)
  2. release-writer subagent (delegation via openminion.subagent)
       - drafts release notes from merged PRs
  3. publisher Agent with a dangerous `save_outputs` tool
       - OpenMinion approval_callback asks the human before anything is written
  4. diagnostics: run ids, stats and tool-call trace written to out/<run>/diagnostics.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

from openminion import Agent, AgentOutputValidationError, ProviderError, TurnTimeoutError, subagent, tool

from . import github_data
from .models import TriageReport

ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / "state"
OUT_DIR = ROOT / "out"

TRIAGER_INSTRUCTIONS = """You are a GitHub triage assistant for open-source maintainers.
Always call list_recent_issues and list_recent_pulls for the repo, and previous_triage to see
what was already triaged last run (do not re-escalate unchanged items).
For every item propose labels from: bug, enhancement, docs, question, security, performance,
breaking-change, good-first-issue, needs-repro, duplicate, dependencies.
Priority: P0 = security/data loss/crash on main path, P1 = broken documented feature,
P2 = normal bug or useful enhancement, P3 = nice-to-have/question.
Keep reasons to one sentence grounded in the title/body. Use the exact numbers and URLs returned by tools.
Return ONLY one JSON object (no Markdown, no prose, no code fences) matching this JSON Schema:
"""

# Workaround for FINDINGS F8: Agent(output_type=...) never sends the schema to the model.
TRIAGER_INSTRUCTIONS += json.dumps(TriageReport.model_json_schema())

FORMATTER_INSTRUCTIONS = ("You convert a GitHub triage write-up into JSON. Keep every item, number, URL, label and "
                          "priority exactly as written. Output ONLY one JSON object matching this JSON Schema: "
                          + json.dumps(TriageReport.model_json_schema()))

RELEASE_INSTRUCTIONS = """You write concise draft release notes in Markdown from merged pull requests.
Group under: ### Features, ### Fixes, ### Docs & Chores. One bullet per PR: '- <title> (#<number>)'.
Do not invent PRs. Finish with a one-line 'Highlights:' sentence."""

# ---------------------------------------------------------------- tools


def _now() -> str:
    # Workaround for FINDINGS F9: the freshness verifier only accepts dated evidence keyed
    # e.g. "retrieved_at"; without it a "last N days" request is answered with a refusal.
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _make_tools(repo: str, days: int, limit: int, trace: list):
    @tool(idempotent=True, min_scope="READ_ONLY", tags=("github", "read"))
    def list_recent_issues(repository: str) -> dict:
        """List issues (not PRs) updated recently in a public GitHub repository 'owner/name'."""
        t0 = time.time()
        rows = github_data.recent_issues(repository or repo, days=days, limit=limit)
        trace.append({"tool": "list_recent_issues", "count": len(rows), "ms": int((time.time() - t0) * 1000)})
        return {"retrieved_at": _now(), "repository": repository or repo, "issues": rows}

    @tool(idempotent=True, min_scope="READ_ONLY", tags=("github", "read"))
    def list_recent_pulls(repository: str) -> dict:
        """List pull requests updated recently in a public GitHub repository 'owner/name'."""
        t0 = time.time()
        rows = github_data.recent_pulls(repository or repo, days=days, limit=limit)
        trace.append({"tool": "list_recent_pulls", "count": len(rows), "ms": int((time.time() - t0) * 1000)})
        return {"retrieved_at": _now(), "repository": repository or repo, "pulls": rows}

    @tool(idempotent=True, min_scope="READ_ONLY", tags=("memory", "read"))
    def previous_triage(repository: str) -> dict:
        """Return the labels/priorities this agent assigned on its previous run for the repo."""
        state = _load_state(repository or repo)
        trace.append({"tool": "previous_triage", "count": len(state.get("items", {}))})
        return {"retrieved_at": _now(), "previous": state or {"note": "no previous run"}}

    return [list_recent_issues, list_recent_pulls, previous_triage]


def _state_path(repo: str) -> Path:
    return STATE_DIR / (repo.replace("/", "__") + ".json")


def _load_state(repo: str) -> dict:
    p = _state_path(repo)
    return json.loads(p.read_text()) if p.exists() else {}


def _save_state(repo: str, report: TriageReport) -> None:
    STATE_DIR.mkdir(exist_ok=True)
    state = {
        "last_run": dt.datetime.now(dt.timezone.utc).isoformat(),
        "items": {str(i.number): {"labels": i.suggested_labels, "priority": i.priority} for i in report.items},
    }
    _state_path(repo).write_text(json.dumps(state, indent=2))


def _render_markdown(report: TriageReport, release_md: str) -> str:
    lines = [f"# Triage report — {report.repo}", "", report.summary, "", "| # | Kind | Priority | Labels | Title |", "|---|---|---|---|---|"]
    for i in sorted(report.items, key=lambda x: (x.priority, x.number)):
        lines.append(f"| [#{i.number}]({i.url}) | {i.kind} | {i.priority} | {', '.join(i.suggested_labels)} | {i.title} |")
    if report.needs_maintainer_attention:
        lines += ["", "**Needs maintainer attention:** " + ", ".join(f"#{n}" for n in report.needs_maintainer_attention)]
    lines += ["", "## Why", ""] + [f"- #{i.number}: {i.reason}" for i in report.items]
    lines += ["", "---", "", "# Draft release notes", "", release_md.strip(), ""]
    return "\n".join(lines)


# ---------------------------------------------------------------- approval


def _approval_callback(auto: str | None, log: list):
    # OpenMinion calls approval_callback(tool_name, args, approval_id) before a confirm-gated tool runs.
    def cb(tool_name: str, args: dict, approval_id: str) -> bool:
        print(f"\n[approval] tool={tool_name} approval_id={approval_id}")
        print(f"[approval] args={json.dumps(args)[:400]}")
        if auto is not None:
            decision = auto == "yes"
            print(f"[approval] auto-decision: {'APPROVE' if decision else 'DENY'}")
        else:
            decision = input("Approve this write? [y/N] ").strip().lower() in {"y", "yes"}
        log.append({"tool": tool_name, "approval_id": approval_id, "approved": decision})
        return decision

    return cb


def _read_only_guard(log: list):
    """Callback for the read-only triage step: only our read tools may be approved."""
    allowed = {"list_recent_issues", "list_recent_pulls", "previous_triage"}

    def cb(tool_name: str, args: dict, approval_id: str) -> bool:
        ok = tool_name in allowed
        log.append({"tool": tool_name, "approval_id": approval_id, "approved": ok, "step": "triage"})
        return ok

    return cb


# ---------------------------------------------------------------- main


def run(args) -> int:
    repo = args.repo
    run_id = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = OUT_DIR / f"{repo.replace('/', '__')}-{run_id}"
    trace: list = []
    approvals: list = []
    diag: dict = {"repo": repo, "run": run_id, "config": args.config, "steps": []}
    session = f"triage-{repo.replace('/', '-')}"
    common = dict(config_path=args.config, agent_id=args.agent)
    if args.model:
        common["model"] = args.model

    try:
        # 1. triage (tools + structured output + session)
        with Agent(name="triager", instructions=TRIAGER_INSTRUCTIONS, output_type=TriageReport,
                   tools=_make_tools(repo, args.days, args.limit, trace), session_id=session, **common) as triager:
            t0 = time.time()
            prompt = (f"Triage repository {repo} (last {args.days} days). Call the tools, then answer with ONLY "
                      "the TriageReport JSON object described in your instructions — no Markdown table, no prose.")
            try:
                res = triager.run(prompt, timeout_seconds=args.timeout, approval_callback=_read_only_guard(approvals))
                report: TriageReport = res.output
                diag["steps"].append({"step": "triage", "run_id": res.run_id, "run_state": res.run_state,
                                      "session_id": res.session_id, "stats": res.stats, "secs": round(time.time() - t0, 1)})
            except AgentOutputValidationError as exc:
                # One bounded repair turn (no tools): convert the prose answer into the schema.
                diag["steps"].append({"step": "triage", "structured_output": "failed", "raw_text_head": exc.raw_text[:300],
                                      "secs": round(time.time() - t0, 1)})
                t0 = time.time()
                with Agent(name="formatter", instructions=FORMATTER_INSTRUCTIONS, output_type=TriageReport, tools=[],
                           session_id=session + "-format", **common) as fmt:
                    res = fmt.run("Convert this triage write-up into the JSON object:\n\n" + exc.raw_text,
                                  timeout_seconds=args.timeout)
                report = res.output
                diag["steps"].append({"step": "format-repair", "run_id": res.run_id, "run_state": res.run_state,
                                      "session_id": res.session_id, "stats": res.stats, "secs": round(time.time() - t0, 1)})
            print(f"[triage] {len(report.items)} items, attention={report.needs_maintainer_attention}")

            # 2. delegation: release-writer subagent
            merged = [p for p in github_data.recent_pulls(repo, days=args.days, limit=args.limit) if p["merged"]]
            writer = subagent(triager, name="release-writer", instructions=RELEASE_INSTRUCTIONS,
                              timeout_seconds=int(args.timeout))
            t0 = time.time()
            rel = writer.run("Merged PRs:\n" + json.dumps([{k: p[k] for k in ("number", "title", "labels")} for p in merged]))
            release_md = rel.text if merged else "_No merged PRs in this window._"
            diag["steps"].append({"step": "release-writer", "run_id": rel.run_id, "run_state": rel.run_state,
                                  "session_id": rel.session_id, "stats": rel.stats, "secs": round(time.time() - t0, 1)})

        report.repo = report.repo or repo
        if not report.summary:
            counts = {p: sum(1 for i in report.items if i.priority == p) for p in ("P0", "P1", "P2", "P3")}
            report.summary = f"{len(report.items)} items triaged — " + ", ".join(f"{k}: {v}" for k, v in counts.items() if v)
        markdown = _render_markdown(report, release_md)
        print("\n" + markdown)

        # 3. human approval before any write
        written: list[str] = []

        @tool(dangerous=True, tags=("filesystem", "write"))
        def save_outputs(confirm_summary: str) -> str:
            """Write the triage report, release notes and memory state to disk. Requires human approval."""
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "triage_report.md").write_text(markdown)
            (run_dir / "triage_report.json").write_text(report.model_dump_json(indent=2))
            _save_state(repo, report)
            written.extend([str(run_dir / "triage_report.md"), str(run_dir / "triage_report.json"), str(_state_path(repo))])
            return "saved: " + ", ".join(written)

        with Agent(name="publisher", instructions="Call save_outputs exactly once with a one-line summary, then report the result.",
                   tools=[save_outputs], forced_tools=["save_outputs"], session_id=session + "-publish", **common) as pub:
            pres = pub.run(f"Save the triage outputs for {repo}.", timeout_seconds=args.timeout,
                           approval_callback=_approval_callback(args.auto_approve, approvals))
            diag["steps"].append({"step": "publish", "run_id": pres.run_id, "run_state": pres.run_state,
                                  "stats": pres.stats, "text": pres.text[:300], "written": written})
        print(f"\n[publish] {'written: ' + ', '.join(written) if written else 'nothing written (denied or tool not executed)'}")
    except ProviderError as exc:
        diag["error"] = {"type": "ProviderError", "code": exc.code, "message": exc.message, "details": exc.details}
        print(f"provider failed: {exc.code}: {exc.message}", file=sys.stderr)
        return _finish(diag, trace, run_dir, 2, approvals)
    except (AgentOutputValidationError, TurnTimeoutError) as exc:
        diag["error"] = {"type": type(exc).__name__, "message": str(exc)[:2000],
                         "raw_text": (getattr(exc, "raw_text", "") or "")[:20000]}
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return _finish(diag, trace, run_dir, 3, approvals)
    return _finish(diag, trace, run_dir, 0, approvals)


def _finish(diag, trace, run_dir: Path, code: int, approvals: list | None = None) -> int:
    diag["approvals"] = approvals or []
    diag["tool_trace"] = trace
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "diagnostics.json").write_text(json.dumps(diag, indent=2, default=str))
    print(f"[diagnostics] {run_dir / 'diagnostics.json'}")
    return code


def main() -> int:
    p = argparse.ArgumentParser(description="OpenMinion GitHub triage + release-notes agent")
    p.add_argument("repo", help="public repo, e.g. openminion/openminion")
    p.add_argument("--days", type=int, default=14)
    p.add_argument("--limit", type=int, default=15)
    p.add_argument("--config", default=os.environ.get("OPENMINION_CONFIG", str(ROOT / ".openminion" / "agents.json")))
    p.add_argument("--agent", default=None)
    p.add_argument("--model", default=None)
    p.add_argument("--timeout", type=float, default=240)
    p.add_argument("--auto-approve", choices=("yes", "no"), default=None, help="non-interactive approval decision (for CI/demo)")
    return run(p.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())

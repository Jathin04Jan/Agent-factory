# Target Repo Kit — install into the repo the agent works ON

These files make the factory's Claude Code sessions dramatically better on
large codebases. Install them into your **target repo** (not this one) and
commit them:

```bash
cd /path/to/your/target-repo
mkdir -p .claude/agents
cp /path/to/agent-factory/target-repo-kit/agents/*.md .claude/agents/
git add .claude && git commit -m "chore: add Claude Code subagents"
```

## What each subagent does

| Agent | Role | Why it matters on a huge repo |
|---|---|---|
| `code-explorer` | Read-only navigator: finds files, traces flows, maps conventions | Exploration happens in the subagent's own context window and only a compact summary returns — the main session keeps its context for actual coding |
| `test-writer` | Writes/updates tests following the repo's existing patterns | Dedicated focus on coverage; runs only affected suites |
| `code-reviewer` | Adversarial fresh-eyes diff review | Catches contract mismatches and edge cases the author-session glosses over |

Claude Code auto-discovers `.claude/agents/*.md` and delegates based on each
agent's `description` — the factory's prompts also nudge it to use them.
The orchestrator needs zero changes.

## Also strongly recommended for the target repo

1. **`CLAUDE.md` at the repo root** — architecture map, module layout, how to
   run tests per module, conventions, forbidden areas. The single biggest
   quality lever for a large codebase.
2. **Per-module `CLAUDE.md` files** (e.g. `backend/billing/CLAUDE.md`) —
   Claude Code reads them when working in that directory. Great for huge
   repos where one root file can't cover everything.
3. Tune the agents above: mention your real frameworks, test commands, and
   directory names instead of the generic wording.

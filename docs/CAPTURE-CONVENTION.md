# Capture convention — feed the shared memory from any project

> Querying the MCP is **read-only** (D5): it never writes. Your *work* feeds the memory through a
> separate, explicit, source-tagged **capture** channel (`projlog`), never through the query surface.
> This keeps the safety guarantee (an LLM can't silently write the truth journal) while letting
> every project's decisions accumulate in one local memory.

## One-time setup (per machine)

Make `projlog` available everywhere:

```bash
pip install -e /path/to/MultiServices-AI
```

Now any project on this machine can write to the shared journal
(`~/.aethercore/journal-llm.jsonl`).

## The convention

Paste this into a project's agent instructions (e.g. its `CLAUDE.md`):

> **Memory capture.** When we make a decision, hit a correction, or reach a validated result,
> record it in the shared memory with a project-namespaced source:
>
> ```bash
> projlog "<the decision/correction/note>" --kind decision --source project:<PROJECT> --session <topic>
> ```
>
> Kinds: `decision` · `correction` · `note` · `hypothesis` · `observation` · `validation`.
> Group a thread under one `--session`; a `correction` in the same session supersedes the earlier
> facts (C3). Querying the memory stays read-only via the MCP — only `projlog` writes.

## Example — project "AetherLife / H3"

```bash
projlog "H3 : architecture retenue = ..." --kind decision    --source project:aetherlife --session h3
projlog "H3 : on suppose que ..."         --kind hypothesis  --source project:aetherlife --session h3
projlog "H3 : mesure terrain = ..."       --kind observation --source project:aetherlife --session h3
projlog "H3 : finalement non, plutot ..." --kind correction  --source project:aetherlife --session h3
```

Then, from any MCP-capable client:

- `recall(source="project:aetherlife")` — only this project's entries, isolated from the rest.
- `brief("h3 ...")`, `lessons()`, `reasoning("h3")`, `recent()` — across the shared memory.

## Scope & limits

- **Same machine** → all projects share `~/.aethercore/journal-llm.jsonl` directly. Works today.
- **Different machines / remote** → you need a sync agent that ships new journal lines to the host
  (the AetherCore "collector/agent" roadmap). Not built here yet.
- The journal is **append-only**: nothing is ever rewritten; corrections close facts, never delete.

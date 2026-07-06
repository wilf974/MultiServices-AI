# Plugging any LLM into MultiService IA

MultiService IA is a **provider-agnostic** memory: any LLM (Claude, ChatGPT, a local Ollama/GGUF
model) — or a human — plugs in via **MCP**, a **REST API**, or plain **files**. The contract is the
same everywhere; only the connector changes. Two invariants hold across all of them:

- **Read-only by default.** Writing is a separate, explicit, human-gated act.
- **No invention.** An empty result is a result — the connector returns it as-is; a missing id is
  reported, never guessed.

> This is the concrete, implementation-grounded integration guide. The abstract, backend-agnostic
> contract (design kit: connector modes, test plan, validation criteria) is maintained separately.

## Three ways to connect

| Connector | Use | How |
|---|---|---|
| **MCP (read)** | Any MCP client (Claude Desktop/Code, Cursor, VS Code…) | `python -m multiservice.mcp_server` (stdio) or the hosted `mem.example.com/mcp` (bearer) |
| **REST web API (read + write)** | Web assistants (ChatGPT / Custom GPT, connectors) | `GET /recall`, `POST /remember`, `GET /recent` + `/openapi.json` (token-authenticated) |
| **Authenticated write (`ingest`)** | Trusted machines writing to a shared journal | `memlog-http` over mTLS + HMAC (source imposed by the client cert's CN) |
| **Files (fallback)** | Cloud LLM with no tool access, or backend unreachable | Paste an export for reading; the human applies proposed writes via a real channel |

## The read surface (tools)

All results carry **provenance** (source, session, dates) and a **freshness** flag (`superseded` /
`corrected_by`). Read tools never mutate the journal (a structural test enforces it).

| Tool | Purpose |
|---|---|
| `recall(query, …)` / `recall_semantic` | Find memories (lexical, or hybrid with local embeddings). Filters: `type`, `source`, structure. |
| `recent(days)` | What's new — the resume entry point. |
| `health()` | Substrate health: availability, event count, latest event, sources. Start a resume with `health → recent → recall`. |
| `replay_event(id, depth)` | The causal chain of an event (what it superseded / what supersedes it). |
| `sources()` / `browse(source, type)` | Map the namespaces / enumerate a project without a query. |
| `why` · `replay` · `brief` · `reasoning` · `lessons` | Explain a turn / session, compose a topic brief, trace a reasoning chain, surface C3 lessons. |
| `index_status()` | Freshness of the semantic index. |
| `curation()` · `project_review(project)` | Health report (duplicates/stale/contradictions) · composed per-project state (valid vs corrected decisions, hypotheses, validations, lessons). |

## Writing (supervised, human-gated)

Writing is never the default. The supported path:

```bash
memlog-http "<a self-contained fact, the why included>" --kind <decision|correction|note|observation|validation|hypothesis> --session <topic-kebab>
# a targeted correction (closes a precise fact — this is the "supersede"):
memlog-http "..." --kind correction --session curation-closures --closes <event-id>
```

- **Source is imposed** by the client certificate's CN — a connector cannot spoof another source.
- **Recall before remember**: check for an equivalent fact first (the server also refuses exact live
  duplicates).
- **Guards at the write path** (refused unless `--force`, human only): **secret values** (API keys /
  tokens — a secret in an append-only journal is unerasable), **unfilled templates**, **exact
  duplicates**.

## Provenance rules

- **Source** — `project:<name>`, `<name>` in kebab-case (e.g. `project:api-web`). A source is a
  project/context, never a model. Reuse an existing source (`sources()`), don't fork variants.
- **Session** — kebab-case topic (e.g. `roadmap-api-web`). One session = one topic; a new topic is a
  new session, even the same day.

## What to log (writeback policy)

Six typed events: `decision` (a choice + its why) · `correction` (a prior entry was wrong; reference
it via `--closes`) · `note` (a durable fact) · `observation` (a verified finding) · `validation` (a
confirmed hypothesis) · `hypothesis` (a supposition to check).

**Never log**: the conversational flow, transient states, paraphrases of what's already there, and
**any secret** (token, password, key, credential). The memory is append-only — a secret written is
unerasable. Write facts that stay useful in six months.

## Modes

| Mode | Read | Write |
|---|---|---|
| `read-only` (default) | Yes | No |
| `supervised-write` | Yes | Proposed, then validated by a human (or a rule) |
| `agentic` | Yes | A local model writes to a **guarded**, non-authoritative namespace (`project:ollama`; observation/note only, deduped) |

## Errors

Structured, never silent. HTTP ingest maps to: `422` (invalid input / template / secret) · `403`
(mTLS / IP not allowed; read surface is read-only) · `409` (nonce replay) · backend unreachable
(connector-level `UNAVAILABLE` / `TIMEOUT`). A missing id → "does not exist", never a guessed one.

## Setup recipes

- Read (MCP): `claude mcp add --transport http multiservice-memory https://mem.example.com/mcp --header "Authorization: Bearer <token>"`
- Write (mTLS): see [`deploy/SETUP-POSTE-CLIENT.md`](../deploy/SETUP-POSTE-CLIENT.md).
- Self-host (Docker + nginx): see [`deploy/`](../deploy/).

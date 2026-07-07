# MultiService IA

> **LLMs forget. Your memory shouldn't.**
>
> *A sovereign memory substrate for LLMs — a force, not a dependency.*

<p align="center">
  <img src="docs/dunkbot-payoff.gif" alt="MultiService IA demo: a stale decision corrected by memory" width="720">
</p>

**Same question. Same history. Two different answers.**  
The difference? One knows a decision has been corrected.

Without memory, the agent re-recommends a **dropped** motor. With MultiService IA, it sees the
decision was **corrected (C3)**, serves the **current truth**, and shows its **provenance** and
**freshness** — memory isn't enough; the edge is **memory + provenance + freshness**.

MultiService IA observes every turn of an LLM conversation (prompt / completion / tool calls /
token usage), remembers it as a dated, sourced, bi-temporal event, and then **restores** it
(recall), **explains** it (why / replay), **economizes** it (caching / context windowing) and
**anticipates** it (pre-heating) — all **locally**, under a strict read-only contract.

It turns a stateless chat into a memory you own: queryable, auditable, and honest about its own
freshness — without ever shipping your data anywhere.

---

## What problem does it solve?

**Without memory:**

- agents repeat abandoned decisions
- context is re-sent every turn
- past reasoning disappears

**With MultiService IA:**

- stale facts are detected
- corrections become first-class events
- every answer can explain where it came from

---

## Why

Conversations with an LLM are ephemeral by default: context is re-sent every turn, knowledge is
lost between sessions, and you can't ask *why* the model said something three days ago.
MultiService IA fixes this with a single, simple idea borrowed from event sourcing: **append every
turn to a local, append-only journal, and never delete anything.** From that journal, everything
else (search, explanation, economy, forecasting) is a pure read.

> Traditional memory answers **"what do I know?"** MultiService IA can also answer **"what is still
> true?"**, **"what was corrected?"**, **"why?"** and **"has this decision been validated?"** —
> through `reasoning()`, `lessons()` and `replay_event()`.

---

## In 30 seconds

```text
Without memory          →  still recommends the NEMA-17 (first idea that comes up)
With MultiService IA    →  detects the NEMA-17 was corrected
                        →  recommends the MG996R + 2:1 gearbox
                        →  explains why (the arm was stalling)
                        →  shows provenance and freshness
```

Most agent memories show diagrams. This one shows a **concrete consequence**: never serving a
decision that has become wrong — without ever losing the history.

---

## Principles (non-negotiable)

These are enforced in code and guarded by tests:

- **Provenance is mandatory.** Every event carries a non-empty `source`. No fact without an origin.
- **Bi-temporality, never deletion.** Events have a `valid_from`; a correction *closes* a fact
  (`valid_to`) but never erases it. Yesterday's truth stays queryable "as it was then."
- **The memory observes; it does not judge or act.** Capture is faithful and total. Filtering
  happens later, at *promotion* and *serving*, gated by a human.
- **Read paths are read-only.** Recall, replay, forecasting and briefing never write the journal,
  never mutate state. A structural test enforces it.
- **Sovereignty.** Inference and embeddings are **100% local** (via [Ollama](https://ollama.com)).
  No hosted inference or embedding API is required or used.
- **Tamper-evident.** An optional hash chain over the journal (`--seal` / `--verify`) makes any past
  edit detectable — the history isn't just un-deleted, it's *provably* un-rewritten.

The healthy separation the project preserves:

> **Capture stores · Recall restores · Replay explains · Preheat anticipates · the Human decides.**

---

## How it works

```
 chat turn ──▶ router ──▶ AetherEvent(s) ──▶ append-only journal (.jsonl)
                                                   │
                          ┌────────────────────────┼─────────────────────────┐
                          ▼                         ▼                          ▼
                   recall / brief            replay / replay_event       forecast / economy
                   (find, read-only)         (explain, read-only)        (anticipate, read-only)
                                                   │
                                          local embeddings (bge-m3)
                                          for hybrid semantic recall
```

Every turn becomes one `prompt`, one `completion` and one `token_usage` event, all sharing a
`turn_id` and a `session_id`. The journal is the single source of truth; the rest of the system is
a set of **pure functions** (`List[AetherEvent] → result`). The only component with side effects
is the inference/embedding backend, deliberately isolated.

---

## Concrete demo — DunkBot 3000 🥞🤖

![Memory Arcade demo](examples/memory_demo/arcade_demo.gif)

A **100% fictional** demo (no real data) shows the value in one shot: **the same question, without
memory then with.** We're building a pancake-flipping robot; on day 1 we decide on a **NEMA-17**
motor, on day 3 the field corrects it (*"it stalls → use an MG996R servo"*).

```bash
python examples/memory_demo/compare.py
```

```text
WITHOUT MultiService IA  (agent with no memory)
  -> Answers blind. At worst, re-recommends the NEMA-17, unaware it was dropped.

WITH MultiService IA  (local memory, read-only)
  brief() — one single call:
    DECISION  [STALE C3 !] : DunkBot ... NEMA-17 ...
    -> revised since (corrected_by): the decision above is NO LONGER the truth.
  CURRENT TRUTH (correction): ... switch to an MG996R servo + 2:1 gearbox.
  Code found (has_code) / Bill of materials (has_table) ... sourced and dated.
```

**The moral:** without memory, the agent may re-recommend the **stale** motor; with memory plus the
bi-temporal **C3** flag, it serves the current truth, sourced and dated.

There's also a fun, self-contained **GUI** (no server): open **`examples/memory_demo/arcade.html`**
in a browser — type a question, see both panels side by side, the stale fact **struck through** (C3),
and the append-only timeline. Details: [`examples/memory_demo/`](examples/memory_demo/README.md).

---

## Dogfooding: the memory remembers its own development

MultiService IA is used to track MultiService IA itself. When the project license changed from
**MIT** to **Apache-2.0**, the old decision was **closed, never deleted**, and `lessons()` surfaced
the current truth.

<p align="center">
  <img src="docs/license-payoff.gif" alt="MultiService IA recalling its own license decision: MIT, corrected to Apache-2.0" width="720">
</p>

Thirty days later, `recall("license")` returns the **current** truth (Apache-2.0) and flags **MIT as
`STALE (C3)`**, while `lessons()` still explains the **why**. Every frame in that clip is a real
event from the journal — not a fictional demo. *(Full 34s video: [`docs/license-demo.mp4`](docs/license-demo.mp4).)*

---

## From Memory to Knowledge

MultiService IA is not just a chat history. Over weeks and months, the journal accumulates
**decisions, corrections, hypotheses, observations and validations** — all typed, sourced and dated.
That lets a **fresh agent session, with no prior context, reconstruct the state of a project from
memory alone.**

<p align="center">
  <img src="docs/from-memory-to-knowledge.png" alt="A fresh agent session with no prior context reconstructs a project's state from memory: current theory, key findings, corrections (STALE C3), rejected hypotheses, mistakes classified into bugs / methodological / negative results, and where to resume." width="760">
</p>

The agent is no longer recalling isolated facts — it is reconstructing the **intellectual history**
of a project: what was believed, what was wrong, what was corrected, what was validated, and *why*.
A search engine returns documents; this returns a **briefing**. That is why events are **typed,
sourced, dated and never deleted**: knowledge emerges from the journal, and the journal stays the
single source of truth.

---

## The memory surface

The substrate exposes a **read-only** surface (e.g. over [MCP](https://modelcontextprotocol.io) to
an MCP-capable client). All results carry provenance and a freshness flag.

| Tool | Purpose |
|---|---|
| `recall(query, …)` | Relevant memories. Filters: type, source, and **structure** (`has_code`, `has_table`). Each hit carries `superseded` / `corrected_by` (was it revised later?). |
| `recall_semantic(query, …)` | Hybrid recall: lexical coverage **+** local semantic embedding, fused and floored to suppress noise. `explain` mode exposes the sub-scores. |
| `sources()` | **Map of the whole memory**: every namespace/source (`project:*`, `llm:*`, …) with its event count — to see *what exists* before searching. |
| `browse(source, type, k)` | **Enumerate without a query**: entries filtered by source/type, most recent first — to explore a whole project where lexical recall wouldn't match. |
| `why(turn_id)` | The events of a single turn — "why the agent saw/said this." |
| `replay(session_id, digest=True)` | Replays a session: a compact one-line-per-turn digest by default, or the full dump. |
| `replay_event(event_id, depth)` | The **causal chain** of an event: focus turn + preceding turns + C3 closure/corrections. |
| `forecast(session_id)` | **Pre-heating**: projects the next turn's cost (snowball vs windowed), read-only estimate. |
| `brief(query, k)` | A composed topic brief in one call: memories + bearing decisions + revised items + sessions. |
| `recent(days)` | **"What's new"**: recent decisions, corrections and latest events — the entry point when resuming work. |
| `reasoning(session_id)` | **Reasoning chain** of a session: hypothesis → observation → decision → correction → validation, ordered, with **present/missing stages** (e.g. a decision with no validation). |
| `lessons()` | **Lessons learned** from C3 corrections: what was revised/abandoned + the truths that still stand. Empty until a correction is logged. |
| `curation(source, …)` | **Health report** (read-only): exact/near duplicates, unfilled templates, stale decisions, contradiction candidates — each with cited evidence and ready closure proposals (`pending_human`). |
| `project_review(project, …)` | **Composed project review** (read-only): reconstructs a project's state from memory alone — valid vs corrected decisions (with the *why*), refuted / standing hypotheses, validations, lessons. Bounded, bi-temporal. |
| `health()` | **Substrate health** (read-only): availability, event count, latest event, distinct sources — the entry point when resuming (`health → recent → recall`). |
| `index_status()` | Freshness of the semantic index (`eligible` / `indexed` / `fresh`). Tells you when semantic recall is partial. |
| `usage()` | **Reuse instrumentation**: how many turns were served from memory (cache, no model call) and input tokens saved. Measures, doesn't predict. |
| resource `briefing/today` | Daily usage briefing (tokens, compaction savings, by model). |

Two human-gated write paths live in the chat loop (not in the read-only surface):

- `/correct <note>` — records a `correction`, marking prior memories of the session as revised (C3).
- `/note <text>` — records an agent-proposed note (`source=agent:claude`), **validated by the human
  who runs the command** (C1). This lets the memory *compound* from the agent's own reasoning,
  while the query surface stays strictly read-only.

---

## Agentic memory — the model searches (and remembers) itself

Beyond the read-only surface, a **local** model (via Ollama function-calling) can drive the memory
**itself**: it decides when it needs a memory, calls `recall` / `sources` / `browse` / `recent` / …,
reads the results and answers — no host-side injection. Every tool call is journaled (`tool_call` /
`tool_result`), so you can audit *what the model searched for*.

It can also **write**, through one guarded tool — `remember(text, kind)`:

- **source is forced** to `project:ollama` (the model can't spoof another source),
- **append-only / bi-temporal** — it records, never deletes,
- **non-authoritative** — kinds limited to `observation` / `note`; authoritative kinds
  (`decision` / `validation` / `correction`) stay **human-gated (C1)**. Model writes are never
  auto-promoted to skills nor served by the decisional cache,
- **deduplicated**.

The model gets a real read+write surface **without** breaking *"the memory observes, the human
decides"*: its writes are source-isolated, non-destructive and non-authoritative. Run it in the chat
loop with `--memory-tools`, or from the local web console (below).

> **Tool sovereignty.** Memory tools are exposed **only for a local turn**. If a turn is routed to a
> cloud provider, no memory tool is exposed and nothing sensitive is embedded in the tool context —
> the memory never leaves the machine.

---

## Multi-provider routing (optional — local-first)

By default everything is local. **Optionally**, a cloud backend can be enabled behind the same
`Backend` interface, governed by a hybrid **"sensitive → local only"** policy:

- **local by default**; a turn goes to the cloud **only if** you explicitly allow it **and** a
  deterministic detector finds nothing sensitive (secrets, PII, unauthorized-access intent).
  *When in doubt: local.*
- if the cloud backend fails, it **falls back to local** — a turn is never lost,
- every routed turn carries **explicit provenance** in the journal (`routed_to`, `routing_reason`,
  `sensitivity_reasons`) — you can always ask *why* a turn went local or cloud.

A `PerplexityBackend` (OpenAI-compatible) ships as the first cloud provider; the interface is
pluggable. Enable with `--cloud` (key via `PPLX_API_KEY`). **Opt-in — the sovereign default is 100%
local.**

---

## Local dev console (web)

A tiny **local-only** web page (Python stdlib, binds `127.0.0.1` — never exposed) to try the model +
memory in a browser: chat with a local model, watch the **model's memory tool calls live**
(recall / remember + results), and toggle `memory-tools` / recall-injection / cloud.

```bash
python -m multiservice.webchat      # http://127.0.0.1:8765
```

The model field accepts an Ollama name **or a path to a `.gguf`** — GGUF models load **in-process**
(`EmbeddedGGUF`, llama-cpp) as a fully-local alternative to Ollama. Everything stays on your machine.

---

## The memory curates itself

Over months the journal accumulates duplicates, reworded re-logs and stale facts. MultiService IA
keeps it clean with a **curation** layer that stays constitutional — it **observes and proposes; the
human decides**. Nothing is auto-deleted; a "fix" is a **C3 closure, never a deletion**.

- **Deterministic detectors** (`curation()` tool / `multiservice.curation_report`) — read-only: exact
  duplicates, near-duplicates, unfilled templates, stale decisions, contradiction candidates, each
  citing its evidence. A **scheduled daily report** stays *quiet unless something is actionable*.
- **Prevention at the source** — the remote-write path (`ingest`) refuses **secret values** (API
  keys / tokens — a secret in an append-only journal is unerasable), **unfilled templates** and
  **exact live duplicates** (same source + kind + text), so that class of pollution can't re-enter
  (`--force` bypasses — human only, C1).
- **A local-LLM comparator** (`multiservice.curation_llm`) — a **local** model (Ollama, never the
  cloud) judges the noisy near-duplicate / contradiction candidates: it **de-noises** false positives
  and proposes **consolidations** (keep the richest existing fact, close the variant). It **proposes,
  never writes** — every proposal is `pending_human` with a ready closure command.

Approving one is a **C3 closure** (`memlog-http … --closes`): the variant is closed, never deleted;
the canonical stays the current truth. The loop: **detect → judge (local LLM) → prevent → monitor →
the human approves.**

---

## Token economy

Real measurements on live conversations showed that up to **98.5% of input tokens** were context
re-sends (the "snowball" of growing context) rather than new information. MultiService IA attacks
this waste with three read-only-friendly levers:

- **Exact result cache** — identical requests are served without calling the model (C3-guarded:
  a later correction invalidates the entry).
- **Semantic cache** — near-paraphrases of an already-answered prompt are served without the model.
  Decisional, so a deliberately high similarity threshold ("when in doubt, don't serve").
- **Context windowing** — keeps the last *N* turns in clear, bounding the snowball.

Crucially, the savings aren't *claimed* — they're **measured**, read-only, by the `usage()` tool:
how many turns were served from memory, and how many input tokens were actually saved.

> **Live measurement** (one real journal): 199 turns · 595 input tokens saved by windowing ·
> 16 saved by the semantic cache (only recently enabled). *Your numbers depend on usage patterns —
> the point is that they are measured, not asserted.*

---

## Sovereignty & privacy

- Everything runs **on your machine**. The journal lives in a local append-only file.
- Inference and embeddings go through a **local Ollama** instance — no hosted API.
- A routing policy keeps **sensitive content off hosted providers**: anything flagged as a
  secret/credential or an unauthorized-access intent is never routed to a cloud inference/embedding
  API, and is never served from cache. (When in doubt: local.)
- **Sovereignty vs. replication.** The claim above is about *inference routing*. The **optional**
  central server replicates the journal to a host **you** control (opt-in, union-by-id merge) — not a
  third party; it does **not** filter on sensitivity, but the write path **refuses secret values**, so
  credentials never enter the journal to begin with.
- **This repository ships no data.** Your journal is yours and stays on your disk.

---

## Quick start

Requirements: Python 3.11+, [Ollama](https://ollama.com) running locally.

```bash
# 1. install
pip install -r requirements.txt

# 2. pull a local chat model and an embedding model
ollama pull <your-chat-model>      # any local model; set via OLLAMA_MODEL
ollama pull bge-m3                  # local embeddings for hybrid recall

# 3. chat (capture is automatic; exact + semantic cache and windowing are ON by default)
python -m multiservice.chat --ollama --recall     # add --recall for live memory injection

# 4. (re)build the semantic index after chatting
python -m multiservice.index

# 5. run the tests
pytest -q
```

Configuration lives in `multiservice/config.py` and is overridable via environment variables
(`OLLAMA_MODEL`, `EMBED_MODEL`, `JOURNAL_PATH`, `KEEP_TURNS`, …).

---

## Tutorial — write → correct → recall in 5 minutes

The heart of MultiService IA is the bi-temporal loop: log a fact, correct it later, and watch the
memory serve the **current** truth while keeping the old one queryable. No cloud, no API keys — and
this walkthrough writes to a throwaway `tuto.jsonl`, so it never touches your real journal.

**1. Install** (and make `projlog` available everywhere)

```bash
pip install -r requirements.txt
pip install -e .
pytest -q                 # optional — watch the invariants pass
```

**2. See the payoff instantly** (no model needed — a fictional demo, same question without vs with memory)

```bash
python examples/memory_demo/compare.py
```

**3. Log your own decision — then let reality correct it**

```bash
projlog "Use a NEMA-17 motor for the arm" --kind decision \
  --source project:tuto --session arm --journal ./tuto.jsonl
# a day later, the field corrects it:
projlog "NEMA-17 stalls -> switch to an MG996R servo + 2:1 gearbox" --kind correction \
  --source project:tuto --session arm --journal ./tuto.jsonl
```

**4. Watch bi-temporality** — the old decision is no longer served, the correction is, and nothing was deleted

```bash
python -c "import json; from multiservice.journal import read_events; from multiservice import memory; \
print(json.dumps(memory.lessons_learned(read_events('tuto.jsonl'), source_prefix='project:tuto'), indent=2, ensure_ascii=False))"
```

You'll see the **lesson** (what was revised + the current truth). The NEMA-17 decision fell; the
correction stands — but the original is still there in `tuto.jsonl`, queryable *as of* any past date.

**5. Chat with your memory injected** (needs a local Ollama model)

```bash
ollama pull <your-chat-model> && ollama pull bge-m3
python -m multiservice.chat --ollama --recall     # capture is automatic; --recall injects memories
```

**6. Keep it clean — validate curation in one click**

```bash
python -m multiservice.curation_inbox --journal ./tuto.jsonl   # http://127.0.0.1:8766
```

**7. Plug your own LLM in** — MCP / REST / files: see [`docs/INTEGRATION.md`](docs/INTEGRATION.md).

---

## Using it from an MCP client

> **Plug any LLM in.** Full connection guide — MCP / REST / files, read + supervised write, tools,
> provenance rules, writeback policy, modes — in **[`docs/INTEGRATION.md`](docs/INTEGRATION.md)**.

Run the read-only memory server:

```bash
python -m multiservice.mcp_server
```

Then point an MCP-capable client at it. A minimal client config looks like:

```json
{
  "mcpServers": {
    "multiservice-memory": {
      "command": "/absolute/path/to/python",
      "args": ["-m", "multiservice.mcp_server"],
      "env": { "PYTHONPATH": "/absolute/path/to/this/repo" }
    }
  }
}
```

> The server caches modules at import; restart the client after adding tools.

### Remote access (hosted HTTP server) — optional

> **Optional, opt-in.** By default the memory is **local and sovereign** — the stdio server above
> keeps everything on your machine and nothing requires a server. Centralizing the journal on a VPS
> is only for those who *want* to reach one shared journal from several machines/networks.

If you opt in, the same read-only surface is served over **HTTPS** — one central journal, no copy on
the clients (the data stays on a host *you* control). Run the streamable-HTTP entrypoint (behind a
reverse proxy that terminates TLS and authenticates):

```bash
multiservice-mcp-http   # read-only tools over streamable-HTTP (default 0.0.0.0:8302)
```

DNS-rebinding protection stays **on**: declare the public Host(s) you serve via
`MULTISERVICE_HTTP_ALLOWED_HOSTS` (comma-separated, e.g. `mem.example.com`). Put it behind a reverse
proxy adding TLS + a bearer token + an IP allowlist, then connect any machine:

```bash
claude mcp add --transport http multiservice-memory https://mem.example.com/mcp \
  --header "Authorization: Bearer <token>"
```

A ready-to-use recipe (Docker with the journal mounted **read-only** + nginx) is in [`deploy/`](deploy/).

> **Semantic is local; a GPU-less central stays lexical.** Embeddings (`bge-m3`) are computed on the
> machine that has the GPU — your workstation. A central server without a GPU serves the read-only
> surface with **lexical** recall (still sourced, dated, C3-aware); hybrid *semantic* recall is a
> local capability. This is by design: the sovereign path is local, and the central server is an
> **option** for reaching one shared journal — not a requirement, and not where the model runs.

**Authenticated remote write (ingest).** Remote machines can also *write* to the central journal over
**mTLS + HMAC** (nonce + timestamp anti-replay); the source is imposed server-side from the client
certificate's CN — a client can never spoof it. Client command: `memlog-http`. Recipe in
[`deploy/`](deploy/) (`Dockerfile.ingest`, `gen-mtls.sh`).

**Web REST API (for web LLMs).** A separate **public, token-authenticated** REST surface lets web
assistants (ChatGPT / Custom GPT, connectors) read and write the central memory: `GET /recall`,
`POST /remember`, `GET /recent`, plus an auto **OpenAPI** schema (`/openapi.json`) for GPT Actions.
Each client's bearer token maps to a source (imposed server-side). Central-only, rate-limited. Recipe
in [`deploy/`](deploy/) (`Dockerfile.webapi`) and [`deploy/SETUP-POSTE-CLIENT.md`](deploy/SETUP-POSTE-CLIENT.md).

---

## CLI

```bash
python -m multiservice.chat        # chat loop (captures + journals every turn)
python -m multiservice.chat --memory-tools --cloud   # agentic memory + optional cloud routing
python -m multiservice.webchat     # local-only web console (Ollama/GGUF + live memory activity)
python -m multiservice.inspect     # usage observability (read-only)
python -m multiservice.economy     # token accounting: prefix re-send, windowing savings
python -m multiservice.index       # incremental local embedding (re)index
python -m multiservice.maintenance # incremental reindex, schedulable (keeps the index fresh)
python -m multiservice.curation_report  # daily curation health report (deterministic, read-only)
python -m multiservice.curation_llm     # local-LLM review: de-noise + consolidation proposals
python -m multiservice.curation_inbox   # local web inbox: approve/reject curation proposals in one click
python -m multiservice.preheat     # pre-heating: projected cost of the next turn
python -m multiservice.mcp_server  # read-only MCP memory server
python -m multiservice.integrity   # tamper-evident hash chain: --seal / --verify the journal
python -m multiservice.procedural  # procedural memory: recurring successful tool-sequences -> playbooks
python -m multiservice.memeval     # memory eval: recall@k on a golden set auto-built from corrections
python -m multiservice.projlog "<decision>" --kind decision --session <topic>   # log a project decision
```

In the chat loop: `/correct <note>`, `/note <text>`, `/model <name|path.gguf>`, `/reset`, `/quit`.

> **Keeping the index fresh, automatically.** `multiservice.maintenance` reindexes only what changed
> and is meant to be scheduled (a Windows scheduled task / cron), so hybrid recall stays fresh with
> no manual step. Semantic embeddings are a **local (GPU)** capability — see the note under
> *Remote access* on why a GPU-less central server stays lexical.

> **Shared memory across projects.** Run `pip install -e .` to make the `projlog` command available
> everywhere on the machine; any project can then feed the same local journal with a namespaced
> source (`projlog "…" --source project:<name> --session <topic>`), isolable via
> `recall(source="project:<name>")`. The query surface stays read-only — only capture writes. See
> [`docs/CAPTURE-CONVENTION.md`](docs/CAPTURE-CONVENTION.md).

> **Dogfooding.** `projlog` writes the project's own decisions/corrections into the journal, so
> `recall`/`brief`/`recent` can ground future work in past reasoning — the memory remembers its own
> development. It's a capture (append-only); the MCP query surface stays read-only.

---

## Project status

Working engine with a full read-only memory surface, **agentic memory** (the model searches and
writes its own `project:ollama` namespace, guarded), **local-first multi-provider routing** (optional
Perplexity cloud behind a "sensitive → local" policy), a **local web console** (Ollama + GGUF), exact
+ semantic caching, context windowing, emergent-skill scaffolding, append-only backup with SHA-256
manifests, local hybrid recall, **schedulable reindexing**, and a **self-curating** layer
(deterministic detectors + scheduled report, ingest-time dedup/template guards, and a local-LLM
comparator that de-noises and proposes consolidations — all human-gated, C3). Everything runs
**locally by default**; the hosted central server (HTTP read + mTLS ingest + web REST API) is an
**opt-in option** for sharing one journal across machines. **Covered by a growing pytest suite
(currently green).** Each feature ships with a permanent regression test; every issue surfaced by
real usage becomes a test.

---

## Roadmap

- ✅ **Multi-provider routing** — shipped: optional cloud backend (Perplexity) behind the same
  interface, governed by the "sensitive → local only" policy, with explicit routing provenance.
- ✅ **Agentic memory** — shipped: the local model drives the memory tools itself and can write to a
  guarded, non-authoritative `project:ollama` namespace; memory tools stay local-only.
- ✅ **Local web console** — shipped: `multiservice.webchat`, Ollama/GGUF + live memory activity.
- ✅ **Schedulable reindexing** — shipped: `multiservice.maintenance`, incremental, keeps recall fresh.
- ✅ **Self-curating memory** — shipped: deterministic detectors + scheduled report, ingest guards
  (exact-dedup + unfilled-template), and a local-LLM comparator (de-noise + consolidation proposals),
  all human-gated (C3 closure, never deletion).
- ✅ **A second (hosted) read-only surface** — shipped: streamable-HTTP server, see [`deploy/`](deploy/).
- ✅ **Authenticated remote write (ingest)** — shipped: mTLS + HMAC + anti-replay, `memlog-http` client.
- ✅ **Web REST API for web LLMs** — shipped: public, token-authenticated FastAPI (recall/remember/recent
  + OpenAPI), Custom GPT-ready. See [`deploy/`](deploy/).
- ✅ **Project review (Synthesis role)** — shipped: `project_review(project)` reconstructs a project's
  bi-temporal state (valid vs corrected decisions with the *why*, hypotheses, validations, lessons).
- ✅ **Secret guard at write** — shipped: the write path refuses credential values (a secret in an
  append-only journal is unerasable); `--force` bypasses (human, C1).
- ✅ **Integration guide** — shipped: [`docs/INTEGRATION.md`](docs/INTEGRATION.md) — plug any LLM in
  (MCP / REST / files, read + supervised write).

### On the roadmap

- **At-rest encryption** of the local journal (append-only + encryption — a deliberate effort).
- **Multi-node hardening** — per-client certificate revocation and rate-limiting.
- **Scaling** to very large, long-lived journals — indexed / paginated storage (optional graph back-end).
- **Comparator calibration** — honor rejects, ignore versioned / distinct-location variants.

---

## Design lineage

The constitutional principles (mandatory provenance, bi-temporal closure-never-deletion,
human-in-the-loop) are inherited from a companion bi-temporal event-sourcing system and applied
here to LLM exchanges. The result is a memory that is faithful by capture and trustworthy by
construction.

---

## License

**Apache License 2.0** — see [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE). Permissive (free for
commercial use), with an explicit patent grant. © 2026 MultiService IA authors.

---

## A note on your data

MultiService IA is designed so that your conversation history never leaves your control. The code
in this repository describes the *system*, not your memory: no journal content is bundled, and none
should be committed. Keep your `*.jsonl` journals out of version control (add them to
`.gitignore`).

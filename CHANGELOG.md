# Changelog

All notable changes to MultiService IA are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/). Versioning: [SemVer](https://semver.org/)
(pre-1.0: the API may still change between minor versions).

## [Unreleased]

### Added

- **Integration guide** (`docs/INTEGRATION.md`) — how any LLM (Claude / ChatGPT / local Ollama) or a
  human plugs into the memory: MCP / REST / files connectors, the read tools, supervised write
  (source imposed by cert; secret / template / duplicate guards), provenance and writeback rules, the
  three modes, and error semantics.

## [0.2.0] — 2026-07-06

Self-curating, multi-provider memory: the substrate now cleans itself, judges with a **local** LLM,
and reconstructs a project's state — while staying sovereign (local by default) and human-gated.

### Added

- **Multi-provider routing** — optional cloud backend (Perplexity, OpenAI-compatible) behind the
  same interface, governed by a "sensitive → local" policy; every routed turn carries explicit
  provenance; local fallback on backend error.
- **Agentic memory** — a local model drives the memory tools itself (function-calling) and can write
  to a guarded, non-authoritative `project:ollama` namespace (source-forced, append-only, deduped).
  Memory tools are exposed for **local turns only**.
- **Local web console** (`multiservice.webchat`) — try the model + memory in a browser (binds
  `127.0.0.1`), with live memory tool-call activity; accepts an Ollama name **or a `.gguf` path**
  (in-process `EmbeddedGGUF`).
- **Self-curating memory**:
  - deterministic detectors + `curation()` MCP tool + schedulable daily report
    (`multiservice.curation_report`);
  - **ingest-time guards** — the remote write path refuses exact live duplicates and unfilled
    templates (`--force` bypasses, human only);
  - a **local-LLM comparator** (`multiservice.curation_llm`) that de-noises near-duplicate /
    contradiction candidates and proposes consolidations. All `pending_human`; closure is C3, never
    deletion.
- **`project_review()`** — composed, bi-temporal per-project review (valid vs corrected decisions
  with the *why*, refuted / standing hypotheses, validations, lessons). MCP tool.
- **Read surface** — new `curation` and `project_review` tools; agentic `sources` / `browse`.
- **Schedulable reindexing** (`multiservice.maintenance`) — incremental, keeps hybrid recall fresh.
- **Hosted surfaces (opt-in)** — streamable-HTTP read server; authenticated remote write (`ingest`,
  mTLS + HMAC + anti-replay, `memlog-http` client); public token-authenticated web REST API
  (recall/remember/recent + OpenAPI, Custom-GPT-ready). Local↔central sync via union-by-id merge.

### Changed

- `looks_like_placeholder` hardened — a real doc that *documents* `<...>` examples is no longer
  flagged (only short texts, or texts *dominated* by `<...>`).
- `OllamaEmbedder` truncates inputs to 6000 chars (llama-server context) + `build_index` default
  batch 4.
- `project_review` correction signal **refined** — a correction supersedes only the immediately
  preceding fact of its session (not all of them), plus targeted closures.

### Notes

- The sovereign default stays **100% local**; the hosted central server is an **option**.
- Covered by a green pytest suite; each feature ships with a permanent regression test.

## [0.1.0] — 2026-06-19

First public release: a sovereign, local-first, bi-temporal memory substrate for LLMs.

### Added

- **Capture** — every conversation turn becomes `prompt` + `completion` + `token_usage`
  events, sharing a `turn_id`/`session_id`, written to a local append-only journal.
- **Constitution** — mandatory provenance (C2) and bi-temporality (C3: a correction *closes*
  a fact, never deletes it). Read paths are pure and read-only (structural test).
- **Read-only memory surface** (MCP): `recall` (lexical, with `type`/`source`/`has_code`/
  `has_table` filters and `superseded`/`corrected_by` freshness), `recall_semantic` (hybrid
  lexical + local embedding), `why`, `replay` (digest or full), `replay_event` (causal chain),
  `forecast` (next-turn pre-heating), `brief` (composed topic brief), `recent` ("what's new"),
  `index_status` (semantic-index freshness), and the `briefing/today` resource.
- **Token economy** — exact result cache and decisional semantic cache (both C3-guarded),
  plus context windowing.
- **Sovereignty** — inference and embeddings 100% local (Ollama); a routing policy keeps
  sensitive content local by construction.
- **Human-gated capture** — `/correct` and `/note` (chat), and `projlog` to record the
  project's own decisions/corrections into the journal (dogfooding); the query surface stays
  read-only.
- **Availability** — append-only backup with SHA-256 manifests.
- **Demo** — fictional "DunkBot 3000" example: `compare.py` (without vs with memory) and a
  self-contained `arcade.html` GUI.
- **Docs** — README (EN/FR), architecture/vision docs, Apache-2.0 license.

### Notes

- No conversation data is shipped in this repository; journals stay on your machine.
- Covered by a green pytest suite; each feature ships with a permanent regression test.

[Unreleased]: https://github.com/wilf974/MultiServices-AI/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/wilf974/MultiServices-AI/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/wilf974/MultiServices-AI/releases/tag/v0.1.0

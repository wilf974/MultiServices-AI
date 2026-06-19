# Changelog

All notable changes to MultiService IA are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/). Versioning: [SemVer](https://semver.org/)
(pre-1.0: the API may still change between minor versions).

## [Unreleased]

- Nothing yet.

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

[Unreleased]: https://github.com/wilf974/MultiServices-AI/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/wilf974/MultiServices-AI/releases/tag/v0.1.0

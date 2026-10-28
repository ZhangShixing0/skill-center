# Data and safety policy

## Stored locally

- Skill name, description, Skill-folder path, source category, content hash, project origin, duplicate relationship, and sync state.
- Presence state, platform first-discovery time, source-file modified time, last confirmed presence, confirmed-removal time, and the first/last observation time for each distinct content hash.
- Local scan-source labels, enable states, modes, ignore-directory names, and absolute paths.
- User-curated display metadata and classification hints in `personal-catalog.local.json`.
- Optional machine-specific source-review suggestions in `classification-suggestions.local.json`, including a proposed classification, confidence, short evidence, and upstream attribution clues. These are review inputs, not confirmed classifications.
- While the local server is running, its PID, port, URL, and a random local-session token in `server-runtime.json`; the file is removed on a clean stop.
- Invocation timestamp, explicit or implicit trigger, Skill version hash, and an optional short task category.
- Optional opaque run ID, workflow template ID, step position, and controlled step outcome. These fields describe structure only, not task content.
- A locally salted workspace fingerprint, friendly local alias, and context kind such as project or standalone. The fingerprint cannot be reversed into a path and is not intended to match across machines.
- User-entered outcome (`solved`, `partial`, or `failed`) linked to a specific invocation when available, plus optional rating, controlled experience tags, and a short note.
- Improvement proposal title, rationale, status, and timestamps.

## Never stored

- User prompts or conversation messages.
- Model responses or generated artifacts.
- Task-specific file contents.
- Invocation workspace absolute paths. A path may be supplied transiently to the loopback service so it can derive the local fingerprint and alias, but the path is discarded and is not returned by usage or detail APIs.
- Task filenames, free-form task descriptions, shell history, or command output.
- Task titles, prompts, filenames, user names, or other content encoded inside run IDs.
- Third-party authentication tokens, credentials, or remote telemetry.
- Contents or filenames from unrelated task workspaces. Only configured Skill folders are inspected.

## Classification

- `self-authored`: created by the user.
- `adapted`: customized from an upstream skill; retain source attribution.
- `public-installed`: installed from a public repository or catalog.
- `system`: bundled system skill.
- `plugin`: skill supplied by an installed plugin.
- `unknown`: personal-root candidate awaiting user confirmation.

Path location is evidence of installation scope, not proof of authorship. Keep new personal-root discoveries as `unknown` until the user classifies them.

Existence is independent from installation scope and authorship:

- `current`: an indexed location whose `SKILL.md` was confirmed present. Confirmed original, adapted, and project-incubated entries may appear in **我的 Skills**.
- `ownership inbox`: a current personal-root entry whose authorship is still `unknown`. It does not belong to the confirmed current list yet.
- `removed`: an indexed location whose `SKILL.md` was confirmed missing. It appears only in read-only removed history, never in current lists, the ownership inbox, invocation selection, or improvement actions.

A lightweight service-start reconciliation may check previously indexed `SKILL.md` paths and mark missing entries removed; a full source rescan remains explicit. Removed rows are not deleted because usage, feedback, project alias, source provenance, and observed-version history may still be useful. If the location reappears, it becomes current again and the removal timestamp is cleared.

`discovered_at` means the first time this local Skill Center observed the Skill, not when the author created it. `modified_at` is the observed source-file modification time and may also be incomplete. The dashboard must say **unrecorded** rather than invent a creation date when no authoritative evidence exists.

Project Skill roots are explicit configuration. Do not infer authorization to scan the user's entire Documents folder. Identical project/global locations may be grouped, but both paths and their content hashes remain traceable.

The source-review endpoint may suggest a classification only for primary personal entries that are still `unknown`. Suggestions must show confidence and evidence. Preview uses a read-only database connection and performs no writes. Applying a batch requires the exact preview token and explicit selected Skill IDs; the token is invalid after a classification, content hash, target classification, or upstream field changes. A successful apply updates only local classification metadata and never edits a Skill source file.

## Local configuration and public packaging

- Store machine-specific source configuration at `SKILL_CENTER_HOME/data/scan-sources.local.json`.
- Treat `SKILL_PROJECT_ROOTS` as environment-managed input. Display it, but never persist its paths through the HTML settings page.
- Store the isolated v2 SQLite database, workspace aliases, usage log, feedback, proposals, personal catalog, machine-specific classification suggestions, and local dashboard state under `SKILL_CENTER_HOME`.
- Treat last-used time, recent project alias, and project count as partial recorded coverage beginning when local usage logging was enabled; never present them as a complete usage history.
- Treat curated workflow templates as recommendations. Only invocation rows sharing the same non-empty opaque run ID may count as observed co-use; never infer a workflow from timestamps or workspace proximity.
- Keep `assets/config/scan-sources.example.json` free of usernames, drive letters, absolute project paths, and private source labels.
- A GitHub release may include the Skill package and the generic example. It must exclude the runtime center, `scan-sources.local.json`, `project-roots.json`, `personal-catalog.local.json`, `classification-suggestions.local.json`, `server-runtime.json`, SQLite/WAL/SHM files, server logs, usage and feedback data, screenshots, browser-smoke output, approval manifests, and `.execution` records.
- A downloaded copy auto-detects standard Codex locations. Each user configures project paths on the **扫描来源** page.
- The shareable-template endpoint exports only generic automatic-source switches, an empty project-source list, and safe default ignore names.

## Public source verification

A URL found in a plugin manifest is a candidate source, not proof that it is public or authoritative. Only links listed as verified in `assets/catalog/public-sources.json` may be opened from the public dashboard.

The public dashboard uses four source states:

- `verified`: a human-verified public upstream URL; clickable.
- `candidate`: a plausible upstream URL that has not yet been verified; visible but not clickable.
- `bundled`: supplied by Codex without a separately verified public upstream page; visible but not clickable.
- `missing`: no usable address exists in the current metadata; visible but not clickable.

## Public localization catalog

- `assets/catalog/public-skills.zh-CN.json` is packaged, path-free display metadata and may be published with the Skill.
- It stores the public Skill name, Chinese display name, Chinese summary, concise usage guidance, and a `source_hash` copied from the upstream content hash. It does not store local paths, usage records, feedback, private classifications, or project configuration.
- The English upstream `SKILL.md` remains the fact source. The Chinese catalog is a read-only presentation layer and never authorizes modifying a system, plugin, or public-installed Skill.
- If `source_hash` no longer matches the current upstream content hash, the dashboard labels the localization as stale and keeps the English original available until the Chinese text is reviewed.
- Source verification and localization are independent: a Skill may have current Chinese text while its source is still a non-clickable candidate, bundled source, or missing source.

## Approval boundary

Aggregate feedback into a proposal, show the proposed diff, and request explicit approval. Only then back up and modify a personal Skill. Project-to-global promotion follows the same boundary: show source, target, hash, file list, portability, and conflicts first; copy only after explicit approval. Source classification follows a lighter but still explicit boundary: suggestions and previews are read-only, and only the entries submitted with a current preview token may update local classification metadata. Never mutate plugin caches or system Skills in place.

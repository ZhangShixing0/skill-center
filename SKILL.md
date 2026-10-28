---
name: skill-manager
description: Manage a local Codex skill library with separate current, ownership-inbox, removed-history, and public views; portable source settings; lifecycle and observed-version tracking; one-click background startup; doctor and recovery commands; read-only preview; atomic local rescans; project/global source tracking; duplicate grouping; privacy-preserving recorded-usage logging; feedback; snapshot diffs; and approval-gated promotion or improvement. Use when the user asks to start or recover the Skill Center, configure where Skills are scanned, rescan, inventory, classify, rank, review, visualize, trace when and where a Skill was observed or recorded as used, distinguish uninstalled from current Skills, copy project Skills into the global library, compare Skill copies, publish a path-safe package, or safely improve personal, project, system, or plugin Skills.
---

# Skill Manager

Manage the user's local Skill library as a source-aware capability graph without collecting prompt or conversation content.

## Core workflow

1. Open the dashboard with `open-skill-center.cmd` or `python scripts/skill_center.py start --open`. If it does not open, run `python scripts/skill_center.py doctor`.
2. Open **扫描来源** or read the current configuration with `python scripts/configure_project_roots.py --list`.
3. Keep standard Codex locations automatic. Add only explicit project Skill roots that the user placed in scope. Choose `skill-container` for direct child Skill folders or `single-skill` when the selected folder itself contains `SKILL.md`.
4. Preview every source change before saving. Treat preview as strictly read-only: it may inspect paths and count candidates, but it must not write the SQLite index or modify any Skill file.
5. Run `python scripts/scan_skills.py`, or click **重新扫描本地 Skills**, to refresh personal, project, system, plugin, and compatible Agents locations. Show added, content-updated, removed, unchanged, and duplicate-location counts; group content-identical copies instead of double-counting them.
6. Treat installation scope and authorship as separate facts. Show confirmed original, adapted, and project-incubated entries in **我的 Skills**; put present personal-root entries with `unknown` authorship in **待认领**. Review the evidence and confidence for each suggestion, select only the entries the user accepts, preview the exact classification changes, and wait for the user to click the final apply action. Suggestions and previews are read-only.
7. Put missing indexed Skills in **已移除** after a scan or lightweight startup reconciliation confirms that their `SKILL.md` no longer exists. Never show an uninstalled Skill in the current library or ownership inbox. Preserve its local history and expose a read-only detail page; do not read, execute, improve, sync, or reclassify a missing file.
8. Use **开始使用** to search from a goal, continue the most recently recorded Skill, enter a curated multi-Skill workflow, or browse the current personal library. Keep the inventory summary visible, but put full trends, projects, outcomes, coverage, lifecycle, and attention queues in **统计洞察**.
9. Use **Public Skills** as a read-only upstream index. Default to the packaged Chinese display layer, keep the English upstream text available for fact checking, and search both languages. Distinguish verified, candidate, bundled, and missing sources; make a link clickable only when its URL is in the verified source catalog. A URL merely present in a plugin manifest is not verification.
10. Use **工作流** for cross-Skill pipelines. Keep curated templates in `assets/catalog/workflows.json` and optional local overrides in `SKILL_CENTER_HOME/data/workflows.local.json`. Label templates as **作者建议组合**. Never present them as observed behavior.
11. Log an actual invocation with `python scripts/log_usage.py --skill <name> --invocation explicit|implicit`. The logger prefers the running loopback service and falls back to the local database. It records the Skill, timestamp, invocation type, version hash, an optional task category, and a salted workspace fingerprint with a local alias; it never persists the workspace path. When multiple Skills belong to the same task, pass the same opaque `--run-id`, an optional `--workflow`, and `--step`. Only those shared identifiers may feed co-use statistics.
12. On the personal Skill detail page, review **最近调用与使用感受**. Link feedback to the exact invocation and require only `solved`, `partial`, or `failed`; keep the controlled experience tags, rating, and short note optional. Show participating cross-Skill workflows separately from the Skill's internal workflow. Label all dashboard totals as **recorded usage** and disclose partial coverage; never imply that the log captures every Skill invocation.

## Scan-source configuration

- Store effective absolute paths only in `SKILL_CENTER_HOME/data/scan-sources.local.json`.
- Treat `SKILL_PROJECT_ROOTS` entries as environment-managed and read-only. Show them in preview, but never copy them into the saved configuration.
- Keep `assets/config/scan-sources.example.json` generic and path-free. New installations must start with no project paths.
- Support enable, disable, add, edit, and remove operations for local project sources.
- Require an exact preview token when saving from the HTML. Reject a stale token after any form change.
- Reject filesystem roots, the user home, the whole Documents/Desktop directory, the Codex root, common system roots, duplicate project paths, and any project path overlapping an automatic Codex location.
- Do not recursively crawl a project source. `skill-container` reads only `root/*/SKILL.md`; `single-skill` reads only `root/SKILL.md`.
- Bound source counts and skip symlinked children, VCS directories, dependency folders, virtual environments, and caches.
- Keep the legacy `project-roots.json` loader for migration, but write new configuration only to `scan-sources.local.json`.

## HTML update boundary

- The **重新扫描本地 Skills** button may rescan only the configured global, environment-managed, and project roots and update the local SQLite index. It does not download or upgrade Skill content.
- Persist the latest scan delta so a restart does not replace a meaningful update result with an automatic no-change scan.
- A personal-folder location is not proof of authorship. Keep present unconfirmed entries as `unknown` in a separate ownership inbox; do not include them in the confirmed current list.
- Treat existence as a separate dimension from source scope and authorship. Current lists default to `is_present=1`; removed history uses `is_present=0` and must never feed current counts, ownership review, invocation selection, or improvement actions.
- On service startup, a lightweight reconciliation may check only previously indexed `path/SKILL.md` files and mark missing rows removed. A full rescan remains an explicit inventory action.
- Preserve lifecycle rows and observed content hashes when a Skill disappears. Set `removed_at` when absence is first confirmed, retain `last_seen_at`, usage, feedback, recent project alias, and observed versions, and clear `removed_at` if the same location reappears.
- Use `discovered_at` only as **platform first discovery**. Filesystem modification time is not guaranteed authorship history, and neither value may be presented as the Skill's true creation time without separate evidence.
- Source-review suggestions must be explainable with visible evidence and a confidence label. High confidence may be preselected in the form, but preselection is not authorization to write.
- Generate classification previews from a read-only database connection. Bind the preview token to the current classification, content hash, requested target, and upstream fields so any intervening edit invalidates it.
- Apply only explicitly selected personal `unknown` entries after a matching preview token is submitted. Never include project, system, plugin, or already-classified Skills in the batch.
- Batch classification may update the local SQLite index and `personal-catalog.local.json`; it must not edit, move, delete, or rewrite any Skill source file.
- Updating the inventory must never edit, copy, delete, or rewrite a Skill source folder.
- Updating Skill content remains a separate workflow: collect feedback, generate a proposal and exact diff, wait for explicit approval, then validate the approved change.

## Public library localization

- Keep Chinese public-library display metadata in `assets/catalog/public-skills.zh-CN.json`. This catalog is packaged and shareable; it must contain only public-facing names, descriptions, usage guidance, and the upstream content hash.
- Treat the English name and description extracted from each upstream `SKILL.md` as the fact source. Localization is a read-only overlay and must never rewrite a system, plugin, or public-installed Skill.
- Bind each localization entry to the upstream `content_hash` through `source_hash`. If the hashes differ after a rescan, label the Chinese entry as **待复核** and keep the English original available.
- Default the public dashboard to Chinese, allow an explicit **英文原文** switch, and let search match both Chinese display fields and English upstream fields.
- Represent provenance with four visible text states: `verified`（来源已验证）, `candidate`（来源待验证）, `bundled`（Codex 系统内置）, and `missing`（来源尚未找到）. Color may reinforce a state but must not be its only signal.
- Only `verified` sources may be clickable. Show a candidate host when useful, but keep it non-clickable until a person verifies the upstream page and adds it to `assets/catalog/public-sources.json`.
- Never add machine paths, runtime records, usage data, private classification suggestions, or project-specific labels to the packaged localization catalog.

## Project Skill promotion

1. Treat the project copy as the fact source until the user approves a global snapshot.
2. Generate a strictly read-only plan with `python scripts/plan_promotions.py --skill <name>`. It opens the existing SQLite inventory with `mode=ro`; use `--refresh` only when a metadata refresh is intentionally allowed.
3. Stop on `blocked-project-bound`, `review-required`, or `name-collision`; never replace a same-named global Skill silently.
4. Present the source, target, content hash, file list, portability result, and exact diff. Wait for explicit approval.
5. Only after approval, run `python scripts/promote_snapshot.py --skill <name> --apply --approval-token APPROVED`. Apply mode refreshes the inventory before copying; dry-run mode stays read-only unless `--refresh` is supplied.
6. Register the project origin hash after copying. Future scans must report `current`, `update-available`, `snapshot-modified`, or `diverged` and offer a diff; never synchronize both directions automatically.

## Safety rules

- Bind the dashboard to `127.0.0.1` only.
- Require a same-origin local session token for every write request, validate the Host header, serialize scans, and never return internal exception details to the browser.
- Store v2 data in `skill-center-v2.sqlite3`; migrate a legacy database with SQLite backup instead of sharing a mutable file with older scripts.
- Keep user-curated descriptions and confirmed classifications in `SKILL_CENTER_HOME/data/personal-catalog.local.json`. Machine-specific review hints may live in `SKILL_CENTER_HOME/data/classification-suggestions.local.json`; never treat that file as confirmed classification and never ship it in the package.
- Bound recursive file enumeration and hashing by file count, per-file bytes, and total bytes.
- Restore the previous scan-source configuration if the post-save scan fails.
- Before publishing the Skill Manager package, apply the exclusions in `assets/config/repository.gitignore.template` and exclude the runtime center, SQLite files, local source configuration, local classification suggestions, usage and feedback data, screenshots, test output, approval manifests, and execution-cockpit records.
- The packaged `assets/catalog/public-skills.zh-CN.json` is intentionally shareable. Validate that it contains no absolute path or runtime/private fields before publishing.
- Export only the packaged path-free example when another user needs a configuration template. Never copy `scan-sources.local.json` into GitHub.
- Usage logging must never store prompts, messages, generated answers, filenames from the user's task, or conversation text. The task-preparation UI separately retains user-entered task text in the browser session; only its explicit Save action persists a browser draft. Do not copy that draft into the usage database.
- Treat an invocation workspace path as transient local input. Derive its salted fingerprint and friendly local alias, then discard the path; never return it from usage or detail APIs.
- Keep `usage_event_id` nullable so older Skill-level feedback remains readable. New feedback should bind to one invocation, and updating that invocation's feedback should not create duplicate entries.
- Treat recent project and last-used fields as the latest locally recorded invocation only. They do not prove all historical projects or all usage before logging was enabled.
- Do not turn task categories into free-form task descriptions. Use short generic labels such as `research`, `writing`, `coding`, `deployment`, or `other`.
- Treat `run_id` as an opaque identifier, not a task title. Allow only letters, numbers, `.`, `_`, `:`, and `-`; never encode prompts, filenames, user names, or task content in it.
- Infer Skill co-use only from a shared non-empty `run_id`. Never infer a workflow from timestamps, workspace proximity, matching categories, or model guesses.
- Treat `system`, `plugin`, and `public-installed` skills as read-only.
- To customize a public skill, copy it into the personal skill root and classify the copy as `adapted`; preserve its upstream source and authorship.
- A plugin manifest URL is only a source candidate. Do not label it verified until the public page has been checked and added to `assets/catalog/public-sources.json`.
- Never overwrite a global Skill during project promotion. Identical copies may be grouped; same-name differences require a separate decision.
- Never apply an improvement proposal automatically.
- Before changing any personal skill, show the proposed patch or diff and wait for explicit user approval.
- After approval, back up the target, apply the patch, run `quick_validate.py`, run relevant script tests, and forward-test when the change is substantial.
- Record the new version only after validation succeeds.

## Commands

```powershell
python scripts/scan_skills.py
python scripts/skill_center.py start --open
python scripts/skill_center.py doctor
python scripts/skill_center.py status
python scripts/skill_center.py stop
python scripts/configure_project_roots.py --list
python scripts/configure_project_roots.py --add "D:\projects\skills" --mode skill-container
python scripts/configure_project_roots.py --add "D:\projects\one-skill" --mode single-skill
python scripts/plan_promotions.py
python scripts/log_usage.py --skill "skill-name" --invocation implicit --category "research"
python scripts/log_usage.py --skill "skill-name" --invocation explicit --project-label "Local project alias"
python scripts/log_usage.py --skill "first-skill" --invocation explicit --run-id "run-20260729-001" --workflow "workflow-id" --step 1
python scripts/log_usage.py --skill "second-skill" --invocation explicit --run-id "run-20260729-001" --workflow "workflow-id" --step 2 --step-outcome solved
python scripts/log_usage.py --skill "skill-name" --invocation explicit --no-workspace
python scripts/propose_improvement.py --skill "skill-name"
python scripts/self_test.py
python scripts/http_e2e.py
python scripts/lifecycle_test.py
```

The dashboard files are installed from `assets/dashboard/` into `%USERPROFILE%\Documents\Codex Skill Center`. Set `SKILL_CENTER_HOME` to override that location. The dashboard server must remain loopback-only.

Read [references/data-policy.md](references/data-policy.md) when explaining privacy, classification, or the approval boundary.

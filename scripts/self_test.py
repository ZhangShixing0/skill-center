from __future__ import annotations

import json
import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import skill_store as store


def write_skill(folder: Path, name: str, description: str = "Test skill") -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n\n## Workflow\n\n1. Inspect input.\n2. Produce output.\n",
        encoding="utf-8",
    )


class SkillStoreV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="skill-center-v2-")
        self.root = Path(self.temp.name)
        self.codex_home = self.root / ".codex"
        self.center_home = self.root / "center"
        self.project_root = self.root / "project-skills"
        self.originals = {
            "CODEX_HOME": store.CODEX_HOME,
            "CENTER_HOME": store.CENTER_HOME,
            "DB_PATH": store.DB_PATH,
            "LEGACY_DB_PATH": store.LEGACY_DB_PATH,
            "PROJECT_ROOTS_PATH": store.PROJECT_ROOTS_PATH,
            "SCAN_SOURCES_PATH": store.SCAN_SOURCES_PATH,
            "LOCAL_CATALOG_PATH": store.LOCAL_CATALOG_PATH,
            "CLASSIFICATION_HINTS_PATH": store.CLASSIFICATION_HINTS_PATH,
            "PUBLIC_SOURCES_PATH": store.PUBLIC_SOURCES_PATH,
            "PUBLIC_LOCALIZATIONS_PATH": store.PUBLIC_LOCALIZATIONS_PATH,
            "READ_ONLY_MODE": store.READ_ONLY_MODE,
            "MAX_CONTENT_FILE_BYTES": store.MAX_CONTENT_FILE_BYTES,
            "MAX_CONTENT_TOTAL_BYTES": store.MAX_CONTENT_TOTAL_BYTES,
        }
        self.original_project_env = os.environ.pop("SKILL_PROJECT_ROOTS", None)
        store.CODEX_HOME = self.codex_home
        store.CENTER_HOME = self.center_home
        store.LEGACY_DB_PATH = self.center_home / "data" / "skill-center.sqlite3"
        store.DB_PATH = self.center_home / "data" / "skill-center-v2.sqlite3"
        store.PROJECT_ROOTS_PATH = self.center_home / "data" / "project-roots.json"
        store.SCAN_SOURCES_PATH = self.center_home / "data" / "scan-sources.local.json"
        store.LOCAL_CATALOG_PATH = self.center_home / "data" / "personal-catalog.local.json"
        store.CLASSIFICATION_HINTS_PATH = (
            self.center_home / "data" / "classification-suggestions.local.json"
        )
        store.PUBLIC_SOURCES_PATH = self.root / "public-sources.json"
        store.PUBLIC_SOURCES_PATH.write_text('{"__verified_urls__": {}}\n', encoding="utf-8")
        store.PUBLIC_LOCALIZATIONS_PATH = self.root / "public-skills.zh-CN.json"
        store.PUBLIC_LOCALIZATIONS_PATH.write_text(
            '{"__meta__":{"default_review_status":"assistant-draft"},"skills":{}}\n',
            encoding="utf-8",
        )
        store.READ_ONLY_MODE = False

        write_skill(self.codex_home / "skills" / "alpha", "alpha", "Global alpha")
        shutil.copytree(self.codex_home / "skills" / "alpha", self.project_root / "alpha")
        write_skill(self.project_root / "beta", "beta", "Portable project beta")
        plugin = self.codex_home / "plugins" / "cache" / "vendor" / "sample" / "1.0"
        write_skill(plugin / "skills" / "public-one", "public-one", "Public plugin skill")
        (plugin / ".codex-plugin").mkdir(parents=True)
        (plugin / ".codex-plugin" / "plugin.json").write_text(
            json.dumps({"name": "sample", "repository": "https://github.com/example/sample"}),
            encoding="utf-8",
        )
        store.save_project_roots([{"path": str(self.project_root), "label": "Test project", "enabled": True}])

    def tearDown(self) -> None:
        for key, value in self.originals.items():
            setattr(store, key, value)
        if self.original_project_env is None:
            os.environ.pop("SKILL_PROJECT_ROOTS", None)
        else:
            os.environ["SKILL_PROJECT_ROOTS"] = self.original_project_env
        self.temp.cleanup()

    def test_source_graph_grouping_and_public_boundary(self) -> None:
        result = store.scan_skills()
        self.assertEqual(result["counts"]["project"], 2)
        self.assertGreaterEqual(result["duplicates_grouped"], 1)
        self.assertEqual(result["added_count"], 4)
        self.assertEqual(result["updated_count"], 0)
        self.assertEqual(result["removed_count"], 0)

        mine = store.list_skills(scope="my", sort="name")
        self.assertEqual([item["name"] for item in mine], ["alpha", "beta"])
        alpha = next(item for item in mine if item["name"] == "alpha")
        self.assertEqual(alpha["duplicate_count"], 1)
        self.assertEqual({location["source_kind"] for location in alpha["locations"]}, {"personal", "project"})

        public = store.list_skills(scope="public")
        public_one = next(item for item in public if item["name"] == "public-one")
        self.assertEqual(public_one["upstream_source"], "https://github.com/example/sample")
        self.assertEqual(public_one["upstream_verified"], 0)
        self.assertEqual(public_one["source_confidence"], "plugin-manifest-unverified")
        with self.assertRaises(ValueError):
            store.get_skill_detail(skill_id=public_one["id"])

        store.PUBLIC_SOURCES_PATH.write_text(
            json.dumps({"__verified_urls__": {"https://github.com/example/sample": {"verified": True}}}),
            encoding="utf-8",
        )
        store.scan_skills()
        verified = next(item for item in store.list_skills(scope="public") if item["name"] == "public-one")
        self.assertEqual(verified["upstream_verified"], 1)
        self.assertEqual(verified["source_confidence"], "catalog-verified")

        write_skill(self.codex_home / "skills" / "collision", "collision", "Global collision")
        write_skill(self.project_root / "collision", "collision", "Different project collision")
        store.scan_skills()
        project_collision = next(
            item for item in store.list_skills(scope="my", include_duplicates=True)
            if item["name"] == "collision" and item["source_kind"] == "project"
        )
        collision_plan = store.promotion_preview(project_collision["id"])
        self.assertEqual(collision_plan["verdict"], "name-collision")
        self.assertFalse(collision_plan["diff"]["identical"])

        database_mtime = store.DB_PATH.stat().st_mtime_ns
        store.READ_ONLY_MODE = True
        try:
            read_only_public = store.list_skills(scope="public")
            self.assertGreaterEqual(len(read_only_public), 1)
            read_only_plan = store.promotion_preview(project_collision["id"])
            self.assertEqual(read_only_plan["verdict"], "name-collision")
        finally:
            store.READ_ONLY_MODE = False
        self.assertEqual(store.DB_PATH.stat().st_mtime_ns, database_mtime)

    def test_public_localization_and_source_status_overlay(self) -> None:
        store.scan_skills()
        public_one = next(
            item for item in store.list_skills(scope="public")
            if item["name"] == "public-one"
        )
        store.PUBLIC_LOCALIZATIONS_PATH.write_text(
            json.dumps(
                {
                    "__meta__": {
                        "default_review_status": "assistant-draft",
                    },
                    "skills": {
                        "public-one": {
                            "display_name": "公开插件示例",
                            "description": "用于验证公开 Skill 的中文展示叠加。",
                            "use_when": "需要测试中文搜索与来源状态时。",
                            "source_hash": public_one["content_hash"],
                        }
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        localized = next(
            item for item in store.list_skills(scope="public", query="中文展示")
            if item["name"] == "public-one"
        )
        self.assertEqual(localized["display_name_zh"], "公开插件示例")
        self.assertEqual(localized["display_name_original"], "Public One")
        self.assertEqual(localized["description_original"], "Public plugin skill")
        self.assertEqual(localized["use_when_zh"], "需要测试中文搜索与来源状态时。")
        self.assertEqual(localized["localization_status"], "assistant-draft")
        self.assertFalse(localized["localization_stale"])
        self.assertEqual(localized["source_status"], "candidate")
        self.assertEqual(localized["source_status_label"], "来源待验证")

        catalog = json.loads(store.PUBLIC_LOCALIZATIONS_PATH.read_text(encoding="utf-8"))
        catalog["skills"]["public-one"]["source_hash"] = "stale"
        store.PUBLIC_LOCALIZATIONS_PATH.write_text(
            json.dumps(catalog, ensure_ascii=False),
            encoding="utf-8",
        )
        stale = next(
            item for item in store.list_skills(scope="public")
            if item["name"] == "public-one"
        )
        self.assertTrue(stale["localization_stale"])

        self.assertEqual(
            store._public_source_status(
                {
                    "source_kind": "system",
                    "upstream_source": "",
                    "upstream_verified": 0,
                }
            )["status"],
            "bundled",
        )
        self.assertEqual(
            store._public_source_status(
                {
                    "source_kind": "personal",
                    "upstream_source": "",
                    "upstream_verified": 0,
                }
            )["status"],
            "missing",
        )

    def test_scan_source_preview_modes_and_private_template(self) -> None:
        single_root = self.root / "single-project-skill"
        write_skill(single_root, "single-project-skill", "One folder is one Skill")
        config = {
            "schema_version": 1,
            "automatic": {
                "personal": False,
                "system": False,
                "plugins": False,
                "agents_global": False,
            },
            "project_sources": [
                {
                    "path": str(self.project_root),
                    "label": "Container",
                    "enabled": True,
                    "mode": "skill-container",
                },
                {
                    "path": str(single_root),
                    "label": "Single",
                    "enabled": True,
                    "mode": "single-skill",
                },
            ],
            "ignore_parts": ["node_modules", ".git"],
        }
        config_before = store.SCAN_SOURCES_PATH.read_bytes()
        self.assertFalse(store.DB_PATH.exists())
        preview = store.preview_scan_sources(config)
        self.assertTrue(preview["valid"])
        self.assertFalse(preview["writes_performed"])
        self.assertEqual(preview["total_candidates"], 3)
        listed = [
            item
            for source in preview["sources"]
            for item in source["candidate_files"]
        ]
        self.assertEqual(len(listed), 3)
        self.assertTrue(all(item["skill_file"].endswith("SKILL.md") for item in listed))
        self.assertFalse(store.DB_PATH.exists())
        self.assertEqual(store.SCAN_SOURCES_PATH.read_bytes(), config_before)

        with self.assertRaisesRegex(ValueError, "重新预览"):
            store.save_scan_sources(
                config,
                preview_token="example_stale_token",
                require_preview=True,
            )
        saved = store.save_scan_sources(
            config,
            preview_token=preview["preview_token"],
            require_preview=True,
        )
        self.assertTrue(saved["writes_performed"])
        discovered = store.discover_skills()
        self.assertEqual({item["name"] for item in discovered}, {"alpha", "beta", "single-project-skill"})

        bad_mode = {
            **config,
            "project_sources": [
                {
                    "path": str(single_root),
                    "label": "Wrong mode",
                    "enabled": True,
                    "mode": "skill-container",
                }
            ],
        }
        invalid = store.preview_scan_sources(bad_mode)
        self.assertFalse(invalid["valid"])
        self.assertTrue(any("单个 Skill" in message for message in invalid["errors"]))

        broad = {
            **config,
            "project_sources": [
                {
                    "path": str(self.codex_home.parent),
                    "label": "Too broad",
                    "enabled": True,
                    "mode": "skill-container",
                }
            ],
        }
        rejected = store.preview_scan_sources(broad)
        self.assertFalse(rejected["valid"])
        self.assertTrue(any("用户主目录" in message for message in rejected["errors"]))

        template = store.shareable_scan_sources_template()
        serialized = json.dumps(template, ensure_ascii=False)
        self.assertFalse(template["contains_local_paths"])
        self.assertEqual(template["config"]["project_sources"], [])
        self.assertNotIn(str(self.root), serialized)

    def test_scan_delta_history_and_usage_coverage(self) -> None:
        first = store.scan_skills()
        self.assertEqual(first["added_count"], 4)
        unchanged = store.scan_skills()
        self.assertEqual(unchanged["added_count"], 0)
        self.assertEqual(unchanged["updated_count"], 0)
        self.assertEqual(unchanged["removed_count"], 0)

        write_skill(self.codex_home / "skills" / "gamma", "gamma", "New global gamma")
        beta_path = self.project_root / "beta" / "SKILL.md"
        beta_path.write_text(
            beta_path.read_text(encoding="utf-8") + "\nUpdated project guidance.\n",
            encoding="utf-8",
        )
        shutil.rmtree(
            self.codex_home
            / "plugins"
            / "cache"
            / "vendor"
            / "sample"
            / "1.0"
            / "skills"
            / "public-one"
        )
        changed = store.scan_skills()
        self.assertEqual({item["name"] for item in changed["delta"]["added"]}, {"gamma"})
        self.assertEqual({item["name"] for item in changed["delta"]["updated"]}, {"beta"})
        self.assertEqual({item["name"] for item in changed["delta"]["removed"]}, {"public-one"})
        self.assertEqual(changed["unchanged_count"], 2)

        latest = store.latest_scan()
        self.assertIsNotNone(latest)
        self.assertEqual(latest["id"], changed["run_id"])
        self.assertEqual(latest["added_count"], 1)
        self.assertEqual(latest["updated_count"], 1)
        self.assertEqual(latest["removed_count"], 1)

        overview = store.summary(scope="my")
        self.assertEqual(overview["usage_tracking"]["coverage"], "partial")
        self.assertEqual(overview["usage_tracking"]["tracked_skills"], 0)
        self.assertGreaterEqual(overview["usage_tracking"]["eligible_skills"], 3)

    def test_detail_feedback_usage_and_snapshot_update(self) -> None:
        store.scan_skills()
        beta_project = next(
            item for item in store.list_skills(scope="my", include_duplicates=True)
            if item["name"] == "beta" and item["source_kind"] == "project"
        )
        plan = store.promotion_preview(beta_project["id"])
        self.assertEqual(plan["verdict"], "review-required")
        self.assertFalse(plan["writes_performed"])

        detail = store.get_skill_detail(name="alpha")
        self.assertEqual(detail["skill"]["name"], "alpha")
        self.assertIn("scripts", detail["resources"])
        self.assertGreaterEqual(len(detail["guide"]["workflow"]), 1)

        alpha = detail["skill"]
        store.set_classification(alpha["id"], "self-authored")
        workspace = self.root / "workspace-alpha"
        (workspace / ".git").mkdir(parents=True)
        usage = store.record_usage(
            "alpha",
            "explicit",
            workspace_path=str(workspace),
            workspace_label="Alpha project",
            run_id="run-alpha-beta-001",
            workflow_id="test-alpha-beta",
            step_position=1,
        )
        store.record_usage(
            "beta",
            "implicit",
            workspace_path=str(workspace),
            workspace_label="Alpha project",
            run_id="run-alpha-beta-001",
            workflow_id="test-alpha-beta",
            step_position=2,
            step_outcome="solved",
        )
        self.assertEqual(usage["workspace"]["label"], "Alpha project")
        self.assertEqual(usage["workspace"]["context_kind"], "project")
        self.assertEqual(usage["run_id"], "run-alpha-beta-001")
        feedback = store.add_feedback(
            alpha["id"],
            "partial",
            3,
            ["missing-context"],
            "Needs a clearer example",
            usage_event_id=usage["event_id"],
        )
        self.assertEqual(feedback["usage_event_id"], usage["event_id"])
        refreshed = next(item for item in store.list_skills(scope="my") if item["name"] == "alpha")
        self.assertEqual(refreshed["uses_all"], 1)
        self.assertEqual(refreshed["feedback_count"], 1)
        refreshed_detail = store.get_skill_detail(name="alpha")
        self.assertEqual(refreshed_detail["usage_events"][0]["workspace_label"], "Alpha project")
        self.assertEqual(refreshed_detail["usage_events"][0]["outcome"], "partial")
        insight = store.insights(scope="my")
        self.assertEqual(insight["run_tracking"]["multi_skill_runs"], 1)
        self.assertEqual(insight["run_tracking"]["co_use"][0]["from_skill"], "alpha")
        self.assertEqual(insight["run_tracking"]["co_use"][0]["to_skill"], "beta")
        with store.connect() as connection:
            workspace_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(workspaces)")
            }
            stored_workspace = dict(
                connection.execute("SELECT * FROM workspaces LIMIT 1").fetchone()
            )
        self.assertNotIn("path", workspace_columns)
        self.assertNotIn(str(workspace), stored_workspace.values())

        snapshot = self.codex_home / "skills" / "beta"
        shutil.copytree(self.project_root / "beta", snapshot)
        origin_hash = store._content_hash(self.project_root / "beta")
        registered = store.register_snapshot(snapshot, self.project_root / "beta", origin_hash)
        self.assertEqual(registered["origin_hash"], origin_hash)
        (self.project_root / "beta" / "references").mkdir()
        (self.project_root / "beta" / "references" / "new.md").write_text("new source content", encoding="utf-8")
        store.scan_skills()
        snapshot_item = next(
            item for item in store.list_skills(scope="my", include_duplicates=True)
            if item["name"] == "beta" and item["source_kind"] == "personal"
        )
        self.assertEqual(snapshot_item["sync_status"], "update-available")
        diff = store.snapshot_diff(snapshot_item["id"])
        self.assertIn("references/new.md", diff["added"])

        (snapshot / "SKILL.md").write_text(
            (snapshot / "SKILL.md").read_text(encoding="utf-8") + "\nGlobal snapshot edit.\n",
            encoding="utf-8",
        )
        store.scan_skills()
        diverged = next(
            item for item in store.list_skills(scope="my", include_duplicates=True)
            if item["name"] == "beta" and item["source_kind"] == "personal"
        )
        self.assertEqual(diverged["sync_status"], "diverged")

    def test_classification_review_preview_and_explicit_batch_apply(self) -> None:
        write_skill(self.codex_home / "skills" / "gamma", "gamma", "Personal gamma")
        store.scan_skills()
        store.CLASSIFICATION_HINTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        store.CLASSIFICATION_HINTS_PATH.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "suggestions": {
                        "alpha": {
                            "classification": "self-authored",
                            "confidence": "high",
                            "evidence": ["Local creation record"],
                        },
                        "gamma": {
                            "classification": "public-installed",
                            "confidence": "medium",
                            "evidence": ["Public package structure"],
                        },
                    },
                }
            ),
            encoding="utf-8",
        )
        alpha_folder = self.codex_home / "skills" / "alpha"
        gamma_folder = self.codex_home / "skills" / "gamma"
        source_hashes = {
            "alpha": store._content_hash(alpha_folder),
            "gamma": store._content_hash(gamma_folder),
        }
        database_mtime = store.DB_PATH.stat().st_mtime_ns
        catalog_before = (
            store.LOCAL_CATALOG_PATH.read_bytes()
            if store.LOCAL_CATALOG_PATH.is_file()
            else None
        )

        review = store.classification_review()
        self.assertFalse(review["writes_performed"])
        self.assertEqual(review["summary"]["total"], 2)
        self.assertEqual(review["summary"]["high_confidence"], 1)
        self.assertEqual(store.DB_PATH.stat().st_mtime_ns, database_mtime)
        self.assertEqual(
            store.LOCAL_CATALOG_PATH.read_bytes()
            if store.LOCAL_CATALOG_PATH.is_file()
            else None,
            catalog_before,
        )
        by_name = {item["name"]: item for item in review["candidates"]}
        decisions = [
            {
                "skill_id": by_name["alpha"]["skill_id"],
                "classification": "self-authored",
            },
            {
                "skill_id": by_name["gamma"]["skill_id"],
                "classification": "public-installed",
            },
        ]
        preview = store.preview_classifications(decisions)
        self.assertFalse(preview["writes_performed"])
        self.assertEqual(preview["change_count"], 2)
        self.assertEqual(store.DB_PATH.stat().st_mtime_ns, database_mtime)
        self.assertEqual(
            next(item for item in store.list_skills(scope="my") if item["name"] == "alpha")[
                "classification"
            ],
            "unknown",
        )

        applied = store.apply_classifications(decisions, preview["preview_token"])
        self.assertTrue(applied["writes_performed"])
        self.assertEqual(applied["applied_count"], 2)
        mine = {item["name"]: item for item in store.list_skills(scope="my")}
        public = {item["name"]: item for item in store.list_skills(scope="public")}
        self.assertEqual(mine["alpha"]["classification"], "self-authored")
        self.assertNotIn("gamma", mine)
        self.assertEqual(public["gamma"]["classification"], "public-installed")
        with self.assertRaisesRegex(ValueError, "公开 Skill"):
            store.get_skill_detail(name="gamma")
        local_catalog = json.loads(store.LOCAL_CATALOG_PATH.read_text(encoding="utf-8"))
        self.assertEqual(local_catalog["alpha"]["classification"], "self-authored")
        self.assertEqual(local_catalog["gamma"]["classification"], "public-installed")
        self.assertEqual(store._content_hash(alpha_folder), source_hashes["alpha"])
        self.assertEqual(store._content_hash(gamma_folder), source_hashes["gamma"])
        with self.assertRaisesRegex(ValueError, "已被归类"):
            store.apply_classifications(decisions, preview["preview_token"])

        beta_project = next(
            item
            for item in store.list_skills(scope="my", include_duplicates=True)
            if item["name"] == "beta" and item["source_kind"] == "project"
        )
        with self.assertRaisesRegex(ValueError, "全局个人"):
            store.preview_classifications(
                [
                    {
                        "skill_id": beta_project["id"],
                        "classification": "self-authored",
                    }
                ]
            )

    def test_database_v2_isolated_from_legacy_filename(self) -> None:
        store.DB_PATH = store.LEGACY_DB_PATH
        legacy_scan = store.scan_skills()
        self.assertTrue(store.LEGACY_DB_PATH.is_file())
        self.assertGreater(legacy_scan["scanned"], 0)

        store.DB_PATH = self.center_home / "data" / "skill-center-v2.sqlite3"
        migrated = store.scan_skills()
        self.assertTrue(store.DB_PATH.is_file())
        connection = sqlite3.connect(store.DB_PATH)
        try:
            version = connection.execute(
                "SELECT value FROM app_meta WHERE key='schema_version'"
            ).fetchone()[0]
            family = connection.execute(
                "SELECT value FROM app_meta WHERE key='database_family'"
            ).fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(int(version), store.DATABASE_SCHEMA_VERSION)
        self.assertEqual(family, store.DATABASE_FAMILY)

        v2_mtime = store.DB_PATH.stat().st_mtime_ns
        connection = sqlite3.connect(store.LEGACY_DB_PATH)
        try:
            connection.execute("UPDATE skills SET is_present=0")
            connection.commit()
        finally:
            connection.close()
        self.assertEqual(store.DB_PATH.stat().st_mtime_ns, v2_mtime)
        self.assertEqual(migrated["scanned"], store.latest_scan()["total_locations"])

        connection = sqlite3.connect(store.DB_PATH)
        try:
            connection.execute(
                "UPDATE app_meta SET value='999' WHERE key='schema_version'"
            )
            connection.commit()
        finally:
            connection.close()
        with self.assertRaisesRegex(RuntimeError, "newer than this package supports"):
            store.connect()

    def test_schema_v5_migration_preserves_existing_usage(self) -> None:
        store.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(store.DB_PATH)
        try:
            connection.executescript(
                """
                CREATE TABLE app_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                INSERT INTO app_meta(key, value) VALUES('schema_version', '2');
                INSERT INTO app_meta(key, value) VALUES('database_family', 'skill-center-v2');
                CREATE TABLE skills (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    path TEXT NOT NULL UNIQUE,
                    source_kind TEXT NOT NULL,
                    source_label TEXT NOT NULL DEFAULT '',
                    classification TEXT NOT NULL DEFAULT 'unknown',
                    upstream_source TEXT NOT NULL DEFAULT '',
                    upstream_author TEXT NOT NULL DEFAULT '',
                    version_hash TEXT NOT NULL DEFAULT '',
                    modified_at TEXT,
                    discovered_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    is_present INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE usage_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    skill_id TEXT NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
                    used_at TEXT NOT NULL,
                    invocation_type TEXT NOT NULL,
                    version_hash TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    skill_id TEXT NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
                    outcome TEXT NOT NULL,
                    rating INTEGER NOT NULL,
                    issue_tags TEXT NOT NULL DEFAULT '[]',
                    note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );
                """
            )
            connection.execute(
                """
                INSERT INTO skills(
                    id, name, path, source_kind, source_label, version_hash,
                    discovered_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "legacy-alpha",
                    "alpha",
                    str(self.codex_home / "skills" / "alpha"),
                    "personal",
                    "Personal",
                    "v2hash",
                    "2026-07-23T00:00:00+00:00",
                    "2026-07-23T00:00:00+00:00",
                ),
            )
            connection.executemany(
                """
                INSERT INTO usage_events(skill_id, used_at, invocation_type, version_hash)
                VALUES('legacy-alpha', ?, 'explicit', 'v2hash')
                """,
                [(f"2026-07-{day:02d}T00:00:00+00:00",) for day in range(1, 21)],
            )
            connection.commit()
        finally:
            connection.close()

        with store.connect() as migrated:
            version = int(
                migrated.execute(
                    "SELECT value FROM app_meta WHERE key='schema_version'"
                ).fetchone()[0]
            )
            usage_count = migrated.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0]
            usage_columns = {
                row[1] for row in migrated.execute("PRAGMA table_info(usage_events)")
            }
            feedback_columns = {
                row[1] for row in migrated.execute("PRAGMA table_info(feedback)")
            }
            workspace_columns = {
                row[1] for row in migrated.execute("PRAGMA table_info(workspaces)")
            }
            task_run_columns = {
                row[1] for row in migrated.execute("PRAGMA table_info(task_runs)")
            }
            skill_columns = {
                row[1] for row in migrated.execute("PRAGMA table_info(skills)")
            }
            version_count = migrated.execute(
                "SELECT COUNT(*) FROM skill_versions WHERE skill_id='legacy-alpha'"
            ).fetchone()[0]

        self.assertEqual(version, 5)
        self.assertEqual(usage_count, 20)
        self.assertTrue(
            {
                "workspace_id",
                "task_category",
                "run_id",
                "workflow_id",
                "step_position",
                "step_outcome",
            }.issubset(usage_columns)
        )
        self.assertIn("usage_event_id", feedback_columns)
        self.assertNotIn("path", workspace_columns)
        self.assertTrue(
            {"workflow_id", "started_at", "last_activity_at", "outcome"}.issubset(
                task_run_columns
            )
        )
        self.assertTrue({"last_seen_at", "removed_at"}.issubset(skill_columns))
        self.assertEqual(version_count, 0)

    def test_uninstalled_skill_is_reconciled_and_history_remains_readable(self) -> None:
        transient = self.codex_home / "skills" / "transient"
        write_skill(transient, "transient", "Temporary installed skill")
        store.scan_skills()
        transient_item = next(
            item for item in store.list_skills(scope="my")
            if item["name"] == "transient"
        )
        usage = store.record_usage(
            "transient",
            "implicit",
            workspace_path=str(self.root / "workspace-transient"),
            workspace_label="Transient project",
        )
        self.assertGreater(usage["event_id"], 0)
        shutil.rmtree(transient)

        reconciled = store.reconcile_missing_skills()
        self.assertTrue(reconciled["writes_performed"])
        self.assertEqual(
            {item["name"] for item in reconciled["removed"]},
            {"transient"},
        )
        self.assertNotIn(
            "transient",
            {item["name"] for item in store.list_skills(scope="my")},
        )
        removed = next(
            item for item in store.list_skills(presence="removed")
            if item["name"] == "transient"
        )
        self.assertEqual(removed["presence_status"], "removed")
        self.assertIsNotNone(removed["removed_at"])
        self.assertEqual(removed["last_workspace_label"], "Transient project")
        detail = store.get_skill_detail(name="transient")
        self.assertFalse(detail["availability"]["file_available"])
        self.assertFalse(detail["availability"]["can_execute"])
        self.assertEqual(detail["usage_events"][0]["workspace_label"], "Transient project")
        self.assertEqual(len(detail["versions"]), 1)

        inbox = {item["name"] for item in store.list_skills(scope="my", ownership="inbox")}
        owned = {item["name"] for item in store.list_skills(scope="my", ownership="owned")}
        self.assertIn("alpha", inbox)
        self.assertIn("beta", owned)
        self.assertNotIn("alpha", owned)

    def test_environment_sources_are_read_only_and_overlap_is_rejected(self) -> None:
        env_root = self.root / "environment-skills"
        write_skill(env_root / "env-only", "env-only", "Managed by environment")
        os.environ["SKILL_PROJECT_ROOTS"] = str(env_root)

        loaded = store.load_scan_sources()
        self.assertNotIn(str(env_root), {item["path"] for item in loaded["project_sources"]})
        preview = store.preview_scan_sources(loaded)
        env_source = next(
            item for item in preview["sources"] if item.get("managed_by") == "environment"
        )
        self.assertFalse(env_source["configurable"])
        self.assertEqual(env_source["found_count"], 1)

        saved = store.save_scan_sources(loaded)
        serialized = store.SCAN_SOURCES_PATH.read_text(encoding="utf-8")
        self.assertNotIn(str(env_root), serialized)
        self.assertEqual(saved["config"]["custom_ignore_parts"], [])

        overlap = {
            **loaded,
            "project_sources": [
                {
                    "path": str(self.codex_home / "skills" / "alpha"),
                    "label": "Overlapping alpha",
                    "enabled": True,
                    "mode": "single-skill",
                }
            ],
        }
        overlap_preview = store.preview_scan_sources(overlap)
        self.assertFalse(overlap_preview["valid"])
        self.assertTrue(
            any("automatic Skill locations" in error for error in overlap_preview["errors"])
        )

    def test_failed_scan_restores_previous_source_configuration(self) -> None:
        current = store.load_scan_sources()
        current_preview = store.preview_scan_sources(current)
        store.save_scan_sources(
            current,
            preview_token=current_preview["preview_token"],
            require_preview=True,
        )
        before = store.SCAN_SOURCES_PATH.read_bytes()
        changed = {
            **current,
            "automatic": {**current["automatic"], "plugins": False},
        }
        changed_preview = store.preview_scan_sources(changed)
        with patch.object(store, "scan_skills", side_effect=RuntimeError("synthetic failure")):
            with self.assertRaisesRegex(ValueError, "previous source configuration was restored"):
                store.save_scan_sources_and_scan(
                    changed,
                    preview_token=changed_preview["preview_token"],
                    require_preview=True,
                )
        self.assertEqual(store.SCAN_SOURCES_PATH.read_bytes(), before)

    def test_content_hash_respects_byte_budget(self) -> None:
        folder = self.root / "large-skill"
        write_skill(folder, "large-skill")
        payload = folder / "payload.bin"
        payload.write_bytes(b"A" * 128)
        store.MAX_CONTENT_FILE_BYTES = 16
        store.MAX_CONTENT_TOTAL_BYTES = 32
        first = store._content_hash(folder)
        payload.write_bytes(b"B" * 128)
        second = store._content_hash(folder)
        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main(verbosity=2)

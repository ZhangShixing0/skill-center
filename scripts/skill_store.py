from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import secrets
import shutil
import sqlite3
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse


SKILL_ROOT = Path(__file__).resolve().parent.parent
CODEX_HOME = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
CENTER_HOME = Path(
    os.environ.get("SKILL_CENTER_HOME", Path.home() / "Documents" / "Codex Skill Center")
)
LEGACY_DB_PATH = CENTER_HOME / "data" / "skill-center.sqlite3"
DB_PATH = CENTER_HOME / "data" / "skill-center-v2.sqlite3"
PROJECT_ROOTS_PATH = CENTER_HOME / "data" / "project-roots.json"
SCAN_SOURCES_PATH = CENTER_HOME / "data" / "scan-sources.local.json"
CATALOG_PATH = SKILL_ROOT / "assets" / "catalog" / "personal-skills.json"
LOCAL_CATALOG_PATH = CENTER_HOME / "data" / "personal-catalog.local.json"
CLASSIFICATION_HINTS_PATH = CENTER_HOME / "data" / "classification-suggestions.local.json"
PUBLIC_SOURCES_PATH = SKILL_ROOT / "assets" / "catalog" / "public-sources.json"
PUBLIC_LOCALIZATIONS_PATH = (
    SKILL_ROOT / "assets" / "catalog" / "public-skills.zh-CN.json"
)
WORKFLOWS_PATH = SKILL_ROOT / "assets" / "catalog" / "workflows.json"
LOCAL_WORKFLOWS_PATH = CENTER_HOME / "data" / "workflows.local.json"
SCAN_SOURCES_TEMPLATE_PATH = SKILL_ROOT / "assets" / "config" / "scan-sources.example.json"
DATABASE_SCHEMA_VERSION = 5
DATABASE_FAMILY = "codex-skill-center-v2"

VALID_CLASSIFICATIONS = {
    "self-authored",
    "adapted",
    "public-installed",
    "system",
    "plugin",
    "unknown",
}
VALID_REVIEW_CLASSIFICATIONS = {"self-authored", "adapted", "public-installed"}
VALID_SUGGESTION_CONFIDENCE = {"high", "medium", "low"}
VALID_OUTCOMES = {"solved", "partial", "failed"}
VALID_STEP_OUTCOMES = {"", "solved", "partial", "failed", "skipped"}
VALID_WORKSPACE_KINDS = {"project", "global", "temporary", "unknown"}
VALID_PORTABILITY = {"portable", "adaptable", "project-bound", "unknown", "not-applicable"}
READ_ONLY_MODE = False
IGNORED_PARTS = {
    ".git",
    ".svn",
    ".hg",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    ".mypy_cache",
    ".pytest_cache",
}
VALID_SOURCE_MODES = {"skill-container", "single-skill"}
AUTOMATIC_SOURCE_KEYS = ("personal", "system", "plugins", "agents_global")
MAX_PROJECT_SOURCES = 100
MAX_PROJECT_SKILLS_PER_SOURCE = 250
MAX_AUTOMATIC_SKILLS_PER_SOURCE = 2000
MAX_CONTENT_FILES_PER_SKILL = 1000
MAX_CONTENT_FILE_BYTES = 5 * 1024 * 1024
MAX_CONTENT_TOTAL_BYTES = 25 * 1024 * 1024

SKILL_COLUMNS: dict[str, str] = {
    "display_name": "TEXT NOT NULL DEFAULT ''",
    "category": "TEXT NOT NULL DEFAULT '其他'",
    "origin_scope": "TEXT NOT NULL DEFAULT ''",
    "origin_path": "TEXT NOT NULL DEFAULT ''",
    "origin_hash": "TEXT NOT NULL DEFAULT ''",
    "project_root": "TEXT NOT NULL DEFAULT ''",
    "content_hash": "TEXT NOT NULL DEFAULT ''",
    "duplicate_group": "TEXT NOT NULL DEFAULT ''",
    "duplicate_of": "TEXT NOT NULL DEFAULT ''",
    "is_primary": "INTEGER NOT NULL DEFAULT 1",
    "sync_status": "TEXT NOT NULL DEFAULT 'standalone'",
    "portability": "TEXT NOT NULL DEFAULT 'unknown'",
    "showcase_level": "TEXT NOT NULL DEFAULT 'standard'",
    "showcase_status": "TEXT NOT NULL DEFAULT 'generated'",
    "upstream_verified": "INTEGER NOT NULL DEFAULT 0",
    "source_confidence": "TEXT NOT NULL DEFAULT ''",
    "last_seen_at": "TEXT",
    "removed_at": "TEXT",
}


class ClosingConnection(sqlite3.Connection):
    """Commit or roll back like sqlite3's context manager, then always close the handle."""

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool | None:
        try:
            return super().__exit__(exc_type, exc, traceback)
        finally:
            self.close()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _json_file(path: Path, fallback: Any) -> Any:
    if not path.is_file():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return fallback


def _catalog() -> dict[str, dict[str, Any]]:
    packaged = _json_file(CATALOG_PATH, {})
    local = _json_file(LOCAL_CATALOG_PATH, {})
    packaged = packaged if isinstance(packaged, dict) else {}
    local = local if isinstance(local, dict) else {}
    return {**packaged, **local}


def _workflow_catalog() -> list[dict[str, Any]]:
    packaged = _json_file(WORKFLOWS_PATH, {})
    local = _json_file(LOCAL_WORKFLOWS_PATH, {})
    packaged_items = packaged.get("workflows", []) if isinstance(packaged, dict) else []
    local_items = local.get("workflows", []) if isinstance(local, dict) else []
    merged: dict[str, dict[str, Any]] = {}
    for raw in [*packaged_items, *local_items]:
        if not isinstance(raw, dict):
            continue
        workflow_id = str(raw.get("id") or "").strip()
        if not workflow_id:
            continue
        merged[workflow_id] = dict(raw)
    return list(merged.values())


def _public_sources() -> dict[str, dict[str, Any]]:
    data = _json_file(PUBLIC_SOURCES_PATH, {})
    return data if isinstance(data, dict) else {}


def _public_localizations() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    data = _json_file(PUBLIC_LOCALIZATIONS_PATH, {})
    if not isinstance(data, dict):
        return {}, {}
    metadata = data.get("__meta__", {})
    skills = data.get("skills", {})
    metadata = metadata if isinstance(metadata, dict) else {}
    skills = skills if isinstance(skills, dict) else {}
    return metadata, {
        str(name): entry
        for name, entry in skills.items()
        if isinstance(name, str) and isinstance(entry, dict)
    }


def _public_source_status(item: dict[str, Any]) -> dict[str, Any]:
    upstream_source = str(item.get("upstream_source") or "")
    verified = bool(item.get("upstream_verified") and _valid_web_url(upstream_source))
    if verified:
        status = "verified"
        label = "来源已验证"
        help_text = "链接已经过本地公开来源目录核验，可以打开上游介绍。"
    elif upstream_source:
        status = "candidate"
        label = "来源待验证"
        help_text = "已从插件清单或本地元数据找到候选地址，核验前不开放跳转。"
    elif item.get("source_kind") == "system":
        status = "bundled"
        label = "Codex 系统内置"
        help_text = "随 Codex 提供，当前安装元数据没有单独的公开上游地址。"
    else:
        status = "missing"
        label = "来源尚未找到"
        help_text = "当前元数据没有可用的上游地址，需要后续补充。"
    return {
        "status": status,
        "label": label,
        "help": help_text,
        "clickable": status == "verified",
    }


def _with_public_display(
    item: dict[str, Any],
    metadata: dict[str, Any],
    localizations: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    original_display_name = str(item.get("display_name") or item.get("name") or "")
    original_description = str(item.get("description") or "")
    entry = localizations.get(str(item.get("name") or ""), {})
    display_name_zh = str(entry.get("display_name") or "").strip()[:160]
    description_zh = str(entry.get("description") or "").strip()[:1200]
    use_when_zh = str(entry.get("use_when") or "").strip()[:600]
    source_hash = str(entry.get("source_hash") or "")
    available = bool(display_name_zh and description_zh)
    stale = bool(
        available
        and source_hash
        and source_hash != str(item.get("content_hash") or "")
    )
    review_status = str(
        entry.get("review_status")
        or metadata.get("default_review_status")
        or "unreviewed"
    )
    source_status = _public_source_status(item)
    item.update(
        display_name_original=original_display_name,
        description_original=original_description,
        display_name_zh=display_name_zh,
        description_zh=description_zh,
        use_when_zh=use_when_zh,
        localization_available=available,
        localization_status=review_status if available else "missing",
        localization_stale=stale,
        source_status=source_status["status"],
        source_status_label=source_status["label"],
        source_status_help=source_status["help"],
        source_clickable=source_status["clickable"],
    )
    return item


def _migrate_legacy_database() -> None:
    if DB_PATH == LEGACY_DB_PATH or DB_PATH.exists() or not LEGACY_DB_PATH.is_file():
        return
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = DB_PATH.with_suffix(DB_PATH.suffix + ".migrating")
    if temporary.exists():
        temporary.unlink()
    source = sqlite3.connect(LEGACY_DB_PATH.resolve().as_uri() + "?mode=ro", uri=True)
    target = sqlite3.connect(temporary)
    try:
        source.backup(target)
        target.commit()
    finally:
        target.close()
        source.close()
    temporary.replace(DB_PATH)


def _schema_version(connection: sqlite3.Connection) -> int:
    table = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='app_meta'"
    ).fetchone()
    if not table:
        return 0
    row = connection.execute(
        "SELECT value FROM app_meta WHERE key='schema_version'"
    ).fetchone()
    if not row:
        return 0
    try:
        return int(row[0])
    except (TypeError, ValueError) as exc:
        raise RuntimeError("Skill Center database has an invalid schema version.") from exc


def _assert_supported_schema(connection: sqlite3.Connection) -> None:
    version = _schema_version(connection)
    if version > DATABASE_SCHEMA_VERSION:
        raise RuntimeError(
            f"Skill Center database schema {version} is newer than this package supports "
            f"({DATABASE_SCHEMA_VERSION})."
        )


def connect() -> sqlite3.Connection:
    if READ_ONLY_MODE:
        if not DB_PATH.is_file():
            raise FileNotFoundError(f"Skill Center database not found: {DB_PATH}")
        connection = sqlite3.connect(
            DB_PATH.resolve().as_uri() + "?mode=ro",
            uri=True,
            factory=ClosingConnection,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        try:
            _assert_supported_schema(connection)
        except Exception:
            connection.close()
            raise
        return connection
    _migrate_legacy_database()
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, factory=ClosingConnection)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=5000")
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        init_db(connection)
    except Exception:
        connection.close()
        raise
    return connection


def connect_readonly() -> sqlite3.Connection:
    if not DB_PATH.is_file():
        raise FileNotFoundError(f"Skill Center database not found: {DB_PATH}")
    connection = sqlite3.connect(
        DB_PATH.resolve().as_uri() + "?mode=ro",
        uri=True,
        factory=ClosingConnection,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    try:
        _assert_supported_schema(connection)
    except Exception:
        connection.close()
        raise
    return connection


def init_db(connection: sqlite3.Connection) -> None:
    connection.execute(
        "CREATE TABLE IF NOT EXISTS app_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    _assert_supported_schema(connection)
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS skills (
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
        CREATE TABLE IF NOT EXISTS usage_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            skill_id TEXT NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
            used_at TEXT NOT NULL,
            invocation_type TEXT NOT NULL,
            version_hash TEXT NOT NULL DEFAULT '',
            workspace_id TEXT REFERENCES workspaces(id) ON DELETE SET NULL,
            task_category TEXT NOT NULL DEFAULT '',
            run_id TEXT NOT NULL DEFAULT '',
            workflow_id TEXT NOT NULL DEFAULT '',
            step_position INTEGER NOT NULL DEFAULT 0,
            step_outcome TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS workspaces (
            id TEXT PRIMARY KEY,
            label TEXT NOT NULL DEFAULT '',
            context_kind TEXT NOT NULL DEFAULT 'unknown',
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS task_runs (
            id TEXT PRIMARY KEY,
            workflow_id TEXT NOT NULL DEFAULT '',
            started_at TEXT NOT NULL,
            last_activity_at TEXT NOT NULL,
            completed_at TEXT,
            outcome TEXT NOT NULL DEFAULT '',
            rating INTEGER NOT NULL DEFAULT 0,
            workspace_id TEXT REFERENCES workspaces(id) ON DELETE SET NULL,
            task_category TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            skill_id TEXT NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
            usage_event_id INTEGER REFERENCES usage_events(id) ON DELETE SET NULL,
            outcome TEXT NOT NULL,
            rating INTEGER NOT NULL,
            issue_tags TEXT NOT NULL DEFAULT '[]',
            note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS proposals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            skill_id TEXT NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            rationale TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS scan_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scanned_at TEXT NOT NULL,
            total_locations INTEGER NOT NULL,
            added_count INTEGER NOT NULL,
            updated_count INTEGER NOT NULL,
            removed_count INTEGER NOT NULL,
            unchanged_count INTEGER NOT NULL,
            duplicate_locations INTEGER NOT NULL,
            delta_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS skill_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            skill_id TEXT NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
            content_hash TEXT NOT NULL,
            version_hash TEXT NOT NULL DEFAULT '',
            source_modified_at TEXT,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            UNIQUE(skill_id, content_hash)
        );
        CREATE INDEX IF NOT EXISTS idx_usage_skill_time ON usage_events(skill_id, used_at);
        CREATE INDEX IF NOT EXISTS idx_task_runs_time ON task_runs(last_activity_at);
        CREATE INDEX IF NOT EXISTS idx_feedback_skill_time ON feedback(skill_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_proposals_skill_status ON proposals(skill_id, status);
        CREATE INDEX IF NOT EXISTS idx_scan_runs_time ON scan_runs(scanned_at);
        CREATE INDEX IF NOT EXISTS idx_skill_versions_skill_time ON skill_versions(skill_id, first_seen_at);
        """
    )
    columns = {row[1] for row in connection.execute("PRAGMA table_info(skills)")}
    for name, declaration in {
        "upstream_source": "TEXT NOT NULL DEFAULT ''",
        "upstream_author": "TEXT NOT NULL DEFAULT ''",
        **SKILL_COLUMNS,
    }.items():
        if name not in columns:
            connection.execute(f"ALTER TABLE skills ADD COLUMN {name} {declaration}")
    usage_columns = {row[1] for row in connection.execute("PRAGMA table_info(usage_events)")}
    for name, declaration in {
        "workspace_id": "TEXT",
        "task_category": "TEXT NOT NULL DEFAULT ''",
        "run_id": "TEXT NOT NULL DEFAULT ''",
        "workflow_id": "TEXT NOT NULL DEFAULT ''",
        "step_position": "INTEGER NOT NULL DEFAULT 0",
        "step_outcome": "TEXT NOT NULL DEFAULT ''",
    }.items():
        if name not in usage_columns:
            connection.execute(f"ALTER TABLE usage_events ADD COLUMN {name} {declaration}")
    feedback_columns = {row[1] for row in connection.execute("PRAGMA table_info(feedback)")}
    if "usage_event_id" not in feedback_columns:
        connection.execute("ALTER TABLE feedback ADD COLUMN usage_event_id INTEGER")
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_usage_workspace_time ON usage_events(workspace_id, used_at)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_feedback_usage_event ON feedback(usage_event_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_usage_run_step "
        "ON usage_events(run_id, step_position, used_at)"
    )
    connection.execute(
        "UPDATE skills SET last_seen_at=updated_at "
        "WHERE is_present=1 AND (last_seen_at IS NULL OR last_seen_at='')"
    )
    connection.execute(
        "UPDATE skills SET removed_at=updated_at "
        "WHERE is_present=0 AND (removed_at IS NULL OR removed_at='')"
    )
    connection.execute(
        """
        INSERT OR IGNORE INTO skill_versions(
          skill_id, content_hash, version_hash, source_modified_at, first_seen_at, last_seen_at
        )
        SELECT id, content_hash, version_hash, modified_at, discovered_at,
               COALESCE(last_seen_at, updated_at)
        FROM skills WHERE content_hash!=''
        """
    )
    if not connection.execute(
        "SELECT 1 FROM app_meta WHERE key='workspace_hash_salt'"
    ).fetchone():
        connection.execute(
            "INSERT INTO app_meta(key, value) VALUES('workspace_hash_salt', ?)",
            (secrets.token_hex(32),),
        )
    connection.execute(
        "INSERT INTO app_meta(key, value) VALUES('database_family', ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (DATABASE_FAMILY,),
    )
    connection.execute(
        "INSERT INTO app_meta(key, value) VALUES('schema_version', ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (str(DATABASE_SCHEMA_VERSION),),
    )
    connection.commit()


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def _frontmatter(path: Path) -> tuple[str, str]:
    text = _read_text(path)
    header = text.split("---", 2)[1] if text.startswith("---") and text.count("---") >= 2 else ""

    def field(name: str) -> str:
        match = re.search(rf"(?m)^{re.escape(name)}:\s*(.+?)\s*$", header)
        if not match:
            return ""
        value = match.group(1).strip().strip("\"'")
        return re.sub(r"\s+", " ", value)

    return field("name") or path.parent.name, field("description")


def _interface_metadata(folder: Path) -> dict[str, str]:
    path = folder / "agents" / "openai.yaml"
    if not path.is_file():
        return {}
    text = _read_text(path)
    result: dict[str, str] = {}
    for key in ("display_name", "short_description", "default_prompt"):
        match = re.search(rf"(?m)^\s*{key}:\s*[\"']?(.*?)[\"']?\s*$", text)
        if match:
            result[key] = match.group(1).strip().strip("\"'")
    return result


def _version_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def _skill_id(path: Path) -> str:
    normalized = str(path.resolve()).replace("\\", "/").lower()
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]


def _active_ignored_parts() -> set[str]:
    data = _json_file(SCAN_SOURCES_PATH, {})
    values = data.get("ignore_parts", []) if isinstance(data, dict) else []
    custom = {
        str(value).strip()
        for value in values
        if isinstance(value, str)
        and value.strip()
        and "/" not in value
        and "\\" not in value
        and value.strip() not in {".", ".."}
    }
    return set(IGNORED_PARTS) | custom


def _iter_content_files(folder: Path) -> Iterable[Path]:
    ignored_parts = _active_ignored_parts()
    yielded = 0
    for current, directories, filenames in os.walk(folder, followlinks=False):
        current_path = Path(current)
        directories[:] = sorted(
            [
                name
                for name in directories
                if name not in ignored_parts and not (current_path / name).is_symlink()
            ],
            key=str.lower,
        )
        for name in sorted(filenames, key=str.lower):
            path = current_path / name
            if path.is_symlink() or not path.is_file():
                continue
            yield path
            yielded += 1
            if yielded >= MAX_CONTENT_FILES_PER_SKILL:
                return


def _content_hash(folder: Path) -> str:
    digest = hashlib.sha256()
    total_bytes = 0
    for path in _iter_content_files(folder):
        relative = path.relative_to(folder).as_posix().encode("utf-8")
        digest.update(relative)
        digest.update(b"\0")
        try:
            size = path.stat().st_size
            digest.update(str(size).encode("ascii"))
            digest.update(b"\0")
            remaining = min(
                size,
                MAX_CONTENT_FILE_BYTES,
                max(0, MAX_CONTENT_TOTAL_BYTES - total_bytes),
            )
            with path.open("rb") as handle:
                while remaining > 0:
                    chunk = handle.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    digest.update(chunk)
                    total_bytes += len(chunk)
                    remaining -= len(chunk)
            if size > MAX_CONTENT_FILE_BYTES:
                digest.update(b"<file-content-truncated>")
            if total_bytes >= MAX_CONTENT_TOTAL_BYTES:
                digest.update(b"<skill-content-budget-exhausted>")
                break
        except OSError:
            digest.update(b"<unreadable>")
            continue
        digest.update(b"\0")
    return digest.hexdigest()[:16]


def _valid_web_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _default_display_name(name: str) -> str:
    return " ".join(part.capitalize() for part in name.replace("_", "-").split("-") if part)


def _category_for(name: str, description: str) -> str:
    haystack = f"{name} {description}".lower()
    rules = [
        (("html", "web", "ui", "ux", "frontend", "design"), "网页与设计"),
        (("deploy", "server", "release", "github", "git"), "发布与部署"),
        (("research", "market", "investigation", "intelligence", "discovery"), "研究与洞察"),
        (("product", "position", "jobs-to-be-done", "workshop"), "产品与策略"),
        (("document", "pdf", "spreadsheet", "presentation", "excel"), "文档与办公"),
        (("agent", "architect", "contract", "app", "test"), "应用工程"),
    ]
    for words, category in rules:
        if any(word in haystack for word in words):
            return category
    return "其他"


def _default_scan_sources() -> dict[str, Any]:
    return {
        "schema_version": 2,
        "automatic": {key: True for key in AUTOMATIC_SOURCE_KEYS},
        "project_sources": [],
        "ignore_parts": sorted(IGNORED_PARTS),
        "custom_ignore_parts": [],
    }


def _expanded_path(value: object) -> Path:
    raw = os.path.expandvars(os.path.expanduser(str(value or "").strip()))
    if not raw:
        raise ValueError("扫描路径不能为空")
    return Path(raw).resolve()


def _source_id(path: Path, mode: str) -> str:
    normalized = f"{path.as_posix().lower()}|{mode}"
    return "project-" + hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:12]


def _unsafe_source_reason(path: Path) -> str:
    broad_roots = {
        Path(path.anchor).resolve(),
        CODEX_HOME.resolve(),
        CODEX_HOME.parent.resolve(),
        (CODEX_HOME.parent / "Documents").resolve(),
        (CODEX_HOME.parent / "Desktop").resolve(),
    }
    for variable in ("SystemRoot", "ProgramFiles", "ProgramFiles(x86)"):
        value = os.environ.get(variable)
        if value:
            broad_roots.add(Path(value).resolve())
    if path in broad_roots:
        return "不能把磁盘根目录、用户主目录、整个 Documents/Desktop、Codex 根目录或系统目录作为项目扫描源"
    automatic_roots = [
        (CODEX_HOME / "skills").resolve(),
        (CODEX_HOME / "plugins" / "cache").resolve(),
        (CODEX_HOME.parent / ".agents" / "skills").resolve(),
    ]
    for automatic_root in automatic_roots:
        if (
            path == automatic_root
            or automatic_root in path.parents
            or path in automatic_root.parents
        ):
            return (
                "Project sources cannot overlap Codex automatic Skill locations. "
                "Use the automatic source switch instead."
            )
    return ""


def _project_skill_files(root: Path, mode: str) -> list[Path]:
    if not root.is_dir():
        raise ValueError(f"扫描目录不存在：{root}")
    reason = _unsafe_source_reason(root)
    if reason:
        raise ValueError(reason)
    if mode == "single-skill":
        skill_file = root / "SKILL.md"
        if not skill_file.is_file():
            raise ValueError("“单个 Skill”模式要求所选文件夹内直接存在 SKILL.md")
        return [skill_file]
    if mode != "skill-container":
        raise ValueError("扫描模式必须是 skill-container 或 single-skill")
    candidates = [
        child / "SKILL.md"
        for child in sorted(root.iterdir(), key=lambda item: item.name.lower())
        if child.is_dir() and not child.is_symlink() and (child / "SKILL.md").is_file()
    ]
    if not candidates:
        if (root / "SKILL.md").is_file():
            raise ValueError("这个文件夹本身是一个 Skill，请改用“单个 Skill”模式")
        raise ValueError("“Skill 容器”模式要求至少一个直接子文件夹包含 SKILL.md")
    if len(candidates) > MAX_PROJECT_SKILLS_PER_SOURCE:
        raise ValueError(f"单个项目来源最多允许 {MAX_PROJECT_SKILLS_PER_SOURCE} 个直接子 Skill")
    return candidates


def _recursive_skill_files(root: Path, ignored_parts: set[str]) -> tuple[list[Path], bool]:
    candidates: list[Path] = []
    if not root.is_dir():
        return candidates, False
    for current, directories, filenames in os.walk(root, followlinks=False):
        current_path = Path(current)
        directories[:] = sorted(
            [
                name
                for name in directories
                if name not in ignored_parts and not (current_path / name).is_symlink()
            ],
            key=str.lower,
        )
        if "SKILL.md" in filenames:
            candidates.append(current_path / "SKILL.md")
            if len(candidates) >= MAX_AUTOMATIC_SKILLS_PER_SOURCE:
                return candidates, True
    return candidates, False


def _automatic_definitions(config: dict[str, Any]) -> list[dict[str, Any]]:
    enabled = config.get("automatic", {})
    return [
        {
            "id": "automatic-personal",
            "key": "personal",
            "label": "Codex 个人 Skills",
            "path": str((CODEX_HOME / "skills").resolve()),
            "enabled": bool(enabled.get("personal", True)),
            "mode": "skill-container",
            "source_kind": "personal",
        },
        {
            "id": "automatic-system",
            "key": "system",
            "label": "Codex 系统 Skills",
            "path": str((CODEX_HOME / "skills" / ".system").resolve()),
            "enabled": bool(enabled.get("system", True)),
            "mode": "skill-container",
            "source_kind": "system",
        },
        {
            "id": "automatic-plugins",
            "key": "plugins",
            "label": "Codex 插件缓存",
            "path": str((CODEX_HOME / "plugins" / "cache").resolve()),
            "enabled": bool(enabled.get("plugins", True)),
            "mode": "recursive",
            "source_kind": "plugin",
        },
        {
            "id": "automatic-agents-global",
            "key": "agents_global",
            "label": "Agents 兼容 Skills",
            "path": str((CODEX_HOME.parent / ".agents" / "skills").resolve()),
            "enabled": bool(enabled.get("agents_global", True)),
            "mode": "skill-container",
            "source_kind": "personal",
        },
    ]


def _legacy_project_sources() -> list[dict[str, Any]]:
    roots: list[dict[str, Any]] = []
    data = _json_file(PROJECT_ROOTS_PATH, [])
    if isinstance(data, dict):
        data = data.get("roots", [])
    if isinstance(data, list):
        for item in data:
            if isinstance(item, str):
                item = {"path": item}
            if isinstance(item, dict) and item.get("path"):
                roots.append({**item, "mode": str(item.get("mode") or "skill-container")})
    return roots


def _clean_ignore_parts(values: object) -> list[str]:
    if not isinstance(values, list):
        values = []
    clean = {
        str(value).strip()
        for value in values
        if isinstance(value, str)
        and value.strip()
        and "/" not in value
        and "\\" not in value
        and value.strip() not in {".", "..", "SKILL.md"}
    }
    if len(clean) > 64:
        raise ValueError("忽略目录名称最多允许 64 个")
    return sorted(set(IGNORED_PARTS) | clean)


def _custom_ignore_parts(values: object) -> list[str]:
    return sorted(set(_clean_ignore_parts(values)) - set(IGNORED_PARTS))


def _normalize_project_source(item: object) -> dict[str, Any]:
    if isinstance(item, str):
        item = {"path": item}
    if not isinstance(item, dict):
        raise ValueError("项目扫描源必须是对象")
    path = _expanded_path(item.get("path"))
    mode = str(item.get("mode") or "skill-container")
    if mode not in VALID_SOURCE_MODES:
        raise ValueError("扫描模式必须是 skill-container 或 single-skill")
    label = str(item.get("label") or path.name or path.parent.name).strip()[:120]
    if not label:
        raise ValueError("扫描来源名称不能为空")
    return {
        "id": str(item.get("id") or _source_id(path, mode))[:80],
        "path": str(path),
        "label": label,
        "enabled": bool(item.get("enabled", True)),
        "mode": mode,
    }


def _normalize_scan_sources(data: object) -> tuple[dict[str, Any], list[str]]:
    if not isinstance(data, dict):
        data = {}
    automatic = {key: True for key in AUTOMATIC_SOURCE_KEYS}
    raw_automatic = data.get("automatic", {})
    if isinstance(raw_automatic, dict):
        for key in AUTOMATIC_SOURCE_KEYS:
            if key in raw_automatic:
                automatic[key] = bool(raw_automatic[key])
    raw_projects = data.get("project_sources", data.get("roots", []))
    if not isinstance(raw_projects, list):
        raw_projects = []
    if len(raw_projects) > MAX_PROJECT_SOURCES:
        raise ValueError(f"项目扫描源最多允许 {MAX_PROJECT_SOURCES} 个")
    projects: list[dict[str, Any]] = []
    errors: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(raw_projects):
        try:
            source = _normalize_project_source(item)
            key = source["path"].lower()
            if key in seen:
                errors.append(
                    f"Project source {index + 1}: the same path cannot be configured twice."
                )
                continue
            seen.add(key)
            projects.append(source)
            if source["enabled"]:
                _project_skill_files(Path(source["path"]), source["mode"])
        except (OSError, ValueError) as exc:
            errors.append(f"项目来源 {index + 1}：{exc}")
    raw_ignore_parts = data.get("custom_ignore_parts", data.get("ignore_parts", []))
    return {
        "schema_version": 2,
        "automatic": automatic,
        "project_sources": projects,
        "ignore_parts": _clean_ignore_parts(raw_ignore_parts),
        "custom_ignore_parts": _custom_ignore_parts(raw_ignore_parts),
    }, errors


def load_scan_sources() -> dict[str, Any]:
    configured = SCAN_SOURCES_PATH.is_file()
    load_errors: list[str] = []
    data: object = {}
    if configured:
        try:
            data = json.loads(SCAN_SOURCES_PATH.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            load_errors.append(
                "The local scan-source configuration could not be read. "
                "Repair or restore scan-sources.local.json before scanning."
            )
    if not isinstance(data, dict):
        data = {}
    if not configured:
        data = {**_default_scan_sources(), "project_sources": _legacy_project_sources()}
    config, errors = _normalize_scan_sources(data)
    config["_load_errors"] = [*load_errors, *errors]
    return config


def _environment_project_sources() -> tuple[list[dict[str, Any]], list[str]]:
    raw_env = os.environ.get("SKILL_PROJECT_ROOTS", "")
    sources: list[dict[str, Any]] = []
    errors: list[str] = []
    seen: set[str] = set()
    for index, value in enumerate(part for part in raw_env.split(os.pathsep) if part.strip()):
        try:
            source = _normalize_project_source(
                {
                    "path": value.strip(),
                    "label": Path(value.strip()).name,
                    "enabled": True,
                    "mode": "skill-container",
                }
            )
            key = source["path"].lower()
            if key in seen:
                continue
            seen.add(key)
            source.update(
                {
                    "id": "environment-" + source["id"].removeprefix("project-"),
                    "managed_by": "environment",
                    "configurable": False,
                }
            )
            _project_skill_files(Path(source["path"]), source["mode"])
            sources.append(source)
        except (OSError, ValueError) as exc:
            errors.append(f"Environment source {index + 1}: {exc}")
    return sources, errors


def _effective_project_sources(config: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    environment, errors = _environment_project_sources()
    return [*config.get("project_sources", []), *environment], errors


def _automatic_skill_files(source: dict[str, Any], ignored_parts: set[str]) -> tuple[list[Path], bool]:
    root = Path(source["path"])
    if not root.is_dir():
        return [], False
    if source["key"] == "plugins":
        return _recursive_skill_files(root, ignored_parts)
    candidates = [
        child / "SKILL.md"
        for child in sorted(root.iterdir(), key=lambda item: item.name.lower())
        if child.is_dir()
        and not child.is_symlink()
        and (child / "SKILL.md").is_file()
        and not (source["key"] == "personal" and child.name == ".system")
    ]
    return candidates[:MAX_AUTOMATIC_SKILLS_PER_SOURCE], len(candidates) > MAX_AUTOMATIC_SKILLS_PER_SOURCE


def _candidate_files(candidates: list[Path]) -> list[dict[str, str]]:
    return [
        {"name": _frontmatter(skill_file)[0], "skill_file": str(skill_file.resolve())}
        for skill_file in candidates
    ]


def preview_scan_sources(data: object) -> dict[str, Any]:
    config, errors = _normalize_scan_sources(data)
    if isinstance(data, dict):
        errors.extend(
            str(item)
            for item in data.get("_load_errors", [])
            if isinstance(item, str) and item.strip()
        )
    project_sources, environment_errors = _effective_project_sources(config)
    errors.extend(environment_errors)
    ignored_parts = set(config["ignore_parts"])
    sources: list[dict[str, Any]] = []
    all_paths: set[str] = set()
    path_owners: dict[str, str] = {}

    def register_candidates(source_label: str, candidates: list[Path]) -> None:
        for skill_file in candidates:
            key = str(skill_file.parent.resolve()).lower()
            existing = path_owners.get(key)
            if existing and existing != source_label:
                errors.append(
                    f'The Skill folder "{skill_file.parent.name}" is included by both '
                    f'"{existing}" and "{source_label}". Remove the overlapping source.'
                )
                continue
            path_owners[key] = source_label
            all_paths.add(key)

    for source in _automatic_definitions(config):
        path = Path(source["path"])
        candidates, truncated = _automatic_skill_files(source, ignored_parts) if source["enabled"] else ([], False)
        status = "disabled" if not source["enabled"] else "missing" if not path.is_dir() else "ready" if candidates else "empty"
        warnings = ["达到自动来源扫描上限，结果已截断"] if truncated else []
        candidate_files = _candidate_files(candidates)
        register_candidates(source["label"], candidates)
        sources.append({
            **source,
            "configurable": False,
            "exists": path.is_dir(),
            "status": status,
            "found_count": len(candidates),
            "sample": [item["name"] for item in candidate_files[:5]],
            "candidate_files": candidate_files,
            "warnings": warnings,
        })
    for source in project_sources:
        path = Path(source["path"])
        project_errors: list[str] = []
        candidates: list[Path] = []
        if source["enabled"]:
            try:
                candidates = _project_skill_files(path, source["mode"])
            except (OSError, ValueError) as exc:
                project_errors.append(str(exc))
        status = "disabled" if not source["enabled"] else "error" if project_errors else "ready"
        candidate_files = _candidate_files(candidates)
        register_candidates(source["label"], candidates)
        sources.append({
            **source,
            "key": source["id"],
            "source_kind": "project",
            "configurable": source.get("managed_by") != "environment",
            "managed_by": source.get("managed_by", "local-config"),
            "exists": path.is_dir(),
            "status": status,
            "found_count": len(candidates),
            "sample": [item["name"] for item in candidate_files[:8]],
            "candidate_files": candidate_files,
            "warnings": project_errors,
        })
        errors.extend(f"{source['label']}：{message}" for message in project_errors)
    canonical = json.dumps(config, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "valid": not errors,
        "writes_performed": False,
        "preview_token": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "config": config,
        "sources": sources,
        "total_candidates": len(all_paths),
        "errors": errors,
    }


def scan_sources_overview() -> dict[str, Any]:
    config = load_scan_sources()
    preview = preview_scan_sources(config)
    preview.update({
        "configured": SCAN_SOURCES_PATH.is_file(),
        "legacy_config_detected": PROJECT_ROOTS_PATH.is_file() and not SCAN_SOURCES_PATH.is_file(),
        "config_path": str(SCAN_SOURCES_PATH),
        "storage": "local-only",
    })
    return preview


def save_scan_sources(
    data: object,
    *,
    preview_token: str = "",
    require_preview: bool = False,
) -> dict[str, Any]:
    preview = preview_scan_sources(data)
    if not preview["valid"]:
        raise ValueError("；".join(preview["errors"]))
    if require_preview and not preview_token:
        raise ValueError("请先预览扫描结果，再保存配置")
    if require_preview and preview_token != preview["preview_token"]:
        raise ValueError("配置已变化，请重新预览后再保存")
    SCAN_SOURCES_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = SCAN_SOURCES_PATH.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(preview["config"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(SCAN_SOURCES_PATH)
    return {
        "config": preview["config"],
        "config_path": str(SCAN_SOURCES_PATH),
        "writes_performed": True,
        "preview": preview,
    }


def save_scan_sources_and_scan(
    data: object,
    *,
    preview_token: str = "",
    require_preview: bool = False,
) -> dict[str, Any]:
    previous_exists = SCAN_SOURCES_PATH.is_file()
    previous_bytes = SCAN_SOURCES_PATH.read_bytes() if previous_exists else b""
    result = save_scan_sources(
        data,
        preview_token=preview_token,
        require_preview=require_preview,
    )
    try:
        result["scan"] = scan_skills()
        return result
    except Exception as exc:
        rollback = SCAN_SOURCES_PATH.with_suffix(".rollback.tmp")
        if previous_exists:
            rollback.write_bytes(previous_bytes)
            rollback.replace(SCAN_SOURCES_PATH)
        elif SCAN_SOURCES_PATH.exists():
            SCAN_SOURCES_PATH.unlink()
        raise ValueError(
            "The scan failed, so the previous source configuration was restored. "
            "Run doctor for details, then preview and try again."
        ) from exc


def shareable_scan_sources_template() -> dict[str, Any]:
    data = _json_file(SCAN_SOURCES_TEMPLATE_PATH, _default_scan_sources())
    config, _ = _normalize_scan_sources(data)
    config["project_sources"] = []
    return {
        "filename": "scan-sources.example.json",
        "config": config,
        "contains_local_paths": False,
        "writes_performed": False,
    }


def load_project_roots() -> list[dict[str, Any]]:
    return [
        source
        for source in load_scan_sources()["project_sources"]
        if source.get("enabled", True)
    ]


def save_project_roots(roots: list[dict[str, Any]]) -> dict[str, Any]:
    current = load_scan_sources()
    current["project_sources"] = [
        {**item, "mode": str(item.get("mode") or "skill-container")}
        for item in roots
    ]
    result = save_scan_sources(current)
    return {
        "roots": result["config"]["project_sources"],
        "config": result["config_path"],
        "writes_performed": True,
    }


def save_project_roots_and_scan(roots: list[dict[str, Any]]) -> dict[str, Any]:
    current = load_scan_sources()
    current["project_sources"] = [
        {**item, "mode": str(item.get("mode") or "skill-container")}
        for item in roots
    ]
    result = save_scan_sources_and_scan(current)
    return {
        "roots": result["config"]["project_sources"],
        "config": result["config_path"],
        "writes_performed": True,
        "scan": result["scan"],
    }


def _plugin_source(skill_file: Path) -> tuple[str, int, str]:
    verified_urls = _public_sources().get("__verified_urls__", {})
    for parent in skill_file.parents:
        manifest = parent / ".codex-plugin" / "plugin.json"
        if not manifest.is_file():
            continue
        data = _json_file(manifest, {})
        values: list[str] = []
        if isinstance(data, dict):
            for key in ("repository", "homepage", "source", "url"):
                value = data.get(key)
                if isinstance(value, str):
                    values.append(value)
                elif isinstance(value, dict):
                    values.extend(str(v) for v in value.values() if isinstance(v, str))
        for value in values:
            if _valid_web_url(value):
                verification = verified_urls.get(value, {}) if isinstance(verified_urls, dict) else {}
                is_verified = int(bool(isinstance(verification, dict) and verification.get("verified")))
                confidence = "catalog-verified" if is_verified else "plugin-manifest-unverified"
                return value, is_verified, confidence
        break
    return "", 0, ""


def _skill_record(
    skill_file: Path,
    source_kind: str,
    source_label: str,
    *,
    project_root: str = "",
) -> dict[str, Any]:
    name, description = _frontmatter(skill_file)
    interface = _interface_metadata(skill_file.parent)
    catalog = _catalog().get(name, {})
    public_source = _public_sources().get(name, {})
    if source_kind == "system":
        classification = "system"
    elif source_kind == "plugin":
        classification = "plugin"
    else:
        classification = "unknown"
    catalog_classification = str(catalog.get("classification") or "")
    if source_kind in {"personal", "project"} and catalog_classification in VALID_CLASSIFICATIONS:
        classification = catalog_classification

    upstream_source = str(public_source.get("url") or catalog.get("upstream_source") or "")
    upstream_verified = int(bool(public_source.get("verified") or catalog.get("upstream_verified")))
    source_confidence = str(public_source.get("confidence") or catalog.get("source_confidence") or "")
    if source_kind == "plugin" and not upstream_source:
        upstream_source, upstream_verified, source_confidence = _plugin_source(skill_file)
    if upstream_source and not _valid_web_url(upstream_source):
        upstream_source, upstream_verified, source_confidence = "", 0, ""

    portability = str(catalog.get("portability") or ("not-applicable" if source_kind in {"system", "plugin"} else "unknown"))
    if portability not in VALID_PORTABILITY:
        portability = "unknown"
    display_name = str(catalog.get("display_name") or interface.get("display_name") or _default_display_name(name))
    category = str(catalog.get("category") or _category_for(name, description))
    modified = datetime.fromtimestamp(skill_file.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")
    folder = skill_file.parent.resolve()
    return {
        "id": _skill_id(folder),
        "name": name,
        "display_name": display_name,
        "description": description,
        "path": str(folder),
        "source_kind": source_kind,
        "source_label": source_label,
        "classification": classification,
        "upstream_source": upstream_source,
        "upstream_author": str(public_source.get("author") or catalog.get("upstream_author") or ""),
        "upstream_verified": upstream_verified,
        "source_confidence": source_confidence,
        "version_hash": _version_hash(skill_file),
        "content_hash": _content_hash(folder),
        "category": category,
        "origin_scope": "project" if source_kind == "project" else source_kind,
        "origin_path": str(folder) if source_kind == "project" else "",
        "origin_hash": "",
        "project_root": project_root,
        "portability": portability,
        "showcase_level": str(catalog.get("showcase_level") or "standard"),
        "showcase_status": str(catalog.get("showcase_status") or "generated"),
        "modified_at": modified,
    }


def discover_skills() -> list[dict[str, Any]]:
    discovered: list[dict[str, Any]] = []
    config = load_scan_sources()
    load_errors = config.get("_load_errors", [])
    if load_errors:
        raise ValueError(" ".join(str(item) for item in load_errors))
    project_sources, environment_errors = _effective_project_sources(config)
    if environment_errors:
        raise ValueError(" ".join(environment_errors))
    ignored_parts = set(config["ignore_parts"])
    for source in _automatic_definitions(config):
        if not source["enabled"]:
            continue
        root = Path(source["path"])
        candidates, _ = _automatic_skill_files(source, ignored_parts)
        for skill_file in candidates:
            source_label = source["label"]
            if source["key"] == "plugins":
                relative = skill_file.relative_to(root)
                source_label = "插件 · " + relative.parts[0]
            discovered.append(
                _skill_record(skill_file, source["source_kind"], source_label)
            )

    for root_config in project_sources:
        if not root_config.get("enabled", True):
            continue
        root = Path(root_config["path"])
        try:
            candidates = _project_skill_files(root, root_config["mode"])
        except (OSError, ValueError):
            continue
        for skill_file in candidates:
            discovered.append(
                _skill_record(
                    skill_file,
                    "project",
                    f"项目 · {root_config['label']}",
                    project_root=str(root),
                )
            )

    unique: dict[str, dict[str, Any]] = {}
    for record in discovered:
        unique.setdefault(record["path"].lower(), record)
    return list(unique.values())


def _primary_priority(row: sqlite3.Row | dict[str, Any]) -> tuple[int, str]:
    item = dict(row)
    if item["source_kind"] == "personal" and item["classification"] == "self-authored":
        rank = 0
    elif item["source_kind"] == "personal" and item["classification"] == "adapted":
        rank = 1
    elif item["source_kind"] == "personal":
        rank = 2
    elif item["source_kind"] == "project":
        rank = 3
    elif item["source_kind"] == "system":
        rank = 4
    else:
        rank = 5
    return rank, item["path"].lower()


def _refresh_relationships(connection: sqlite3.Connection) -> None:
    rows = connection.execute("SELECT * FROM skills WHERE is_present=1").fetchall()
    connection.execute(
        "UPDATE skills SET duplicate_group='', duplicate_of='', is_primary=1, "
        "sync_status=CASE WHEN source_kind IN ('system','plugin') THEN 'not-applicable' "
        "WHEN source_kind='project' THEN 'review-required' ELSE 'standalone' END WHERE is_present=1"
    )

    by_fingerprint: dict[tuple[str, str], list[sqlite3.Row]] = {}
    for row in rows:
        by_fingerprint.setdefault((row["name"].lower(), row["content_hash"]), []).append(row)
    for (name, content_hash), group in by_fingerprint.items():
        if len(group) < 2:
            continue
        primary = sorted(group, key=_primary_priority)[0]
        group_id = hashlib.sha1(f"{name}|{content_hash}".encode("utf-8")).hexdigest()[:12]
        for row in group:
            is_primary = int(row["id"] == primary["id"])
            status = "current" if is_primary and row["source_kind"] == "personal" else "identical-copy"
            connection.execute(
                "UPDATE skills SET duplicate_group=?, duplicate_of=?, is_primary=?, sync_status=? WHERE id=?",
                (group_id, "" if is_primary else primary["id"], is_primary, status, row["id"]),
            )

    rows = connection.execute("SELECT * FROM skills WHERE is_present=1").fetchall()
    by_name: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        by_name.setdefault(row["name"].lower(), []).append(row)

    for same_name in by_name.values():
        globals_ = [row for row in same_name if row["source_kind"] == "personal"]
        projects = [row for row in same_name if row["source_kind"] == "project"]
        for project in projects:
            if not globals_:
                status = "promotion-ready" if project["portability"] == "portable" else "review-required"
                connection.execute("UPDATE skills SET sync_status=? WHERE id=?", (status, project["id"]))
                continue
            if project["duplicate_of"]:
                continue
            connection.execute("UPDATE skills SET sync_status='name-collision' WHERE id=?", (project["id"],))

        for snapshot in globals_:
            if not snapshot["origin_path"]:
                continue
            origin = next((row for row in projects if row["path"].lower() == snapshot["origin_path"].lower()), None)
            if origin is None:
                connection.execute("UPDATE skills SET sync_status='source-missing' WHERE id=?", (snapshot["id"],))
                continue
            source_changed = bool(snapshot["origin_hash"] and origin["content_hash"] != snapshot["origin_hash"])
            snapshot_changed = bool(snapshot["origin_hash"] and snapshot["content_hash"] != snapshot["origin_hash"])
            if source_changed and snapshot_changed:
                status = "diverged"
            elif source_changed:
                status = "update-available"
            elif snapshot_changed:
                status = "snapshot-modified"
            else:
                status = "current"
            connection.execute("UPDATE skills SET sync_status=? WHERE id=?", (status, snapshot["id"]))


def _scan_delta_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item["id"],
        "name": item["name"],
        "display_name": item.get("display_name") or item["name"],
        "source_kind": item["source_kind"],
        "classification": item.get("classification") or "unknown",
    }


def scan_skills() -> dict[str, Any]:
    records = discover_skills()
    now = utc_now()
    with connect() as connection:
        previous = {
            row["id"]: dict(row)
            for row in connection.execute(
                "SELECT id, name, display_name, source_kind, classification, content_hash "
                "FROM skills WHERE is_present=1"
            )
        }
        discovered = {item["id"]: item for item in records}
        added = [
            _scan_delta_item(discovered[skill_id])
            for skill_id in sorted(discovered.keys() - previous.keys())
        ]
        removed = [
            _scan_delta_item(previous[skill_id])
            for skill_id in sorted(previous.keys() - discovered.keys())
        ]
        updated = [
            _scan_delta_item(discovered[skill_id])
            for skill_id in sorted(discovered.keys() & previous.keys())
            if discovered[skill_id]["content_hash"] != previous[skill_id]["content_hash"]
        ]
        unchanged_count = len(records) - len(added) - len(updated)
        connection.execute(
            "UPDATE skills SET is_present=0, removed_at=COALESCE(removed_at, ?), updated_at=? "
            "WHERE is_present=1",
            (now, now),
        )
        for item in records:
            connection.execute(
                """
                INSERT INTO skills (
                    id, name, display_name, description, path, source_kind, source_label,
                    classification, upstream_source, upstream_author, upstream_verified,
                    source_confidence, version_hash, content_hash, category, origin_scope,
                    origin_path, origin_hash, project_root, portability, showcase_level,
                    showcase_status, modified_at, discovered_at, updated_at,
                    last_seen_at, removed_at, is_present
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 1)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    display_name=excluded.display_name,
                    description=excluded.description,
                    path=excluded.path,
                    source_kind=excluded.source_kind,
                    source_label=excluded.source_label,
                    classification=CASE
                        WHEN skills.classification='unknown' AND excluded.classification!='unknown'
                        THEN excluded.classification ELSE skills.classification END,
                    upstream_source=CASE WHEN excluded.source_kind IN ('system','plugin') THEN excluded.upstream_source WHEN skills.upstream_source!='' THEN skills.upstream_source ELSE excluded.upstream_source END,
                    upstream_author=CASE WHEN excluded.source_kind IN ('system','plugin') THEN excluded.upstream_author WHEN skills.upstream_author!='' THEN skills.upstream_author ELSE excluded.upstream_author END,
                    upstream_verified=CASE WHEN excluded.source_kind IN ('system','plugin') THEN excluded.upstream_verified WHEN skills.upstream_verified=1 THEN 1 ELSE excluded.upstream_verified END,
                    source_confidence=CASE WHEN excluded.source_kind IN ('system','plugin') THEN excluded.source_confidence WHEN skills.source_confidence!='' THEN skills.source_confidence ELSE excluded.source_confidence END,
                    version_hash=excluded.version_hash,
                    content_hash=excluded.content_hash,
                    category=excluded.category,
                    origin_scope=excluded.origin_scope,
                    origin_path=CASE WHEN skills.origin_path!='' AND excluded.source_kind!='project' THEN skills.origin_path ELSE excluded.origin_path END,
                    origin_hash=CASE WHEN skills.origin_hash!='' THEN skills.origin_hash ELSE excluded.origin_hash END,
                    project_root=excluded.project_root,
                    portability=excluded.portability,
                    showcase_level=excluded.showcase_level,
                    showcase_status=excluded.showcase_status,
                    modified_at=excluded.modified_at,
                    updated_at=excluded.updated_at,
                    last_seen_at=excluded.last_seen_at,
                    removed_at=NULL,
                    is_present=1
                """,
                (
                    item["id"], item["name"], item["display_name"], item["description"], item["path"],
                    item["source_kind"], item["source_label"], item["classification"],
                    item["upstream_source"], item["upstream_author"], item["upstream_verified"],
                    item["source_confidence"], item["version_hash"], item["content_hash"],
                    item["category"], item["origin_scope"], item["origin_path"], item["origin_hash"],
                    item["project_root"], item["portability"], item["showcase_level"],
                    item["showcase_status"], item["modified_at"], now, now, now,
                ),
            )
            if item["content_hash"]:
                connection.execute(
                    """
                    INSERT INTO skill_versions(
                      skill_id, content_hash, version_hash, source_modified_at,
                      first_seen_at, last_seen_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(skill_id, content_hash) DO UPDATE SET
                      version_hash=excluded.version_hash,
                      source_modified_at=excluded.source_modified_at,
                      last_seen_at=excluded.last_seen_at
                    """,
                    (
                        item["id"], item["content_hash"], item["version_hash"],
                        item["modified_at"], now, now,
                    ),
                )
        _refresh_relationships(connection)
        counts = dict(
            connection.execute(
                "SELECT source_kind, COUNT(*) AS count FROM skills WHERE is_present=1 GROUP BY source_kind"
            ).fetchall()
        )
        duplicates = connection.execute(
            "SELECT COUNT(*) FROM skills WHERE is_present=1 AND duplicate_of!=''"
        ).fetchone()[0]
        delta = {"added": added, "updated": updated, "removed": removed}
        cursor = connection.execute(
            """
            INSERT INTO scan_runs(
                scanned_at, total_locations, added_count, updated_count, removed_count,
                unchanged_count, duplicate_locations, delta_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now,
                len(records),
                len(added),
                len(updated),
                len(removed),
                unchanged_count,
                int(duplicates),
                json.dumps(delta, ensure_ascii=False),
            ),
        )
        connection.execute(
            "DELETE FROM scan_runs WHERE id NOT IN (SELECT id FROM scan_runs ORDER BY id DESC LIMIT 50)"
        )
        connection.commit()
    return {
        "run_id": cursor.lastrowid,
        "scanned_at": now,
        "scanned": len(records),
        "counts": counts,
        "duplicates_grouped": int(duplicates),
        "added_count": len(added),
        "updated_count": len(updated),
        "removed_count": len(removed),
        "unchanged_count": unchanged_count,
        "delta": delta,
        "project_roots": load_project_roots(),
        "database": str(DB_PATH),
    }


def latest_scan() -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute("SELECT * FROM scan_runs ORDER BY id DESC LIMIT 1").fetchone()
    if row is None:
        return None
    item = dict(row)
    item["delta"] = json.loads(item.pop("delta_json") or "{}")
    return item


def reconcile_missing_skills() -> dict[str, Any]:
    """Mark indexed Skill paths that no longer contain SKILL.md as removed."""
    if not DB_PATH.is_file():
        return {"checked": 0, "removed_count": 0, "removed": [], "writes_performed": False}
    now = utc_now()
    with connect() as connection:
        rows = connection.execute(
            "SELECT id, name, display_name, path FROM skills WHERE is_present=1"
        ).fetchall()
        missing = [
            dict(row)
            for row in rows
            if not (Path(row["path"]) / "SKILL.md").is_file()
        ]
        for item in missing:
            connection.execute(
                "UPDATE skills SET is_present=0, removed_at=COALESCE(removed_at, ?), updated_at=? "
                "WHERE id=? AND is_present=1",
                (now, now, item["id"]),
            )
        connection.commit()
    return {
        "checked": len(rows),
        "removed_count": len(missing),
        "removed": [
            {"id": item["id"], "name": item["name"], "display_name": item["display_name"]}
            for item in missing
        ],
        "writes_performed": bool(missing),
        "observed_at": now,
    }


def _maps(connection: sqlite3.Connection) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    usage: dict[str, dict[str, Any]] = {}
    feedback_map: dict[str, dict[str, Any]] = {}
    cutoff_7 = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat(timespec="seconds")
    cutoff_30 = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat(timespec="seconds")
    for row in connection.execute(
        """
        SELECT skill_id,
          COUNT(*) AS uses_all,
          SUM(CASE WHEN used_at >= ? THEN 1 ELSE 0 END) AS uses_7,
          SUM(CASE WHEN used_at >= ? THEN 1 ELSE 0 END) AS uses_30,
          MAX(used_at) AS last_used
        FROM usage_events GROUP BY skill_id
        """,
        (cutoff_7, cutoff_30),
    ):
        usage[row["skill_id"]] = dict(row)
    for row in connection.execute(
        """
        SELECT u.skill_id, u.version_hash AS last_used_version,
          COALESCE(w.label, '') AS last_workspace_label,
          COALESCE(w.context_kind, 'unknown') AS last_workspace_kind
        FROM usage_events u
        LEFT JOIN workspaces w ON w.id=u.workspace_id
        WHERE u.id=(
          SELECT u2.id FROM usage_events u2
          WHERE u2.skill_id=u.skill_id
          ORDER BY u2.used_at DESC, u2.id DESC LIMIT 1
        )
        """
    ):
        usage.setdefault(row["skill_id"], {}).update(dict(row))
    for row in connection.execute(
        """
        SELECT skill_id, COUNT(*) AS feedback_count, AVG(NULLIF(rating, 0)) AS average_rating,
          SUM(CASE WHEN outcome='failed' THEN 1 ELSE 0 END) AS failed_count,
          SUM(CASE WHEN outcome='partial' THEN 1 ELSE 0 END) AS partial_count
        FROM feedback GROUP BY skill_id
        """
    ):
        feedback_map[row["skill_id"]] = dict(row)
    return usage, feedback_map


def _locations(connection: sqlite3.Connection, item: dict[str, Any]) -> list[dict[str, Any]]:
    if not item.get("is_present"):
        rows = connection.execute(
            "SELECT id, path, source_kind, source_label, content_hash, sync_status, is_primary, is_present "
            "FROM skills WHERE id=?",
            (item["id"],),
        ).fetchall()
    elif item.get("duplicate_group"):
        rows = connection.execute(
            "SELECT id, path, source_kind, source_label, content_hash, sync_status, is_primary, is_present "
            "FROM skills WHERE is_present=1 AND duplicate_group=? ORDER BY is_primary DESC, source_kind, path",
            (item["duplicate_group"],),
        ).fetchall()
    else:
        rows = connection.execute(
            "SELECT id, path, source_kind, source_label, content_hash, sync_status, is_primary, is_present "
            "FROM skills WHERE is_present=1 AND id=?",
            (item["id"],),
        ).fetchall()
    return [dict(row) for row in rows]


def list_skills(
    scope: str = "all",
    query: str = "",
    classification: str = "",
    sort: str = "usage30",
    category: str = "",
    include_duplicates: bool = False,
    presence: str = "present",
    ownership: str = "",
) -> list[dict[str, Any]]:
    if presence not in {"present", "removed", "all"}:
        raise ValueError("presence must be present, removed, or all")
    if ownership not in {"", "owned", "inbox"}:
        raise ValueError("ownership must be owned or inbox")
    localization_metadata, public_localizations = _public_localizations()
    with connect() as connection:
        where = {
            "present": "WHERE is_present=1",
            "removed": "WHERE is_present=0",
            "all": "",
        }[presence]
        rows = connection.execute(f"SELECT * FROM skills {where}").fetchall()
        usage, feedback_map = _maps(connection)
        pending = dict(
            connection.execute(
                "SELECT skill_id, COUNT(*) FROM proposals WHERE status='pending' GROUP BY skill_id"
            ).fetchall()
        )

        result: list[dict[str, Any]] = []
        mine = {"self-authored", "adapted", "unknown"}
        public = {"public-installed", "system", "plugin"}
        query_lower = query.strip().lower()
        for row in rows:
            item = _with_public_display(
                dict(row),
                localization_metadata,
                public_localizations,
            )
            if not include_duplicates and not item["is_primary"]:
                continue
            if scope == "my" and item["classification"] not in mine and item["source_kind"] != "project":
                continue
            if scope == "public" and item["classification"] not in public:
                continue
            if ownership == "owned" and not (
                item["classification"] in {"self-authored", "adapted"}
                or item["source_kind"] == "project"
            ):
                continue
            if ownership == "inbox" and not (
                item["classification"] == "unknown"
                and item["source_kind"] != "project"
            ):
                continue
            if classification and item["classification"] != classification:
                continue
            if category and item["category"] != category:
                continue
            haystack = (
                f'{item["name"]} {item["display_name"]} {item["description"]} '
                f'{item["display_name_zh"]} {item["description_zh"]} {item["use_when_zh"]} '
                f'{item["source_label"]} {item["source_status_label"]} {item["category"]}'
            ).lower()
            if query_lower and query_lower not in haystack:
                continue
            u = usage.get(item["id"], {})
            f = feedback_map.get(item["id"], {})
            item.update(
                uses_all=int(u.get("uses_all") or 0),
                uses_7=int(u.get("uses_7") or 0),
                uses_30=int(u.get("uses_30") or 0),
                last_used=u.get("last_used"),
                last_workspace_label=str(u.get("last_workspace_label") or ""),
                last_workspace_kind=str(u.get("last_workspace_kind") or "unknown"),
                last_used_version=str(u.get("last_used_version") or ""),
                feedback_count=int(f.get("feedback_count") or 0),
                average_rating=round(float(f["average_rating"]), 1) if f.get("average_rating") is not None else None,
                failed_count=int(f.get("failed_count") or 0),
                partial_count=int(f.get("partial_count") or 0),
                pending_proposals=int(pending.get(item["id"], 0)),
            )
            item["presence_status"] = "present" if item["is_present"] else "removed"
            item["presence_label"] = "当前可用" if item["is_present"] else "已移除"
            item["locations"] = _locations(connection, item)
            item["duplicate_count"] = max(0, len(item["locations"]) - 1)
            dissatisfaction = 6 - item["average_rating"] if item["average_rating"] is not None else 0
            item["improvement_priority"] = round(
                item["uses_30"] * dissatisfaction + item["failed_count"] * 3 + item["partial_count"] * 1.5,
                1,
            )
            result.append(item)

    sorters = {
        "usage30": lambda item: (
            -item["uses_30"],
            (item["display_name_zh"] or item["display_name"]).lower(),
        ),
        "priority": lambda item: (
            -item["improvement_priority"],
            -item["uses_30"],
            (item["display_name_zh"] or item["display_name"]).lower(),
        ),
        "recent": lambda item: (item["last_used"] is None, -(datetime.fromisoformat(item["last_used"]).timestamp()) if item["last_used"] else 0),
        "removed": lambda item: (
            item["removed_at"] is None,
            -(datetime.fromisoformat(item["removed_at"]).timestamp()) if item["removed_at"] else 0,
        ),
        "name": lambda item: (item["display_name_zh"] or item["display_name"]).lower(),
        "showcase": lambda item: (
            item["showcase_level"] != "rich",
            -item["uses_30"],
            (item["display_name_zh"] or item["display_name"]).lower(),
        ),
    }
    return sorted(result, key=sorters.get(sort, sorters["usage30"]))


def summary(scope: str = "all") -> dict[str, Any]:
    all_skills = list_skills()
    skills = list_skills(scope=scope)
    owned_skills = list_skills(scope="my", ownership="owned")
    inbox_skills = list_skills(scope="my", ownership="inbox")
    removed_skills = list_skills(presence="removed")
    skill_ids = {item["id"] for item in skills}
    total_30 = sum(item["uses_30"] for item in skills)
    feedback_count = sum(item["feedback_count"] for item in skills)
    avg_rating = (
        sum((item["average_rating"] or 0) * item["feedback_count"] for item in skills) / feedback_count
        if feedback_count else None
    )
    pending = sum(item["pending_proposals"] for item in skills)
    with connect() as connection:
        usage_rows = connection.execute(
            "SELECT skill_id, substr(used_at, 1, 10) AS day FROM usage_events WHERE used_at >= ?",
            ((datetime.now(timezone.utc) - timedelta(days=13)).date().isoformat(),),
        ).fetchall()
        duplicate_locations = connection.execute(
            "SELECT COUNT(*) FROM skills WHERE is_present=1 AND duplicate_of!=''"
        ).fetchone()[0]
    daily_map = Counter(row["day"] for row in usage_rows if row["skill_id"] in skill_ids)
    today = datetime.now(timezone.utc).date()
    trend = [
        {"day": (today - timedelta(days=offset)).isoformat(), "count": daily_map.get((today - timedelta(days=offset)).isoformat(), 0)}
        for offset in range(13, -1, -1)
    ]
    classifications = Counter(item["classification"] for item in all_skills)
    source_kinds = Counter(item["source_kind"] for item in all_skills)
    categories = Counter(item["category"] for item in skills)
    tracked_skills = sum(item["uses_all"] > 0 for item in skills)
    return {
        "total_skills": len(all_skills),
        "my_skills": len(owned_skills),
        "local_skills": len(list_skills(scope="my")),
        "public_skills": len(list_skills(scope="public")),
        "inbox_skills": len(inbox_skills),
        "removed_skills": len(removed_skills),
        "inventory": {
            "owned": len(owned_skills),
            "inbox": len(inbox_skills),
            "removed": len(removed_skills),
        },
        "project_skills": source_kinds["project"],
        "unknown_skills": classifications["unknown"],
        "duplicate_locations": int(duplicate_locations),
        "updates_available": sum(item["sync_status"] in {"update-available", "diverged"} for item in all_skills),
        "uses_30": total_30,
        "usage_tracking": {
            "coverage": "partial",
            "label": "部分记录",
            "tracked_skills": tracked_skills,
            "eligible_skills": len(skills),
            "detail": "仅统计通过 Skill Manager 日志写入的调用，不代表全部使用次数。",
        },
        "average_rating": round(float(avg_rating), 1) if avg_rating is not None else None,
        "pending_proposals": pending,
        "classifications": dict(classifications),
        "source_kinds": dict(source_kinds),
        "categories": dict(categories),
        "trend": trend,
        "latest_scan": latest_scan(),
        "updated_at": utc_now(),
    }


def list_workflows(skill_name: str = "") -> list[dict[str, Any]]:
    skills = list_skills(presence="present")
    by_name = {str(item["name"]).lower(): item for item in skills}
    observations: dict[str, dict[str, Any]] = {}
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT workflow_id, COUNT(DISTINCT run_id) AS recorded_runs,
                   MAX(used_at) AS last_recorded_at
            FROM usage_events
            WHERE workflow_id!='' AND run_id!=''
            GROUP BY workflow_id
            """
        ).fetchall()
        multi_rows = connection.execute(
            """
            SELECT workflow_id, COUNT(*) AS multi_skill_runs
            FROM (
              SELECT workflow_id, run_id
              FROM usage_events
              WHERE workflow_id!='' AND run_id!=''
              GROUP BY workflow_id, run_id
              HAVING COUNT(DISTINCT skill_id) >= 2
            )
            GROUP BY workflow_id
            """
        ).fetchall()
    for row in rows:
        observations[str(row["workflow_id"])] = {
            "recorded_runs": int(row["recorded_runs"] or 0),
            "multi_skill_runs": 0,
            "last_recorded_at": row["last_recorded_at"],
        }
    for row in multi_rows:
        observations.setdefault(
            str(row["workflow_id"]),
            {"recorded_runs": 0, "multi_skill_runs": 0, "last_recorded_at": None},
        )["multi_skill_runs"] = int(row["multi_skill_runs"] or 0)

    result: list[dict[str, Any]] = []
    match_name = skill_name.strip().lower()
    for raw in _workflow_catalog():
        workflow_id = str(raw.get("id") or "").strip()
        raw_steps = raw.get("steps", [])
        if not workflow_id or not isinstance(raw_steps, list):
            continue
        steps: list[dict[str, Any]] = []
        for index, raw_step in enumerate(raw_steps, start=1):
            if isinstance(raw_step, str):
                raw_step = {"skill": raw_step}
            if not isinstance(raw_step, dict):
                continue
            name = str(raw_step.get("skill") or "").strip()
            if not name:
                continue
            installed = by_name.get(name.lower())
            steps.append(
                {
                    "position": index,
                    "skill": name,
                    "role": str(raw_step.get("role") or "").strip()[:240],
                    "optional": bool(raw_step.get("optional")),
                    "available": installed is not None,
                    "display_name": (
                        str(raw_step.get("label") or "").strip()
                        or (
                            installed.get("display_name_zh")
                            or installed.get("display_name")
                            or name
                            if installed
                            else name
                        )
                    ),
                    "classification": installed.get("classification") if installed else "",
                    "source_kind": installed.get("source_kind") if installed else "",
                }
            )
        if match_name and not any(step["skill"].lower() == match_name for step in steps):
            continue
        required = [step for step in steps if not step["optional"]]
        available_required = sum(step["available"] for step in required)
        observation = observations.get(
            workflow_id,
            {"recorded_runs": 0, "multi_skill_runs": 0, "last_recorded_at": None},
        )
        result.append(
            {
                "id": workflow_id,
                "title": str(raw.get("title") or workflow_id).strip()[:160],
                "description": str(raw.get("description") or "").strip()[:500],
                "best_for": str(raw.get("best_for") or "").strip()[:300],
                "source_type": "curated",
                "source_label": "作者建议组合",
                "steps": steps,
                "step_count": len(steps),
                "available_count": sum(step["available"] for step in steps),
                "required_count": len(required),
                "available_required_count": available_required,
                "ready": bool(required and available_required == len(required)),
                "copy_prompt": str(raw.get("copy_prompt") or "").strip()[:2000],
                **observation,
            }
        )
    return sorted(
        result,
        key=lambda item: (
            not item["ready"],
            -item["multi_skill_runs"],
            -item["available_count"],
            item["title"].lower(),
        ),
    )


def insights(scope: str = "my") -> dict[str, Any]:
    if scope not in {"all", "my", "public"}:
        raise ValueError("scope must be all, my, or public")
    skills = (
        list_skills(scope="my", ownership="owned")
        if scope == "my"
        else list_skills(scope=scope)
    )
    skill_ids = {str(item["id"]) for item in skills}
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    cutoff_iso = cutoff.isoformat(timespec="seconds")
    today = datetime.now(timezone.utc).date()
    events: list[dict[str, Any]] = []
    with connect() as connection:
        if skill_ids:
            placeholders = ",".join("?" for _ in skill_ids)
            rows = connection.execute(
                f"""
                SELECT u.id, u.skill_id, s.name AS skill_name, s.display_name,
                       u.used_at, u.invocation_type, u.version_hash,
                       u.workspace_id, COALESCE(w.label, '') AS workspace_label,
                       u.task_category, u.run_id, u.workflow_id,
                       u.step_position, u.step_outcome,
                       f.outcome, f.rating
                FROM usage_events u
                JOIN skills s ON s.id=u.skill_id
                LEFT JOIN workspaces w ON w.id=u.workspace_id
                LEFT JOIN feedback f ON f.id=(
                  SELECT f2.id FROM feedback f2
                  WHERE f2.usage_event_id=u.id
                  ORDER BY f2.created_at DESC, f2.id DESC LIMIT 1
                )
                WHERE u.skill_id IN ({placeholders}) AND u.used_at>=?
                ORDER BY u.used_at, u.id
                """,
                (*sorted(skill_ids), cutoff_iso),
            ).fetchall()
            events = [dict(row) for row in rows]

    day_counts = Counter(str(event["used_at"])[:10] for event in events)
    trend = [
        {
            "day": (today - timedelta(days=offset)).isoformat(),
            "count": int(day_counts.get((today - timedelta(days=offset)).isoformat(), 0)),
        }
        for offset in range(29, -1, -1)
    ]
    invocation = Counter(str(event["invocation_type"] or "unknown") for event in events)
    outcomes = Counter(str(event["outcome"] or "") for event in events if event.get("outcome"))
    workspace_counts: dict[str, dict[str, Any]] = {}
    for event in events:
        key = str(event.get("workspace_id") or "unassigned")
        item = workspace_counts.setdefault(
            key,
            {
                "workspace_id": key,
                "label": str(event.get("workspace_label") or "未关联项目"),
                "event_count": 0,
                "skills": set(),
                "last_used": "",
            },
        )
        item["event_count"] += 1
        item["skills"].add(str(event["skill_id"]))
        item["last_used"] = max(item["last_used"], str(event["used_at"]))
    projects = sorted(
        [
            {
                "workspace_id": item["workspace_id"],
                "label": item["label"],
                "event_count": item["event_count"],
                "skill_count": len(item["skills"]),
                "last_used": item["last_used"],
            }
            for item in workspace_counts.values()
        ],
        key=lambda item: (-item["event_count"], item["label"]),
    )

    run_groups: dict[str, list[dict[str, Any]]] = {}
    run_event_count = 0
    for event in events:
        run_id = str(event.get("run_id") or "")
        if not run_id:
            continue
        run_event_count += 1
        run_groups.setdefault(run_id, []).append(event)
    edge_counts: Counter[tuple[str, str]] = Counter()
    multi_skill_runs = 0
    for run_events in run_groups.values():
        ordered = sorted(
            run_events,
            key=lambda item: (
                int(item.get("step_position") or 0) <= 0,
                int(item.get("step_position") or 0),
                str(item["used_at"]),
                int(item["id"]),
            ),
        )
        distinct: list[str] = []
        display: dict[str, str] = {}
        for event in ordered:
            name = str(event["skill_name"])
            display[name] = str(event["display_name"] or name)
            if not distinct or distinct[-1] != name:
                distinct.append(name)
        if len(set(distinct)) < 2:
            continue
        multi_skill_runs += 1
        for left, right in zip(distinct, distinct[1:]):
            if left != right:
                edge_counts[(left, right)] += 1
    co_use = [
        {
            "from_skill": left,
            "from_display": next(
                (item["display_name"] for item in skills if item["name"] == left),
                left,
            ),
            "to_skill": right,
            "to_display": next(
                (item["display_name"] for item in skills if item["name"] == right),
                right,
            ),
            "run_count": count,
            "evidence": "共享同一任务运行编号",
        }
        for (left, right), count in edge_counts.most_common(12)
    ]

    high_use_low_satisfaction = [
        item
        for item in skills
        if item["uses_30"] > 0
        and (
            item["failed_count"] > 0
            or item["partial_count"] > 0
            or (item["average_rating"] is not None and item["average_rating"] < 4)
        )
    ]
    high_use_low_satisfaction.sort(
        key=lambda item: (
            -item["failed_count"],
            -item["partial_count"],
            item["average_rating"] if item["average_rating"] is not None else 9,
            -item["uses_30"],
        )
    )
    untried = [item for item in skills if item["uses_all"] == 0]
    reliable = [
        item
        for item in skills
        if item["feedback_count"] >= 2
        and item["average_rating"] is not None
        and item["average_rating"] >= 4
        and item["failed_count"] == 0
    ]
    reliable.sort(key=lambda item: (-item["average_rating"], -item["feedback_count"]))
    tracked = sum(item["uses_all"] > 0 for item in skills)
    feedback_events = sum(outcomes.values())

    def compact(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": item["id"],
            "name": item["name"],
            "display_name": item["display_name"],
            "uses_30": item["uses_30"],
            "uses_all": item["uses_all"],
            "last_used": item["last_used"],
            "last_workspace_label": item["last_workspace_label"],
            "feedback_count": item["feedback_count"],
            "average_rating": item["average_rating"],
            "failed_count": item["failed_count"],
            "partial_count": item["partial_count"],
        }

    return {
        "scope": scope,
        "period_days": 30,
        "recorded_events": len(events),
        "active_days": len(day_counts),
        "tracked_skills": tracked,
        "eligible_skills": len(skills),
        "coverage": {
            "status": "partial",
            "skill_ratio": round(tracked / len(skills), 3) if skills else 0,
            "run_event_ratio": round(run_event_count / len(events), 3) if events else 0,
            "detail": "只统计已写入本地日志的数据；未记录不等于没有使用。",
        },
        "trend": trend,
        "invocation": {
            "explicit": int(invocation["explicit"]),
            "implicit": int(invocation["implicit"]),
        },
        "outcomes": {
            "solved": int(outcomes["solved"]),
            "partial": int(outcomes["partial"]),
            "failed": int(outcomes["failed"]),
            "sample_size": int(feedback_events),
        },
        "projects": projects[:12],
        "categories": [
            {"name": name, "count": count}
            for name, count in Counter(
                str(event.get("task_category") or "其他") for event in events
            ).most_common()
        ],
        "top_skills": [
            compact(item)
            for item in sorted(
                skills,
                key=lambda item: (-item["uses_30"], -item["uses_all"], item["display_name"]),
            )[:12]
        ],
        "attention": {
            "high_use_low_satisfaction": [
                compact(item) for item in high_use_low_satisfaction[:8]
            ],
            "untried": [compact(item) for item in untried[:12]],
            "reliable": [compact(item) for item in reliable[:8]],
        },
        "run_tracking": {
            "recorded_runs": len(run_groups),
            "multi_skill_runs": multi_skill_runs,
            "events_with_run_id": run_event_count,
            "co_use": co_use,
            "detail": (
                "只有共享同一运行编号的调用才进入组合统计；"
                "历史调用不会按时间接近自动推断。"
            ),
        },
        "workflows": list_workflows(),
        "inventory": summary(scope),
        "updated_at": utc_now(),
    }


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _workspace_context(
    connection: sqlite3.Connection,
    workspace_path: str = "",
    workspace_label: str = "",
    workspace_kind: str = "",
) -> dict[str, str]:
    try:
        current = Path(workspace_path or os.getcwd()).expanduser().resolve()
    except (OSError, RuntimeError):
        current = Path.cwd().resolve()
    if current.is_file():
        current = current.parent

    root = current
    detected_kind = "temporary"
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            root = candidate
            detected_kind = "project"
            break
    try:
        codex_home = CODEX_HOME.expanduser().resolve()
        center_home = CENTER_HOME.expanduser().resolve()
        if _is_within(root, codex_home) or _is_within(root, center_home):
            detected_kind = "global"
    except (OSError, RuntimeError):
        pass

    clean_kind = workspace_kind.strip().lower() or detected_kind
    if clean_kind not in VALID_WORKSPACE_KINDS:
        raise ValueError("invalid workspace kind")
    default_label = {
        "global": "全局任务",
        "temporary": root.name or "临时任务",
        "unknown": "未命名项目",
    }.get(clean_kind, root.name or "未命名项目")
    clean_label = re.sub(r"[\x00-\x1f\x7f]", "", workspace_label.strip() or default_label)[:80]

    row = connection.execute(
        "SELECT value FROM app_meta WHERE key='workspace_hash_salt'"
    ).fetchone()
    if row is None:
        raise RuntimeError("workspace privacy salt is missing")
    normalized = os.path.normcase(str(root))
    fingerprint = hashlib.sha256(
        f"{row[0]}\0{normalized}".encode("utf-8", errors="surrogatepass")
    ).hexdigest()[:24]
    workspace_id = f"ws-{fingerprint}"
    now = utc_now()
    connection.execute(
        """
        INSERT INTO workspaces(id, label, context_kind, first_seen_at, last_seen_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          label=CASE WHEN excluded.label!='' THEN excluded.label ELSE workspaces.label END,
          context_kind=excluded.context_kind,
          last_seen_at=excluded.last_seen_at
        """,
        (workspace_id, clean_label, clean_kind, now, now),
    )
    return {"id": workspace_id, "label": clean_label, "context_kind": clean_kind}


def record_usage(
    skill_name: str,
    invocation_type: str,
    skill_path: str = "",
    workspace_path: str = "",
    workspace_label: str = "",
    workspace_kind: str = "",
    task_category: str = "",
    run_id: str = "",
    workflow_id: str = "",
    step_position: int = 0,
    step_outcome: str = "",
) -> dict[str, Any]:
    if invocation_type not in {"explicit", "implicit"}:
        raise ValueError("invocation_type must be explicit or implicit")
    clean_run_id = run_id.strip()
    clean_workflow_id = workflow_id.strip()
    if clean_run_id and (
        len(clean_run_id) > 120
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]*", clean_run_id)
    ):
        raise ValueError("run_id must be an opaque identifier using letters, numbers, . _ : or -")
    if clean_workflow_id and (
        len(clean_workflow_id) > 120
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]*", clean_workflow_id)
    ):
        raise ValueError("workflow_id must use letters, numbers, . _ : or -")
    clean_step_position = int(step_position or 0)
    if clean_step_position < 0 or clean_step_position > 1000:
        raise ValueError("step_position must be between 0 and 1000")
    clean_step_outcome = step_outcome.strip()
    if clean_step_outcome not in VALID_STEP_OUTCOMES:
        raise ValueError("step_outcome must be solved, partial, failed, skipped, or empty")
    with connect() as connection:
        if skill_path:
            row = connection.execute("SELECT * FROM skills WHERE lower(path)=lower(?)", (str(Path(skill_path).resolve()),)).fetchone()
        else:
            row = connection.execute(
                """
                SELECT * FROM skills WHERE lower(name)=lower(?) AND is_present=1
                ORDER BY CASE classification WHEN 'self-authored' THEN 0 WHEN 'adapted' THEN 1 ELSE 2 END,
                         CASE source_kind WHEN 'personal' THEN 0 WHEN 'project' THEN 1 ELSE 2 END LIMIT 1
                """,
                (skill_name,),
            ).fetchone()
        if row is None:
            raise KeyError(f"skill not found: {skill_name or skill_path}")
        used_at = utc_now()
        workspace = _workspace_context(
            connection,
            workspace_path=workspace_path,
            workspace_label=workspace_label,
            workspace_kind=workspace_kind,
        )
        clean_category = (task_category.strip() or row["category"] or "其他")[:60]
        if clean_run_id:
            connection.execute(
                """
                INSERT INTO task_runs(
                  id, workflow_id, started_at, last_activity_at,
                  workspace_id, task_category
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  workflow_id=CASE
                    WHEN excluded.workflow_id!='' THEN excluded.workflow_id
                    ELSE task_runs.workflow_id
                  END,
                  last_activity_at=excluded.last_activity_at,
                  workspace_id=COALESCE(excluded.workspace_id, task_runs.workspace_id),
                  task_category=CASE
                    WHEN excluded.task_category!='' THEN excluded.task_category
                    ELSE task_runs.task_category
                  END
                """,
                (
                    clean_run_id,
                    clean_workflow_id,
                    used_at,
                    used_at,
                    workspace["id"],
                    clean_category,
                ),
            )
        cursor = connection.execute(
            """
            INSERT INTO usage_events(
              skill_id, used_at, invocation_type, version_hash, workspace_id, task_category,
              run_id, workflow_id, step_position, step_outcome
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["id"],
                used_at,
                invocation_type,
                row["version_hash"],
                workspace["id"],
                clean_category,
                clean_run_id,
                clean_workflow_id,
                clean_step_position,
                clean_step_outcome,
            ),
        )
        connection.commit()
        return {
            "event_id": cursor.lastrowid,
            "skill": row["name"],
            "skill_id": row["id"],
            "used_at": used_at,
            "invocation_type": invocation_type,
            "version_hash": row["version_hash"],
            "workspace": workspace,
            "task_category": clean_category,
            "run_id": clean_run_id,
            "workflow_id": clean_workflow_id,
            "step_position": clean_step_position,
            "step_outcome": clean_step_outcome,
        }


def list_usage_events(
    skill_id: str = "",
    workspace_id: str = "",
    limit: int = 30,
) -> list[dict[str, Any]]:
    clean_limit = max(1, min(int(limit), 200))
    where = ["1=1"]
    values: list[Any] = []
    if skill_id:
        where.append("u.skill_id=?")
        values.append(skill_id)
    if workspace_id:
        where.append("u.workspace_id=?")
        values.append(workspace_id)
    values.append(clean_limit)
    with connect() as connection:
        rows = connection.execute(
            f"""
            SELECT
              u.id, u.skill_id, s.name AS skill_name, s.display_name,
              u.used_at, u.invocation_type, u.version_hash,
              u.workspace_id, COALESCE(w.label, '') AS workspace_label,
              COALESCE(w.context_kind, 'unknown') AS workspace_kind,
              u.task_category, u.run_id, u.workflow_id,
              u.step_position, u.step_outcome,
              f.id AS feedback_id, f.outcome, f.rating, f.issue_tags,
              f.note, f.created_at AS feedback_created_at
            FROM usage_events u
            JOIN skills s ON s.id=u.skill_id
            LEFT JOIN workspaces w ON w.id=u.workspace_id
            LEFT JOIN feedback f ON f.id=(
              SELECT f2.id FROM feedback f2
              WHERE f2.usage_event_id=u.id
              ORDER BY f2.created_at DESC, f2.id DESC LIMIT 1
            )
            WHERE {" AND ".join(where)}
            ORDER BY u.used_at DESC, u.id DESC
            LIMIT ?
            """,
            tuple(values),
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["issue_tags"] = json.loads(item["issue_tags"] or "[]")
        item["rating"] = int(item["rating"] or 0)
        result.append(item)
    return result


def _classification_file_signals(folder: Path) -> dict[str, Any]:
    skill_file = folder / "SKILL.md"
    if not skill_file.is_file():
        return {"evidence": [], "upstream_source": "", "upstream_author": ""}
    text = _read_text(skill_file)
    author_match = re.search(r"(?mi)^\s*author:\s*['\"]?(.+?)['\"]?\s*$", text)
    license_match = re.search(r"(?mi)^\s*license:\s*['\"]?(.+?)['\"]?\s*$", text)
    urls = [
        value.rstrip(".,);]}>\"'")
        for value in re.findall(r"https?://[^\s<>()\[\]{}\"']+", text)
        if _valid_web_url(value.rstrip(".,);]}>\"'"))
    ]
    evidence: list[str] = []
    author = author_match.group(1).strip()[:160] if author_match else ""
    if author:
        evidence.append(f"SKILL.md 声明作者：{author}")
    if license_match:
        evidence.append(f"SKILL.md 声明许可证：{license_match.group(1).strip()[:80]}")
    upstream = next(
        (
            value
            for value in urls
            if "github.com" in urlparse(value).netloc.lower()
        ),
        "",
    )
    if upstream:
        evidence.append("SKILL.md 包含公开 GitHub 来源")
    return {
        "evidence": evidence[:3],
        "upstream_source": upstream[:500],
        "upstream_author": author,
    }


def _classification_hint_map() -> dict[str, dict[str, Any]]:
    payload = _json_file(CLASSIFICATION_HINTS_PATH, {})
    if not isinstance(payload, dict):
        return {}
    entries = payload.get("suggestions", payload)
    if not isinstance(entries, dict):
        return {}
    return {
        str(name).strip().lower(): dict(value)
        for name, value in entries.items()
        if str(name).strip() and isinstance(value, dict)
    }


def classification_review() -> dict[str, Any]:
    hints = _classification_hint_map()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat(timespec="seconds")
    with connect_readonly() as connection:
        rows = connection.execute(
            """
            SELECT s.*,
              COALESCE((
                SELECT COUNT(*) FROM usage_events u
                WHERE u.skill_id=s.id AND u.used_at>=?
              ), 0) AS uses_30
            FROM skills s
            WHERE s.is_present=1
              AND s.is_primary=1
              AND s.source_kind='personal'
              AND s.classification='unknown'
            ORDER BY s.display_name COLLATE NOCASE, s.name COLLATE NOCASE
            """,
            (cutoff,),
        ).fetchall()

    candidates: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        file_signals = _classification_file_signals(Path(item["path"]))
        hint = hints.get(item["name"].lower(), {})
        suggested = str(hint.get("classification") or "")
        confidence = str(hint.get("confidence") or "")
        evidence = [
            str(value).strip()[:240]
            for value in hint.get("evidence", [])
            if str(value).strip()
        ][:4]
        upstream_source = str(hint.get("upstream_source") or file_signals["upstream_source"]).strip()[:500]
        upstream_author = str(hint.get("upstream_author") or file_signals["upstream_author"]).strip()[:160]

        if suggested not in VALID_REVIEW_CLASSIFICATIONS:
            if file_signals["evidence"]:
                suggested = "public-installed"
                confidence = "high" if upstream_source and upstream_author else "medium"
                evidence = list(file_signals["evidence"])
            else:
                suggested = "unknown"
                confidence = "low"
                evidence = ["未找到可靠的作者或上游来源线索，需要人工确认"]
        else:
            for signal in file_signals["evidence"]:
                if signal not in evidence and len(evidence) < 4:
                    evidence.append(signal)

        if confidence not in VALID_SUGGESTION_CONFIDENCE:
            confidence = "medium" if suggested != "unknown" else "low"
        if upstream_source and not _valid_web_url(upstream_source):
            upstream_source = ""
            evidence.append("本地提示中的上游地址无效，已忽略")
        candidates.append(
            {
                "skill_id": item["id"],
                "name": item["name"],
                "display_name": item["display_name"],
                "description": item["description"],
                "source_label": item["source_label"],
                "category": item["category"],
                "version_hash": item["version_hash"],
                "content_hash": item["content_hash"],
                "uses_30": int(item["uses_30"] or 0),
                "suggested_classification": suggested,
                "confidence": confidence,
                "evidence": evidence[:4],
                "upstream_source": upstream_source,
                "upstream_author": upstream_author,
                "selected_by_default": confidence == "high" and suggested != "unknown",
            }
        )

    rank = {"high": 0, "medium": 1, "low": 2}
    candidates.sort(
        key=lambda item: (
            rank.get(item["confidence"], 3),
            -int(item["uses_30"]),
            item["display_name"].lower(),
        )
    )
    suggestion_counts = Counter(item["suggested_classification"] for item in candidates)
    confidence_counts = Counter(item["confidence"] for item in candidates)
    return {
        "candidates": candidates,
        "summary": {
            "total": len(candidates),
            "high_confidence": confidence_counts["high"],
            "needs_review": confidence_counts["medium"] + confidence_counts["low"],
            "suggested_self_authored": suggestion_counts["self-authored"],
            "suggested_public_installed": suggestion_counts["public-installed"],
            "suggested_adapted": suggestion_counts["adapted"],
            "unresolved": suggestion_counts["unknown"],
        },
        "writes_performed": False,
        "boundary": "建议来自本地证据和本机提示；只有明确提交的条目才会改变分类。",
    }


def _classification_changes(
    decisions: list[dict[str, Any]],
    *,
    only_unknown: bool,
    allow_unknown: bool = False,
) -> list[dict[str, Any]]:
    if not isinstance(decisions, list) or not decisions:
        raise ValueError("请至少选择一个来源建议")
    if len(decisions) > 100:
        raise ValueError("一次最多整理 100 个 Skill")
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for decision in decisions:
        if not isinstance(decision, dict):
            raise ValueError("来源决定格式无效")
        skill_id = str(decision.get("skill_id") or "").strip()
        classification = str(decision.get("classification") or "").strip()
        if not skill_id or skill_id in seen:
            raise ValueError("来源决定包含空 ID 或重复 Skill")
        allowed = VALID_REVIEW_CLASSIFICATIONS | ({"unknown"} if allow_unknown else set())
        if classification not in allowed:
            raise ValueError("来源决定只能是我的原创、公开安装或改造版")
        upstream_source = str(decision.get("upstream_source") or "").strip()[:500]
        upstream_author = str(decision.get("upstream_author") or "").strip()[:160]
        if classification == "adapted" and not upstream_source:
            raise ValueError("改造版必须填写上游来源")
        if upstream_source and not _valid_web_url(upstream_source):
            raise ValueError("上游来源必须是有效的 http 或 https 地址")
        seen.add(skill_id)
        normalized.append(
            {
                "skill_id": skill_id,
                "classification": classification,
                "upstream_source": upstream_source,
                "upstream_author": upstream_author,
            }
        )

    placeholders = ",".join("?" for _ in normalized)
    with connect_readonly() as connection:
        rows = connection.execute(
            f"SELECT * FROM skills WHERE id IN ({placeholders})",
            tuple(item["skill_id"] for item in normalized),
        ).fetchall()
    by_id = {row["id"]: dict(row) for row in rows}
    changes: list[dict[str, Any]] = []
    for decision in normalized:
        row = by_id.get(decision["skill_id"])
        if row is None or not row["is_present"]:
            raise KeyError("待整理的 Skill 不存在或已移除")
        if row["source_kind"] != "personal":
            raise ValueError("批量来源整理只适用于全局个人 Skill")
        if only_unknown and row["classification"] != "unknown":
            raise ValueError(f"{row['display_name']} 已被归类，请刷新建议")
        changes.append(
            {
                **decision,
                "name": row["name"],
                "display_name": row["display_name"],
                "from_classification": row["classification"],
                "content_hash": row["content_hash"],
            }
        )
    return sorted(changes, key=lambda item: item["skill_id"])


def _classification_preview_token(changes: list[dict[str, Any]]) -> str:
    canonical = [
        {
            "skill_id": item["skill_id"],
            "from": item["from_classification"],
            "to": item["classification"],
            "upstream_source": item["upstream_source"],
            "upstream_author": item["upstream_author"],
            "content_hash": item["content_hash"],
        }
        for item in changes
    ]
    return hashlib.sha256(
        json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def preview_classifications(decisions: list[dict[str, Any]]) -> dict[str, Any]:
    changes = _classification_changes(decisions, only_unknown=True)
    counts = Counter(item["classification"] for item in changes)
    return {
        "preview_token": _classification_preview_token(changes),
        "change_count": len(changes),
        "summary": {
            "self-authored": counts["self-authored"],
            "public-installed": counts["public-installed"],
            "adapted": counts["adapted"],
        },
        "changes": [
            {
                key: item[key]
                for key in (
                    "skill_id",
                    "name",
                    "display_name",
                    "from_classification",
                    "classification",
                    "upstream_source",
                    "upstream_author",
                )
            }
            for item in changes
        ],
        "writes_performed": False,
    }


def _catalog_with_classifications(changes: list[dict[str, Any]]) -> dict[str, Any]:
    catalog = _json_file(LOCAL_CATALOG_PATH, {})
    catalog = dict(catalog) if isinstance(catalog, dict) else {}
    confirmed_at = utc_now()
    for item in changes:
        entry = catalog.get(item["name"], {})
        entry = dict(entry) if isinstance(entry, dict) else {}
        entry["classification"] = item["classification"]
        entry["classification_confirmed_at"] = confirmed_at
        entry["source_confidence"] = "user-confirmed-local"
        if item["upstream_source"]:
            entry["upstream_source"] = item["upstream_source"]
        else:
            entry.pop("upstream_source", None)
        if item["upstream_author"]:
            entry["upstream_author"] = item["upstream_author"]
        else:
            entry.pop("upstream_author", None)
        entry["upstream_verified"] = False
        catalog[item["name"]] = entry
    return catalog


def _write_json_temporary(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{secrets.token_hex(6)}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return temporary


def _restore_local_catalog(previous: bytes | None) -> None:
    if previous is None:
        LOCAL_CATALOG_PATH.unlink(missing_ok=True)
        return
    temporary = LOCAL_CATALOG_PATH.with_name(
        f"{LOCAL_CATALOG_PATH.name}.{secrets.token_hex(6)}.restore"
    )
    temporary.write_bytes(previous)
    temporary.replace(LOCAL_CATALOG_PATH)


def _persist_classification_changes(changes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    previous_catalog = (
        LOCAL_CATALOG_PATH.read_bytes()
        if LOCAL_CATALOG_PATH.is_file()
        else None
    )
    temporary = _write_json_temporary(
        LOCAL_CATALOG_PATH,
        _catalog_with_classifications(changes),
    )
    catalog_replaced = False
    try:
        with connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            for item in changes:
                current = connection.execute(
                    "SELECT source_kind, classification, content_hash FROM skills WHERE id=? AND is_present=1",
                    (item["skill_id"],),
                ).fetchone()
                if current is None:
                    raise KeyError("待整理的 Skill 不存在或已移除")
                if current["source_kind"] != "personal":
                    raise ValueError("来源归类只适用于全局个人 Skill")
                if (
                    current["classification"] != item["from_classification"]
                    or current["content_hash"] != item["content_hash"]
                ):
                    raise ValueError("Skill 状态已变化，请重新预览")
                connection.execute(
                    """
                    UPDATE skills
                    SET classification=?, upstream_source=?, upstream_author=?,
                        upstream_verified=0, source_confidence='user-confirmed-local',
                        updated_at=?
                    WHERE id=?
                    """,
                    (
                        item["classification"],
                        item["upstream_source"],
                        item["upstream_author"],
                        utc_now(),
                        item["skill_id"],
                    ),
                )
            _refresh_relationships(connection)
            temporary.replace(LOCAL_CATALOG_PATH)
            catalog_replaced = True
            try:
                connection.commit()
            except Exception:
                _restore_local_catalog(previous_catalog)
                catalog_replaced = False
                raise
    except Exception:
        temporary.unlink(missing_ok=True)
        if catalog_replaced:
            _restore_local_catalog(previous_catalog)
        raise
    return [
        {
            "id": item["skill_id"],
            "name": item["name"],
            "classification": item["classification"],
            "upstream_source": item["upstream_source"],
            "upstream_author": item["upstream_author"],
        }
        for item in changes
    ]


def apply_classifications(
    decisions: list[dict[str, Any]],
    preview_token: str,
) -> dict[str, Any]:
    changes = _classification_changes(decisions, only_unknown=True)
    expected = _classification_preview_token(changes)
    if not preview_token or not secrets.compare_digest(preview_token, expected):
        raise ValueError("来源决定已变化，请重新预览后再应用")
    results = _persist_classification_changes(changes)
    return {
        "applied_count": len(results),
        "results": results,
        "writes_performed": True,
    }


def set_classification(
    skill_id: str,
    classification: str,
    upstream_source: str = "",
    upstream_author: str = "",
) -> dict[str, Any]:
    decisions = [
        {
            "skill_id": skill_id,
            "classification": classification,
            "upstream_source": upstream_source,
            "upstream_author": upstream_author,
        }
    ]
    changes = _classification_changes(decisions, only_unknown=False, allow_unknown=True)
    return _persist_classification_changes(changes)[0]


def add_feedback(
    skill_id: str,
    outcome: str,
    rating: int,
    issue_tags: list[str],
    note: str,
    usage_event_id: int = 0,
) -> dict[str, Any]:
    if outcome not in VALID_OUTCOMES:
        raise ValueError("invalid outcome")
    if rating < 0 or rating > 5:
        raise ValueError("rating must be between 0 and 5")
    clean_tags = sorted({str(tag).strip()[:40] for tag in issue_tags if str(tag).strip()})[:8]
    clean_note = note.strip()[:1200]
    with connect() as connection:
        event = None
        if usage_event_id:
            event = connection.execute(
                "SELECT id, skill_id FROM usage_events WHERE id=?",
                (int(usage_event_id),),
            ).fetchone()
            if event is None:
                raise KeyError("usage event not found")
            if skill_id and event["skill_id"] != skill_id:
                raise ValueError("usage event does not belong to this skill")
            skill_id = event["skill_id"]
        if not skill_id or not connection.execute(
            "SELECT 1 FROM skills WHERE id=?", (skill_id,)
        ).fetchone():
            raise KeyError("skill not found")
        created_at = utc_now()
        existing = (
            connection.execute(
                "SELECT id FROM feedback WHERE usage_event_id=? ORDER BY id DESC LIMIT 1",
                (int(usage_event_id),),
            ).fetchone()
            if usage_event_id
            else None
        )
        if existing:
            feedback_id = int(existing["id"])
            connection.execute(
                """
                UPDATE feedback
                SET outcome=?, rating=?, issue_tags=?, note=?, created_at=?
                WHERE id=?
                """,
                (
                    outcome,
                    rating,
                    json.dumps(clean_tags, ensure_ascii=False),
                    clean_note,
                    created_at,
                    feedback_id,
                ),
            )
            updated = True
        else:
            cursor = connection.execute(
                """
                INSERT INTO feedback(
                  skill_id, usage_event_id, outcome, rating, issue_tags, note, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    skill_id,
                    int(usage_event_id) if usage_event_id else None,
                    outcome,
                    rating,
                    json.dumps(clean_tags, ensure_ascii=False),
                    clean_note,
                    created_at,
                ),
            )
            feedback_id = int(cursor.lastrowid)
            updated = False
        connection.commit()
    return {
        "id": feedback_id,
        "usage_event_id": int(usage_event_id) if usage_event_id else None,
        "created_at": created_at,
        "updated": updated,
    }


def list_feedback(skill_id: str) -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT
              f.*, u.used_at, u.version_hash AS usage_version_hash,
              u.task_category, COALESCE(w.label, '') AS workspace_label,
              COALESCE(w.context_kind, 'unknown') AS workspace_kind
            FROM feedback f
            LEFT JOIN usage_events u ON u.id=f.usage_event_id
            LEFT JOIN workspaces w ON w.id=u.workspace_id
            WHERE f.skill_id=?
            ORDER BY f.created_at DESC LIMIT 30
            """,
            (skill_id,),
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["issue_tags"] = json.loads(item["issue_tags"] or "[]")
        result.append(item)
    return result


def create_proposal(skill_id: str) -> dict[str, Any]:
    with connect() as connection:
        skill = connection.execute("SELECT * FROM skills WHERE id=?", (skill_id,)).fetchone()
        if skill is None:
            raise KeyError("skill not found")
        if skill["classification"] not in {"self-authored", "adapted", "unknown"} and skill["source_kind"] != "project":
            raise ValueError("公开、系统和插件 Skill 必须先复制为个人版本才能改进")
        feedback_rows = connection.execute(
            "SELECT * FROM feedback WHERE skill_id=? ORDER BY created_at DESC LIMIT 20", (skill_id,)
        ).fetchall()
        tags: Counter[str] = Counter()
        notes: list[str] = []
        outcomes: Counter[str] = Counter()
        for row in feedback_rows:
            tags.update(json.loads(row["issue_tags"] or "[]"))
            outcomes[row["outcome"]] += 1
            if row["note"]:
                notes.append(row["note"].strip())
        tag_text = "、".join(tag for tag, _ in tags.most_common(4)) or "暂无重复问题标签"
        rationale = (
            f"基于最近 {len(feedback_rows)} 条反馈：未解决 {outcomes['failed']} 次，"
            f"部分解决 {outcomes['partial']} 次。高频问题：{tag_text}。"
        )
        if notes:
            rationale += " 代表性备注：" + "；".join(notes[:3])
        title = f"改进 {skill['name']} 的下一个版本"
        now = utc_now()
        cursor = connection.execute(
            "INSERT INTO proposals(skill_id, title, rationale, status, created_at, updated_at) VALUES (?, ?, ?, 'pending', ?, ?)",
            (skill_id, title, rationale[:2000], now, now),
        )
        connection.commit()
        return {"id": cursor.lastrowid, "skill_id": skill_id, "title": title, "rationale": rationale[:2000], "status": "pending", "created_at": now}


def list_proposals(scope: str = "all") -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT p.*, s.name AS skill_name, s.display_name, s.classification, s.source_kind
            FROM proposals p JOIN skills s ON s.id=p.skill_id
            ORDER BY CASE p.status WHEN 'pending' THEN 0 ELSE 1 END, p.created_at DESC
            """
        ).fetchall()
    mine = {"self-authored", "adapted", "unknown"}
    result = [dict(row) for row in rows]
    return [item for item in result if scope != "my" or item["classification"] in mine or item["source_kind"] == "project"]


def _resource_inventory(folder: Path) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = {"scripts": [], "assets": [], "references": [], "agents": []}
    for group in groups:
        root = folder / group
        if not root.is_dir():
            continue
        for path in _iter_content_files(root):
            groups[group].append({"path": path.relative_to(folder).as_posix(), "size": path.stat().st_size})
    groups["other"] = []
    for path in _iter_content_files(folder):
        relative = path.relative_to(folder)
        if relative.parts[0] not in groups and relative.name != "SKILL.md":
            groups["other"].append({"path": relative.as_posix(), "size": path.stat().st_size})
    return groups


def _section_lines(text: str, heading_names: set[str]) -> list[str]:
    lines = text.splitlines()
    collecting = False
    depth = 0
    result: list[str] = []
    for line in lines:
        match = re.match(r"^(#{2,4})\s+(.+?)\s*$", line)
        if match:
            label = re.sub(r"[*`_]", "", match.group(2)).strip().lower()
            if collecting and len(match.group(1)) <= depth:
                break
            if label in heading_names:
                collecting = True
                depth = len(match.group(1))
                continue
        if collecting:
            cleaned = re.sub(r"^\s*(?:[-*]|\d+[.)])\s+", "", line).strip()
            if cleaned and not cleaned.startswith("```"):
                result.append(cleaned)
    return result[:12]


def list_skill_versions(skill_id: str, limit: int = 20) -> list[dict[str, Any]]:
    if not skill_id:
        return []
    bounded_limit = max(1, min(int(limit), 100))
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT content_hash, version_hash, source_modified_at, first_seen_at, last_seen_at
            FROM skill_versions WHERE skill_id=?
            ORDER BY first_seen_at DESC, id DESC LIMIT ?
            """,
            (skill_id, bounded_limit),
        ).fetchall()
    return [dict(row) for row in rows]


def get_skill_detail(skill_id: str = "", name: str = "") -> dict[str, Any]:
    skills = list_skills(include_duplicates=True, presence="all")
    item = next((skill for skill in skills if skill_id and skill["id"] == skill_id), None)
    if item is None and name:
        matches = [skill for skill in skills if skill["name"].lower() == name.lower()]
        item = sorted(matches, key=_primary_priority)[0] if matches else None
    if item is None:
        raise KeyError("skill not found")
    if item["is_present"] and (
        item["source_kind"] in {"system", "plugin"}
        or item["classification"] in {"system", "plugin", "public-installed"}
    ):
        raise ValueError("公开 Skill 不生成本地详情页，请打开已验证的上游来源")
    folder = Path(item["path"])
    skill_file = folder / "SKILL.md"
    file_available = skill_file.is_file()
    text = _read_text(skill_file) if file_available else ""
    catalog = _catalog().get(item["name"], {})
    prompts = catalog.get("prompts") or (
        [f"Use ${item['name']} to help me complete this task: <describe the outcome and constraints>."]
        if file_available else []
    )
    workflow = catalog.get("workflow") or _section_lines(text, {"workflow", "core workflow", "process", "application"})
    if not workflow:
        workflow = (
            ["确认目标、输入与约束", "按 Skill 工作流执行", "验证结果并记录使用反馈"]
            if file_available
            else ["该 Skill 已从本机移除；这里只保留来源、版本和已记录使用历史。"]
        )
    empty_resources = {key: [] for key in ("scripts", "assets", "references", "agents", "other")}
    return {
        "skill": item,
        "availability": {
            "status": item["presence_status"],
            "file_available": file_available,
            "can_execute": bool(item["is_present"] and file_available),
        },
        "guide": {
            "tagline": catalog.get("tagline") or item["description"],
            "best_for": catalog.get("best_for") or [item["description"] or "历史记录"],
            "not_for": catalog.get("not_for") or ["与该 Skill 描述无关的普通任务"],
            "prompts": prompts,
            "workflow": workflow,
            "inputs": catalog.get("inputs") or ["明确的目标", "相关上下文或素材", "输出限制"],
            "outputs": catalog.get("outputs") or ["符合 Skill 工作流的可验证结果"],
            "showcase_url": catalog.get("showcase_url") or "",
            "showcase_caption": catalog.get("showcase_caption") or "",
        },
        "resources": _resource_inventory(folder) if file_available else empty_resources,
        "versions": list_skill_versions(item["id"]),
        "feedback": list_feedback(item["id"]),
        "usage_events": list_usage_events(skill_id=item["id"], limit=30),
        "related_workflows": list_workflows(item["name"]),
    }


def _file_map(folder: Path) -> dict[str, Path]:
    return {path.relative_to(folder).as_posix(): path for path in _iter_content_files(folder)}


def compare_skill_folders(left: Path, right: Path, max_diff_lines: int = 500) -> dict[str, Any]:
    left_files = _file_map(left) if left.is_dir() else {}
    right_files = _file_map(right) if right.is_dir() else {}
    added = sorted(set(right_files) - set(left_files))
    removed = sorted(set(left_files) - set(right_files))
    changed: list[dict[str, Any]] = []
    remaining = max_diff_lines
    for relative in sorted(set(left_files) & set(right_files)):
        before = left_files[relative].read_bytes()
        after = right_files[relative].read_bytes()
        if before == after:
            continue
        record: dict[str, Any] = {"path": relative, "before_size": len(before), "after_size": len(after), "diff": ""}
        if remaining > 0:
            try:
                before_text = before.decode("utf-8-sig").splitlines()
                after_text = after.decode("utf-8-sig").splitlines()
                lines = list(difflib.unified_diff(before_text, after_text, fromfile=f"before/{relative}", tofile=f"after/{relative}", lineterm=""))
                record["diff"] = "\n".join(lines[:remaining])
                remaining -= min(remaining, len(lines))
            except UnicodeDecodeError:
                record["binary"] = True
        changed.append(record)
    return {
        "left": str(left),
        "right": str(right),
        "added": added,
        "removed": removed,
        "changed": changed,
        "identical": not added and not removed and not changed,
        "truncated": remaining <= 0,
    }


def promotion_preview(skill_id: str) -> dict[str, Any]:
    with connect() as connection:
        row = connection.execute("SELECT * FROM skills WHERE id=? AND is_present=1", (skill_id,)).fetchone()
    if row is None:
        raise KeyError("skill not found")
    item = dict(row)
    if item["source_kind"] != "project":
        raise ValueError("只有项目级 Skill 可以生成全局快照推广计划")
    source = Path(item["path"])
    target = (CODEX_HOME / "skills" / item["name"]).resolve()
    if item["portability"] == "project-bound":
        verdict = "blocked-project-bound"
    elif target.is_dir():
        verdict = "already-identical" if _content_hash(target) == item["content_hash"] else "name-collision"
    elif item["portability"] == "portable":
        verdict = "ready"
    else:
        verdict = "review-required"
    files = [
        {"path": path.relative_to(source).as_posix(), "size": path.stat().st_size}
        for path in _iter_content_files(source)
    ]
    diff = compare_skill_folders(source, target) if target.is_dir() else None
    return {
        "skill_id": item["id"],
        "name": item["name"],
        "display_name": item["display_name"],
        "source": str(source),
        "target": str(target),
        "source_hash": item["content_hash"],
        "portability": item["portability"],
        "verdict": verdict,
        "safe_to_copy": verdict == "ready",
        "files": files,
        "diff": diff,
        "writes_performed": False,
    }


def snapshot_diff(skill_id: str) -> dict[str, Any]:
    with connect() as connection:
        row = connection.execute("SELECT * FROM skills WHERE id=? AND is_present=1", (skill_id,)).fetchone()
    if row is None:
        raise KeyError("skill not found")
    if not row["origin_path"]:
        raise ValueError("该 Skill 没有关联的项目来源")
    return compare_skill_folders(Path(row["path"]), Path(row["origin_path"]))


def register_snapshot(snapshot_path: Path, origin_path: Path, origin_hash: str) -> dict[str, Any]:
    scan_skills()
    with connect() as connection:
        row = connection.execute("SELECT * FROM skills WHERE lower(path)=lower(?)", (str(snapshot_path.resolve()),)).fetchone()
        if row is None:
            raise KeyError("snapshot not found after scan")
        connection.execute(
            "UPDATE skills SET origin_scope='project', origin_path=?, origin_hash=?, sync_status='current', updated_at=? WHERE id=?",
            (str(origin_path.resolve()), origin_hash, utc_now(), row["id"]),
        )
        _refresh_relationships(connection)
        connection.commit()
        return {"id": row["id"], "path": str(snapshot_path.resolve()), "origin_path": str(origin_path.resolve()), "origin_hash": origin_hash}


def install_dashboard_files() -> Path:
    source = SKILL_ROOT / "assets" / "dashboard"
    CENTER_HOME.mkdir(parents=True, exist_ok=True)
    (CENTER_HOME / "data").mkdir(exist_ok=True)
    (CENTER_HOME / "backups").mkdir(exist_ok=True)
    shutil.copytree(source, CENTER_HOME, dirs_exist_ok=True)
    return CENTER_HOME

"""SQLite 儲存層：文件（含版本）、官方比賽、活動、爬取紀錄。"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .auth import ROOT

DB_PATH = ROOT / "data" / "kb.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    doc_id        TEXT PRIMARY KEY,      -- 例如 hc:4902349883927、tutorial:alpha-submission
    source        TEXT NOT NULL,         -- help_center / tutorial / operator / video / forum / competition / event
    source_type   TEXT NOT NULL,         -- glossary / faq / competition_rule / doc / operator / video / forum_post / ...
    authority     INTEGER NOT NULL,      -- 1 官方文件 / 2 官方公告或置頂 / 3 社群
    audience      TEXT NOT NULL DEFAULT 'all',  -- all / tw_consultant
    title         TEXT NOT NULL,
    url           TEXT,
    section_path  TEXT,                  -- 例如 "Research FAQs > Submission"
    body_md       TEXT NOT NULL,
    lang          TEXT,
    published_at  TEXT,
    updated_at    TEXT,                  -- 原文更新時間
    fetched_at    TEXT NOT NULL,
    content_hash  TEXT NOT NULL,
    version       INTEGER NOT NULL DEFAULT 1,
    meta          TEXT                   -- JSON：其他欄位（pinned、comment_count、category_id…）
);
CREATE TABLE IF NOT EXISTS document_versions (
    doc_id TEXT, version INTEGER, content_hash TEXT, title TEXT, body_md TEXT,
    updated_at TEXT, fetched_at TEXT, PRIMARY KEY (doc_id, version)
);
CREATE TABLE IF NOT EXISTS competitions_official (
    id TEXT PRIMARY KEY, name TEXT, description TEXT, status TEXT, scoring TEXT,
    start_date TEXT, end_date TEXT, signup_start TEXT, signup_end TEXT,
    team_based INTEGER, faq_url TEXT, hc_category_id INTEGER, raw TEXT, fetched_at TEXT
);
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY, title TEXT, type TEXT, start TEXT, end TEXT, timezone TEXT,
    language TEXT, description_md TEXT, register_url TEXT, raw TEXT, fetched_at TEXT
);
CREATE TABLE IF NOT EXISTS datasets (           -- 每個 (資料集, region, delay, universe) 一列
    dataset_id TEXT, region TEXT, delay INTEGER, universe TEXT, name TEXT,
    category_id TEXT, category TEXT, subcategory TEXT, coverage REAL, date_coverage REAL,
    value_score REAL, field_count INTEGER, alpha_count INTEGER, user_count INTEGER,
    pyramid_multiplier REAL, themes TEXT, date_updated TEXT, fetched_at TEXT,
    PRIMARY KEY (dataset_id, region, delay, universe)
);
CREATE TABLE IF NOT EXISTS data_categories (
    id TEXT PRIMARY KEY, name TEXT, parent_id TEXT, dataset_count INTEGER, field_count INTEGER,
    regions TEXT, fetched_at TEXT
);
CREATE TABLE IF NOT EXISTS crawl_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT, started_at TEXT, finished_at TEXT,
    status TEXT, n_seen INTEGER, n_new INTEGER, n_changed INTEGER, error TEXT
);
CREATE INDEX IF NOT EXISTS idx_docs_source ON documents(source, source_type);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def upsert_document(con: sqlite3.Connection, doc: dict) -> str:
    """寫入文件；內容 hash 變了就升版並保留舊版。回傳 'new' / 'changed' / 'same'。"""
    h = hashlib.sha256((doc["title"] + "\n" + doc["body_md"]).encode("utf-8")).hexdigest()
    row = con.execute("SELECT content_hash, version, title, body_md, updated_at, fetched_at "
                      "FROM documents WHERE doc_id=?", (doc["doc_id"],)).fetchone()
    fields = dict(doc, content_hash=h, fetched_at=now(),
                  meta=json.dumps(doc.get("meta") or {}, ensure_ascii=False))
    fields.setdefault("audience", "all")
    for k in ("url", "section_path", "lang", "published_at", "updated_at"):
        fields.setdefault(k, None)

    if row and row["content_hash"] == h:
        con.execute("UPDATE documents SET fetched_at=?, meta=?, updated_at=? WHERE doc_id=?",
                    (fields["fetched_at"], fields["meta"], fields["updated_at"], doc["doc_id"]))
        return "same"

    version = 1
    if row:  # 舊版存檔
        con.execute("INSERT OR IGNORE INTO document_versions VALUES (?,?,?,?,?,?,?)",
                    (doc["doc_id"], row["version"], row["content_hash"], row["title"],
                     row["body_md"], row["updated_at"], row["fetched_at"]))
        version = row["version"] + 1
    fields["version"] = version
    cols = ["doc_id", "source", "source_type", "authority", "audience", "title", "url",
            "section_path", "body_md", "lang", "published_at", "updated_at", "fetched_at",
            "content_hash", "version", "meta"]
    con.execute(f"INSERT OR REPLACE INTO documents ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                [fields[c] for c in cols])
    return "changed" if row else "new"


def get_meta(con: sqlite3.Connection, doc_id: str) -> dict | None:
    row = con.execute("SELECT meta, updated_at FROM documents WHERE doc_id=?", (doc_id,)).fetchone()
    if not row:
        return None
    return {"updated_at": row["updated_at"], **json.loads(row["meta"] or "{}")}

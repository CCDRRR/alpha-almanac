"""各知識來源的爬取 + 正規化。每個函式回傳 (seen, new, changed)。"""
from __future__ import annotations

import json
import re
import sqlite3

from ..auth import API
from ..htmlmd import html_to_md, rows_to_md
from ..store import get_meta, now, upsert_document
from .client import Client

PLATFORM = "https://platform.worldquantbrain.com"

# 論壇：要爬的主題（id → audience）
FORUM_TOPICS = {
    17340188832919: "tw_consultant",  # 台灣研究顧問論壇
    40035965643159: "tw_consultant",  # 台灣顧問討論區
    18068926798871: "all",            # BRAIN TIPS
}

COMP_RE = re.compile(r"competition|challenge|\bIQC\b|\bSPC\b|\bAQP\b|\bARC\b|\bDCC\b|\bPAC\b", re.I)


class Counter:
    def __init__(self):
        self.seen = self.new = self.changed = 0

    def add(self, status: str):
        self.seen += 1
        if status == "new":
            self.new += 1
        elif status == "changed":
            self.changed += 1

    def tuple(self):
        return self.seen, self.new, self.changed


def _maybe_html(s: str | None) -> str:
    if not s:
        return ""
    return html_to_md(s) if "<" in s else s.strip()


# ---------------------------------------------------------------- 官方比賽 / 活動
def crawl_competitions(c: Client, con: sqlite3.Connection):
    cnt = Counter()
    for comp in c.paginate_api("/competitions", "api/competitions"):
        m = re.search(r"categories/(\d+)", comp.get("faq") or "")
        con.execute(
            "INSERT OR REPLACE INTO competitions_official VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (comp["id"], comp["name"], comp.get("description"), comp.get("status"), comp.get("scoring"),
             comp.get("startDate"), comp.get("endDate"), comp.get("signUpStartDate"),
             comp.get("signUpEndDate"), int(bool(comp.get("teamBased"))), comp.get("faq"),
             int(m.group(1)) if m else None, json.dumps(comp, ensure_ascii=False), now()))
        body = "\n\n".join(filter(None, [
            _maybe_html(comp.get("description")),
            f"- 比賽代碼：{comp['id']}",
            f"- 狀態：{comp.get('status')}",
            f"- 期間：{comp.get('startDate')} ~ {comp.get('endDate')}",
            f"- 報名：{comp.get('signUpStartDate')} ~ {comp.get('signUpEndDate')}",
            f"- 評分類型：{comp.get('scoring')}",
            f"- 團隊賽：{'是' if comp.get('teamBased') else '否'}",
            f"- 規則與 FAQ：{comp.get('faq')}" if comp.get("faq") else "",
        ]))
        cnt.add(upsert_document(con, {
            "doc_id": f"competition:{comp['id']}", "source": "competition",
            "source_type": "competition", "authority": 1, "title": comp["name"],
            "url": f"{PLATFORM}/competition/{comp['id']}", "body_md": body, "lang": "en",
            "updated_at": comp.get("startDate"), "meta": {"id": comp["id"]},
        }))
    return cnt.tuple()


def crawl_events(c: Client, con: sqlite3.Connection):
    cnt = Counter()
    for ev in c.paginate_api("/events", "api/events"):
        desc = _maybe_html(ev.get("description"))
        con.execute("INSERT OR REPLACE INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (ev["id"], ev["title"], ev.get("type"), ev.get("start"), ev.get("end"),
                     ev.get("timezone"), ev.get("language"), desc, ev.get("register"),
                     json.dumps(ev, ensure_ascii=False), now()))
        body = f"{desc}\n\n- 時間：{ev.get('start')} ~ {ev.get('end')}（{ev.get('timezone')}）\n" \
               f"- 形式：{ev.get('type')}\n- 報名：{ev.get('register') or '—'}"
        cnt.add(upsert_document(con, {
            "doc_id": f"event:{ev['id']}", "source": "event", "source_type": "event",
            "authority": 1, "title": ev["title"], "url": f"{PLATFORM}/events/{ev['id']}",
            "body_md": body, "lang": ev.get("language"), "updated_at": ev.get("start"),
        }))
    return cnt.tuple()


# ---------------------------------------------------------------- 運算子
def crawl_operators(c: Client, con: sqlite3.Connection):
    cnt = Counter()
    for op in c.get_json(API + "/operators", raw_name="api/operators"):
        body = "\n".join([
            f"**定義**：`{op.get('definition')}`", "",
            op.get("description") or "", "",
            f"- 類別：{op.get('category')}",
            f"- 適用範圍：{', '.join(op.get('scope') or [])}",
            f"- 開放等級：{op.get('level')}",
        ])
        cnt.add(upsert_document(con, {
            "doc_id": f"operator:{op['name']}", "source": "operator", "source_type": "operator",
            "authority": 1, "title": f"Operator: {op['name']}",
            "url": f"{PLATFORM}/learn/operators", "section_path": f"Operators > {op.get('category')}",
            "body_md": body, "lang": "en", "meta": {"name": op["name"], "category": op.get("category")},
        }))
    return cnt.tuple()


# ---------------------------------------------------------------- 平台文件
def _tutorial_body(page: dict) -> str:
    out = []
    for b in page.get("content", []):
        t, v = b.get("type"), b.get("value")
        if t == "TEXT" and isinstance(v, str):
            out.append(html_to_md(v))
        elif t == "HEADING" and isinstance(v, dict):
            out.append("#" * int(v.get("level", 2)) + " " + str(v.get("content", "")))
        elif t == "TABLE" and isinstance(v, dict):
            out.append(rows_to_md([[str(x).replace("\n", " ") for x in r] for r in v.get("data", [])]))
        elif isinstance(v, str) and t not in ("IMAGE", "VIDEO"):
            out.append(_maybe_html(v))
    return "\n\n".join(s for s in out if s.strip())


def crawl_tutorials(c: Client, con: sqlite3.Connection):
    cnt = Counter()
    for tut in c.paginate_api("/tutorials", "api/tutorials"):
        for p in tut.get("pages", []):
            doc_id = f"tutorial:{p['id']}"
            old = get_meta(con, doc_id)
            if old and old.get("updated_at") == p.get("lastModified"):
                cnt.add("same")
                continue
            page = c.get_json(f"{API}/tutorial-pages/{p['id']}", raw_name=f"api/tutorial-pages/{p['id']}")
            cnt.add(upsert_document(con, {
                "doc_id": doc_id, "source": "tutorial", "source_type": "doc", "authority": 1,
                "title": page.get("title") or p["title"],
                "url": f"{PLATFORM}/learn/documentation/{tut['id']}/{p['id']}",
                "section_path": f"Documentation > {tut.get('title')}",
                "body_md": _tutorial_body(page), "lang": "en",
                "updated_at": p.get("lastModified"),
                "meta": {"tutorial": tut["id"], "category": tut.get("category")},
            }))
    return cnt.tuple()


# ---------------------------------------------------------------- 影片課程
def crawl_videos(c: Client, con: sqlite3.Connection):
    cnt = Counter()
    for course in c.paginate_api("/video-courses", "api/video-courses"):
        for v in course.get("videos", []):
            # 沒有逐字稿、說明又只是課程簡介的影片，沒有可檢索的內容，略過
            if not (v.get("transcript") or "").strip() and v.get("description") == course.get("description"):
                continue
            body = "\n\n".join(filter(None, [
                _maybe_html(v.get("description")),
                "## 逐字稿\n\n" + _maybe_html(v.get("transcript")) if v.get("transcript") else "",
            ]))
            if not body:
                continue
            cnt.add(upsert_document(con, {
                "doc_id": f"video:{course['id']}:{v['id']}", "source": "video", "source_type": "video",
                "authority": 1, "title": v.get("title") or v["id"],
                "url": f"{PLATFORM}/learn/courses/{course['id']}/{v['id']}",
                "section_path": f"Courses > {course.get('title')}", "body_md": body,
                "lang": v.get("language") or "en", "updated_at": v.get("lastModified"),
            }))
    return cnt.tuple()


# ---------------------------------------------------------------- Help Center
def crawl_help_center(c: Client, con: sqlite3.Connection):
    c.ensure_support_sso()
    cnt = Counter()
    base = "/api/v2/help_center/en-us"
    cats = {x["id"]: x for x in c.paginate_zendesk(f"{base}/categories.json", "categories", "hc/categories")}
    secs = {x["id"]: x for x in c.paginate_zendesk(f"{base}/sections.json", "sections", "hc/sections")}
    comp_cats = {r[0] for r in con.execute(
        "SELECT hc_category_id FROM competitions_official WHERE hc_category_id IS NOT NULL")}

    for a in c.paginate_zendesk(f"{base}/articles.json", "articles", "hc/articles"):
        if a.get("draft"):
            continue
        sec = secs.get(a.get("section_id"), {})
        cat = cats.get(sec.get("category_id"), {})
        cnt.add(upsert_document(con, article_doc(a, cat, sec, cat.get("id") in comp_cats)))
    return cnt.tuple()


def article_doc(a: dict, cat: dict, sec: dict, is_comp_cat: bool = False) -> dict:
    """Zendesk 文章 → documents 列（定期爬蟲與即時搜尋共用）。"""
    cat_name, sec_name = cat.get("name", ""), sec.get("name", "")
    if "glossary" in cat_name.lower() or a["id"] == 4902349883927:
        stype = "glossary"
    elif is_comp_cat or COMP_RE.search(cat_name):
        stype = "competition_rule"
    elif "faq" in (cat_name + " " + sec_name).lower():
        stype = "faq"
    else:
        stype = "doc"
    return {
        "doc_id": f"hc:{a['id']}", "source": "help_center", "source_type": stype, "authority": 1,
        "title": a["title"], "url": a.get("html_url"),
        "section_path": " > ".join(filter(None, [cat_name, sec_name])),
        "body_md": html_to_md(a.get("body")), "lang": a.get("source_locale") or "en-us",
        "published_at": a.get("created_at"), "updated_at": a.get("edited_at") or a.get("updated_at"),
        "meta": {"category_id": cat.get("id"), "section_id": sec.get("id"),
                 "user_segment_ids": a.get("user_segment_ids"), "label_names": a.get("label_names")},
    }


def forum_doc(c: Client, p: dict, audience: str, topic_name: str) -> dict:
    """論壇文章（含留言）→ documents 列（定期爬蟲與即時搜尋共用）。"""
    comments = []
    if p.get("comment_count"):
        comments = list(c.paginate_zendesk(f"/api/v2/community/posts/{p['id']}/comments.json",
                                           "comments", f"forum/comments/{p['id']}"))
    parts = [html_to_md(p.get("details"))]
    if comments:
        parts.append("## 留言")
        for cm in sorted(comments, key=lambda x: x["created_at"]):
            tag = "（官方回覆）" if cm.get("official") else ""
            parts.append(f"### 留言 {cm['created_at'][:10]}{tag}\n\n{html_to_md(cm.get('body'))}")
    return {
        "doc_id": f"forum:{p['id']}", "source": "forum", "source_type": "forum_post",
        "authority": 2 if (p.get("pinned") or p.get("featured")) else 3,
        "audience": audience, "title": p["title"], "url": p.get("html_url"),
        "section_path": f"Community > {topic_name}", "body_md": "\n\n".join(parts),
        "published_at": p.get("created_at"), "updated_at": p.get("updated_at"),
        "meta": {"topic_id": p.get("topic_id"), "pinned": p.get("pinned"), "featured": p.get("featured"),
                 "comment_count": p.get("comment_count"), "vote_sum": p.get("vote_sum"),
                 "official_comments": sum(1 for x in comments if x.get("official"))},
    }


# ---------------------------------------------------------------- 論壇
def crawl_forum(c: Client, con: sqlite3.Connection):
    c.ensure_support_sso()
    cnt = Counter()
    topics = {t["id"]: t for t in c.paginate_zendesk("/api/v2/community/topics.json", "topics", "forum/topics")}
    for tid, audience in FORUM_TOPICS.items():
        tname = topics.get(tid, {}).get("name", str(tid))
        for p in c.paginate_zendesk(f"/api/v2/community/topics/{tid}/posts.json", "posts",
                                    f"forum/{tid}/posts"):
            doc_id = f"forum:{p['id']}"
            old = get_meta(con, doc_id)
            if old and old.get("updated_at") == p.get("updated_at") \
                    and old.get("comment_count") == p.get("comment_count"):
                cnt.add("same")
                continue
            cnt.add(upsert_document(con, forum_doc(c, {**p, "topic_id": tid}, audience, tname)))
    return cnt.tuple()


# ---------------------------------------------------------------- 平台公告
def crawl_announcements(c: Client, con: sqlite3.Connection):
    """/users/self/messages?type=ANNOUNCEMENT：全站公告（只收 ANNOUNCEMENT，不收個人通知）。"""
    cnt = Counter()
    for m in c.paginate_api("/users/self/messages?type=ANNOUNCEMENT&limit=50", "api/announcements"):
        if m.get("type") != "ANNOUNCEMENT":
            continue
        cnt.add(upsert_document(con, {
            "doc_id": f"announcement:{m['id']}", "source": "announcement", "source_type": "announcement",
            "authority": 1, "title": m.get("title") or m["id"],
            "url": f"{PLATFORM}/messages/announcements",
            "section_path": "Platform > Announcements", "body_md": _maybe_html(m.get("description")),
            "lang": "en", "published_at": m.get("dateCreated"), "updated_at": m.get("dateCreated"),
            "meta": {"id": m["id"], "tags": m.get("tags")},
        }))
    return cnt.tuple()


# ---------------------------------------------------------------- 資料集 / 資料類別
def crawl_data_categories(c: Client, con: sqlite3.Connection):
    cnt = Counter()
    cats = c.get_json(API + "/data-categories", raw_name="api/data-categories")

    def walk(nodes, parent):
        for n in nodes:
            con.execute("INSERT OR REPLACE INTO data_categories VALUES (?,?,?,?,?,?,?)",
                        (n["id"], n["name"], parent, n.get("datasetCount"), n.get("fieldCount"),
                         json.dumps(n.get("region")), now()))
            cnt.add("same")
            walk(n.get("children") or [], n["id"])

    walk(cats, None)
    return cnt.tuple()


def crawl_datasets(c: Client, con: sqlite3.Connection):
    """所有 (資料集 × region × delay × universe)；結構化存 datasets 表，
    另外每個資料集彙整成一篇文件（說明 + 各 region 可用性與 pyramid 乘數）給檢索用。"""
    by_id: dict[str, list[dict]] = {}
    for d in c.paginate_api("/data-sets?limit=50", "api/data-sets"):
        cat, sub = d.get("category") or {}, d.get("subcategory") or {}
        con.execute("INSERT OR REPLACE INTO datasets VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (d["id"], d.get("region"), d.get("delay"), d.get("universe"), d.get("name"),
                     cat.get("id"), cat.get("name"), sub.get("name"), d.get("coverage"),
                     d.get("dateCoverage"), d.get("valueScore"), d.get("fieldCount"),
                     d.get("alphaCount"), d.get("userCount"), d.get("pyramidMultiplier"),
                     json.dumps(d.get("themes") or [], ensure_ascii=False), d.get("dateUpdated"), now()))
        by_id.setdefault(d["id"], []).append(d)

    cnt = Counter()
    for ds_id, rows in by_id.items():
        d0 = rows[0]
        cat, sub = (d0.get("category") or {}).get("name"), (d0.get("subcategory") or {}).get("name")
        papers = [f"- [{p.get('title')}]({p.get('url')})" for p in d0.get("researchPapers") or [] if p.get("url")]
        table = rows_to_md([["Region", "Delay", "Universe", "Coverage", "Multiplier", "Themes"]] + [
            [r.get("region"), str(r.get("delay")), r.get("universe"),
             f"{(r.get('coverage') or 0):.0%}", str(r.get("pyramidMultiplier")),
             ", ".join(t.get("name", "") if isinstance(t, dict) else str(t) for t in r.get("themes") or [])]
            for r in sorted(rows, key=lambda r: (r.get("region") or "", r.get("delay") or 0, r.get("universe") or ""))
        ])
        body = "\n\n".join(filter(None, [
            _maybe_html(d0.get("description")),
            f"- 資料集代碼：`{ds_id}`\n- 類別：{cat} > {sub}\n- 欄位數：{d0.get('fieldCount')}",
            "## 參考資料\n\n" + "\n".join(papers) if papers else "",
            "## 各 Region 可用性\n\n" + table,  # 刻意不寫 pyramid：乘數問題交給 get_pyramid_multipliers
        ]))
        cnt.add(upsert_document(con, {
            "doc_id": f"dataset:{ds_id}", "source": "dataset", "source_type": "dataset", "authority": 1,
            "title": f"Dataset: {d0.get('name')} ({ds_id})", "url": f"{PLATFORM}/data/data-sets/{ds_id}",
            "section_path": f"Data > {cat} > {sub}", "body_md": body, "lang": "en",
            "updated_at": max((r.get("dateUpdated") or "") for r in rows) or None,
            "meta": {"category_id": (d0.get("category") or {}).get("id"), "n_variants": len(rows)},
        }))
    return cnt.tuple()


# 順序有意義：competitions 先跑，help_center 才知道哪些分類屬於比賽
SOURCES = {
    "competitions": crawl_competitions,
    "events": crawl_events,
    "operators": crawl_operators,
    "tutorials": crawl_tutorials,
    "videos": crawl_videos,
    "help_center": crawl_help_center,
    "forum": crawl_forum,
    "announcements": crawl_announcements,
    "data_categories": crawl_data_categories,
    "datasets": crawl_datasets,
}

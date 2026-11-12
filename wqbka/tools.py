"""Agent 工具（一般 Python 函式）。Web agent 直接呼叫；MCP server 只是包一層。

原則：先查本地（不花 token、不需登入）；本地沒有或要求即時，才用 search_live 上網，
且只有那時 session 失效才請使用者登入。抓回來的文件寫回本地並建索引，下次直接命中。
"""
from __future__ import annotations

import json
import time

from .index import Index, index_docs, lookup_term
from .store import connect, upsert_document

SNIPPET = 600          # 每段回給模型的字數上限（省 token）
LOW_CONFIDENCE = 0.80  # 最高向量相似度低於此值 → 幾乎可確定本地沒有
LOW_COVERAGE = 0.45    # 問題用詞在知識庫的覆蓋率低於此值 → 多半離題（見 Index.coverage）

_index: Index | None = None


def _idx() -> Index:
    global _index
    if _index is None:
        _index = Index()
    return _index


def _hit(r: dict) -> dict:
    return {
        "doc_id": r["doc_id"], "title": r["title"], "section": r["heading"] or r["section_path"],
        "source": r["source_type"], "authority": r["authority"], "audience": r["audience"],
        "date": (r["updated_at"] or r["published_at"] or "")[:10], "url": r["url"],
        "text": r["text"][:SNIPPET],
    }


# ---------------------------------------------------------------- 本地工具
def lookup_glossary(term: str) -> dict:
    """官方詞彙表 / 運算子的精確定義。"""
    hits = lookup_term(connect(), term)
    return {"found": bool(hits), "results": hits}


def search_docs(query: str, source_types: list[str] | None = None, k: int = 6,
                since: str | None = None) -> dict:
    """本地混合檢索。source_types 可選：glossary competition_rule faq doc operator video
    forum_post competition event announcement dataset。since=YYYY-MM-DD 只回該日之後的內容。"""
    idx = _idx()
    rows = idx.search(query, k=k, source_types=source_types, since=since)
    best = max((r["dense"] for r in rows), default=0.0)
    cov = idx.coverage(query)
    return {"low_confidence": best < LOW_CONFIDENCE or cov < LOW_COVERAGE,
            "vocab_coverage": round(cov, 2), "expanded_terms": idx.last_expansion,
            "results": [_hit(r) for r in rows]}


def get_document(doc_id: str, max_chars: int = 6000) -> dict:
    """讀整篇文件（search_docs 的片段不夠時）。"""
    r = connect().execute("select doc_id,title,url,section_path,source_type,authority,"
                          "published_at,updated_at,body_md from documents where doc_id=?",
                          (doc_id,)).fetchone()
    if not r:
        return {"error": "not_found", "doc_id": doc_id}
    d = dict(r)
    body = d.pop("body_md") or ""
    d["truncated"] = len(body) > max_chars
    d["body"] = body[:max_chars]
    return d


def get_competitions(active_on: str | None = None, query: str | None = None) -> dict:
    """官方比賽與活動（結構化）。active_on=YYYY-MM-DD 只回當天進行中的。
    TODO：台灣在地挑戰（論壇公告 → Haiku 抽取）完成後一併回傳。"""
    con = connect()
    comps = [dict(r) for r in con.execute(
        "select id,name,scoring,start_date,end_date,signup_start,signup_end,team_based,faq_url "
        "from competitions_official order by start_date desc")]
    events = [dict(r) for r in con.execute(
        "select id,title,type,start,end,timezone,register_url from events order by start desc")]
    if active_on:
        comps = [c for c in comps if (c["start_date"] or "") <= active_on + "T99"
                 and (c["end_date"] or "9999") >= active_on]
        events = [e for e in events if (e["end"] or e["start"] or "") >= active_on]
    if query:
        q = query.lower()
        comps = [c for c in comps if q in (c["name"] or "").lower() or q in (c["id"] or "").lower()]
        events = [e for e in events if q in (e["title"] or "").lower()]
    return {"timezone_note": "官方日期為美東時間（ET）", "competitions": comps, "events": events}


def open_calendar(view: str | None = None, q: str | None = None, month: str | None = None,
                  theme: str | None = None, tz: str | None = None) -> dict:
    """在使用者電腦上用瀏覽器打開「活動月曆」頁面（會先用本地資料重建）。預設顯示台灣時間。
    view：all 全部 / comp 比賽 / pp Power Pool / events 活動（非比賽）/ custom 自訂。
    q：預先填入搜尋（例 GLB、USD）；month：跳到某月（YYYY-MM）；theme：dark / light / blue / almanac（農民曆）；
    tz：tw 台灣時間 / et 美東時間（官方以美東為準）。
    使用者說「打開月曆」「給我看月曆」時用這個；只要文字答案時用 get_calendar。"""
    from .calendar import open_page
    res = open_page(view=view, q=q, date_=(month + "-01") if month and len(month) == 7 else month,
                    theme=theme, tz=tz)
    res["message"] = ("已在瀏覽器打開活動月曆" if res.get("opened")
                      else f"無法自動開啟瀏覽器，請手動打開：{res['file']}")
    return res


def get_almanac(date: str | None = None) -> dict:
    """今日宜忌（Alpha 農民曆）：依目前時間列出「宜」（進行中的 Power Pool Theme、Theme 乘數、比賽、即將開始的活動）
    與「忌」（快截止別拖延、剛截止別再交、沒有 PP Theme 時別交 pure PPA），外加一則官方規則提醒。
    date=YYYY-MM-DD 可查某天（以台灣中午計）。使用者問「今天宜忌」「今天該做什麼 / 交什麼」時用這個。"""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from .calendar import almanac
    at = datetime.fromisoformat(f"{date}T12:00:00").replace(tzinfo=ZoneInfo("Asia/Taipei")) if date else None
    return almanac(at)


def get_calendar(on: str | None = None, start: str | None = None, end: str | None = None,
                 kind: str | None = None, tw_only: bool = False, tag: str | None = None) -> dict:
    """活動月曆（官方比賽、Theme、Power Pool、台灣挑戰、活動），含目的、計分方式（Theme 含條件與推薦資料集）、獎項。
    on=YYYY-MM-DD 取當天進行中；或用 start/end 取期間重疊者。kind：官方比賽 Theme 季賽 雙週賽 週賽 Agent 活動。
    tag：例如 "Power Pool"（查進行中的 Power Pool Theme 與規則）、"GLB"、"台灣顧問"。"""
    from .calendar import tw_label
    con = connect()
    try:
        rows = [dict(r) for r in con.execute("select * from calendar_items order by start desc")]
    except Exception:
        return {"error": "calendar_not_built", "message": "請先執行 python -m wqbka.calendar"}
    if on:
        start = end = on
    if start:
        rows = [r for r in rows if r["end"] >= start]
    if end:
        rows = [r for r in rows if r["start"] <= end]
    if kind:
        rows = [r for r in rows if r["kind"] == kind]
    if tw_only:
        rows = [r for r in rows if r["audience"] == "tw_consultant"]
    for r in rows:
        r["tags"] = json.loads(r["tags"] or "[]")
        r.pop("built_at", None)
        r["start_tw"], r["end_tw"] = tw_label(r["start_at"]), tw_label(r["end_at"])
    if tag:
        rows = [r for r in rows if any(tag.lower() == t.lower() for t in r["tags"])]
    out = {"timezone_note": ("start/end 為美東（ET）日期，官方以此為準；start_tw/end_tw 為換算後的台灣時間。"
                             "回答時預設給台灣時間，並註明美東時間。time_basis=et_date 表示公告只寫日期、以美東當天整天計"),
           "count": len(rows), "items": rows[:30]}
    if tag and tag.lower() == "power pool":
        from .calendar import ppa_rules
        out["ppa_rules"] = ppa_rules(con)  # PPA 通用資格與提交額度（來自官方文件）
    return out


def get_pyramid_multipliers(region: str | None = None, delay: int | None = None,
                            category: str | None = None) -> dict:
    """官方 Pyramid 乘數（region × delay × 資料類別），由各資料集的 pyramidMultiplier 彙整。
    region 例：USA GLB EUR ASI CHN IND；delay 0 或 1；category 例：Analyst、Price Volume。"""
    sql = ("select region, delay, category, group_concat(distinct pyramid_multiplier) m, "
           "count(distinct dataset_id) n, max(fetched_at) f from datasets where pyramid_multiplier is not null")
    args: list = []
    if region:
        sql += " and upper(region)=upper(?)"
        args.append(region)
    if delay is not None:
        sql += " and delay=?"
        args.append(int(delay))
    if category:
        sql += " and lower(category) like lower(?)"
        args.append(f"%{category}%")
    rows = connect().execute(sql + " group by 1,2,3 order by 1,2,3", args).fetchall()
    out = [{"region": r["region"], "delay": r["delay"], "category": r["category"],
            "multiplier": r["m"], "datasets": r["n"]} for r in rows]
    return {"note": "由 /data-sets 彙整；multiplier 若出現多個值表示該組合內資料集不一致",
            "fetched_at": rows[0]["f"] if rows else None, "results": out,
            "url": "https://platform.worldquantbrain.com/genius"}


def kb_status() -> dict:
    """知識庫涵蓋範圍與更新時間（給 system prompt 與狀態頁）。不打網路。"""
    con = connect()
    counts = {f"{s}/{t}": n for s, t, n in con.execute(
        "select source,source_type,count(*) from documents group by 1,2")}
    last = {s: f for s, f in con.execute(
        "select source,max(finished_at) from crawl_runs where status='ok' group by 1")}
    from .auth import login_time
    lt = login_time()
    return {"documents": counts, "last_crawl": last,
            "session_age_hours": round((time.time() - lt.timestamp()) / 3600, 1) if lt else None,
            "session_note": "session 約 4 小時；只有 search_live 需要有效 session"}


# ---------------------------------------------------------------- 即時搜尋
class LoginRequired(RuntimeError):
    pass


def search_live(query: str, max_docs: int = 3) -> dict:
    """本地沒有 / 要求最新時才用：搜 Help Center + 論壇，抓前幾篇寫回本地後再檢索。"""
    from .crawl.client import SUPPORT, Client, SessionExpired
    from .crawl.sources import FORUM_TOPICS, article_doc, forum_doc

    c = Client(delay=0.5)
    try:
        c.ensure_login()
        c.ensure_support_sso()
        arts = c.get_json(SUPPORT + "/api/v2/help_center/articles/search.json",
                          {"query": query, "locale": "en-us", "per_page": max_docs}).get("results", [])
        posts = c.get_json(SUPPORT + "/api/v2/help_center/community_posts/search.json",
                           {"query": query, "per_page": max_docs}).get("results", [])
    except SessionExpired:
        return {"error": "login_required",
                "message": "需要即時查詢，但 WQB 登入已過期。請呼叫 login_start 打開掃臉頁，"
                           "使用者完成掃臉後呼叫 login_finish，再重新查詢。"}

    con = connect()
    touched, statuses = [], {}
    for a in arts[:max_docs]:
        sec = c.get_json(f"{SUPPORT}/api/v2/help_center/en-us/sections/{a['section_id']}.json") \
            .get("section", {}) if a.get("section_id") else {}
        cat = c.get_json(f"{SUPPORT}/api/v2/help_center/en-us/categories/{sec['category_id']}.json") \
            .get("category", {}) if sec.get("category_id") else {}
        doc = article_doc(a, cat, sec)
        statuses[doc["doc_id"]] = upsert_document(con, doc)
        touched.append(doc["doc_id"])
    topics: dict[int, str] = {}
    for p in posts[:max_docs]:
        tid = p.get("topic_id")
        if tid and tid not in topics:
            topics[tid] = c.get_json(f"{SUPPORT}/api/v2/community/topics/{tid}.json") \
                .get("topic", {}).get("name", str(tid))
        audience = FORUM_TOPICS.get(tid, "all")
        doc = forum_doc(c, p, audience, topics.get(tid, ""))
        statuses[doc["doc_id"]] = upsert_document(con, doc)
        touched.append(doc["doc_id"])
    con.commit()

    new_ids = [d for d in touched if statuses[d] != "same"]
    if new_ids:
        index_docs(con, new_ids)
        _idx().reload()
    res = search_docs(query, k=6)
    res["live"] = {"fetched": len(touched), "new_or_changed": len(new_ids),
                   "titles": [connect().execute("select title from documents where doc_id=?",
                                                (d,)).fetchone()[0] for d in touched]}
    return res


def login_start() -> dict:
    """登入 WQB（只有 search_live 需要；查本地資料不用登入）。
    已登入會直接回報剩餘時間；否則用本機 .env 的帳密送出，並在使用者電腦打開掃臉頁。
    回傳 face_scan_required 時，請使用者完成掃臉並告訴你，再呼叫 login_finish。
    帳密不會出現在對話或回傳值中；不要向使用者索取帳密。"""
    from .auth import start_login
    res = start_login()
    if res.get("browser_opened"):
        res.pop("persona_url", None)  # 瀏覽器已打開，就不必把一次性連結貼進對話
    return res


def login_finish() -> dict:
    """使用者說掃臉完成後呼叫，完成登入並保存 session（約 4 小時）。回傳 not_completed 代表還沒掃完。"""
    from .auth import finish_login
    return finish_login()


TOOLS = {
    "lookup_glossary": lookup_glossary,
    "search_docs": search_docs,
    "get_document": get_document,
    "get_competitions": get_competitions,
    "get_pyramid_multipliers": get_pyramid_multipliers,
    "get_calendar": get_calendar,
    "get_almanac": get_almanac,
    "open_calendar": open_calendar,
    "search_live": search_live,
    "login_start": login_start,
    "login_finish": login_finish,
    "kb_status": kb_status,
}

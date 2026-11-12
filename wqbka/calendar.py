"""活動月曆：從本地知識庫整理出「有起訖日期」的比賽 / Theme / 活動（規則解析，不用 LLM）。

    python -m wqbka.calendar          # 重建 calendar_items 表 + data/calendar.json + data/calendar.html
    python -m wqbka.calendar --open   # 建完直接用瀏覽器開

來源：官方比賽 API、官方活動 API、平台 Theme 公告、台灣論壇主辦方公告。
"""
from __future__ import annotations

import json
import re
import sys
import webbrowser
from datetime import date

from .auth import ROOT
from .store import connect, now

OUT_JSON = ROOT / "data" / "calendar.json"
OUT_HTML = ROOT / "data" / "calendar.html"
TEMPLATE = ROOT / "wqbka" / "web" / "calendar.html"

SCHEMA = """
drop table if exists calendar_items;  -- 衍生資料，每次重建；欄位有變也不用遷移
create table calendar_items(
  id text primary key, title text, kind text, tags text, start text, end text,
  start_at text, end_at text, time_basis text,
  purpose text, scoring text, prize text, url text, source text, audience text,
  published_at text, built_at text);
"""

# 時間：官方以美東時間（ET）為準。start / end 是 ET 日期；start_at / end_at 是精確時刻（含時區位移），
# 頁面與工具再換算成台灣時間顯示。只有日期的項目（Theme、論壇公告）視為 ET 當天 00:00:00 ~ 23:59:59。
ET = "America/New_York"
TW = "Asia/Taipei"


def _et_instant(d: str, end: bool) -> str:
    from zoneinfo import ZoneInfo
    from datetime import datetime
    t = "23:59:59" if end else "00:00:00"
    return datetime.fromisoformat(f"{d}T{t}").replace(tzinfo=ZoneInfo(ET)).isoformat()


def _add_instants(it: dict) -> None:
    if it.get("start_at") and it.get("end_at"):
        it["time_basis"] = "exact"
    else:
        it["start_at"], it["end_at"] = _et_instant(it["start"], False), _et_instant(it["end"], True)
        it["time_basis"] = "et_date"  # 公告只寫日期：假設美東當天整天


def tw_label(iso: str) -> str:
    """'2026-11-22T23:59:59-05:00' → '2026-11-23 12:59（台灣）'"""
    from zoneinfo import ZoneInfo
    from datetime import datetime
    return datetime.fromisoformat(iso).astimezone(ZoneInfo(TW)).strftime("%Y-%m-%d %H:%M") + "（台灣）"

REGIONS = ["USA", "GLB", "EUR", "ASI", "CHN", "IND", "JPN", "DEU", "GBR", "KOR", "HKG", "AMR", "TWN"]
MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


# ---------------------------------------------------------------- 日期解析
def _year_for(month: int, pub: str | None) -> int:
    """論壇常只寫 M/D：用發文年份推算；跨年（12 月發文寫 1 月）自動 +1。"""
    py, pm = (int(pub[:4]), int(pub[5:7])) if pub else (date.today().year, date.today().month)
    return py + 1 if month < pm - 6 else (py - 1 if month > pm + 6 else py)


def _iso(y: int, m: int, d: int) -> str | None:
    try:
        return date(y, m, d).isoformat()
    except ValueError:
        return None


def md_range(text: str, pub: str | None) -> tuple[str, str] | None:
    """10/27 - 11/9、10/13-10/26、10/27- 11/9 (日期更正)"""
    m = re.search(r"(?<![\d/])(\d{1,2})/(\d{1,2})\s*(?:\([^)]{0,10}\))?\s*[-–~～]\s*(\d{1,2})/(\d{1,2})(?![\d/])", text)
    if not m:
        return None
    m1, d1, m2, d2 = map(int, m.groups())
    s, e = _iso(_year_for(m1, pub), m1, d1), _iso(_year_for(m2, pub), m2, d2)
    return (s, e) if s and e and s <= e else None


def ymd_range(text: str) -> tuple[str, str] | None:
    """2026/10/1 ~ 2026/12/6、2026/12/1 ~ 12/13"""
    m = re.search(r"(20\d\d)[/.-](\d{1,2})[/.-](\d{1,2})\s*[~\-–～至到]\s*(?:(20\d\d)[/.-])?(\d{1,2})[/.-](\d{1,2})", text)
    if not m:
        return None
    y1, m1, d1, y2, m2, d2 = m.groups()
    s, e = _iso(int(y1), int(m1), int(d1)), _iso(int(y2 or y1), int(m2), int(d2))
    return (s, e) if s and e and s <= e else None


_EN_DATE = re.compile(r"(?:(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})|([A-Za-z]{3,9})\s+(\d{1,2})(?:st|nd|rd|th)?)")


def en_range(line: str, pub: str | None) -> tuple[str, str] | None:
    """Duration: 26th October'26 - 22nd November'26 / November 9`th - December 6`th"""
    clean = re.sub(r"[`’'´]\s*(\d{2})(?!\d)", r" '\1", line)       # October’26 → October '26
    clean = re.sub(r"[`’'´]", "", clean)                            # 9`th → 9th
    found = []
    for m in _EN_DATE.finditer(clean):
        day, mon = (m.group(1), m.group(2)) if m.group(1) else (m.group(4), m.group(3))
        mi = MONTHS.get(mon[:3].lower())
        if mi:
            yy = re.match(r"\s*'(\d{2})", clean[m.end():])
            y = 2000 + int(yy.group(1)) if yy else _year_for(mi, pub)
            iso = _iso(y, mi, int(day))
            if iso:
                found.append(iso)
    return (found[0], found[1]) if len(found) >= 2 and found[0] <= found[1] else None


# ---------------------------------------------------------------- 文字整理
def _sections(md: str) -> list[tuple[int, str, str]]:
    """[(層級, 標題, 內文)]，標題去掉 markdown 符號。"""
    out, lv, head, buf = [], 0, "", []
    for line in md.splitlines():
        m = re.match(r"^(#{1,6})\s*(.*)$", line)
        if m:
            out.append((lv, head, "\n".join(buf).strip()))
            lv, head, buf = len(m.group(1)), re.sub(r"[*_`]", "", m.group(2)).strip(), []
        else:
            buf.append(line)
    out.append((lv, head, "\n".join(buf).strip()))
    return [s for s in out if s[1] or s[2]]


def _short(text: str, n: int = 320) -> str:
    text = re.sub(r"\*\*|__|`", "", text)
    text = re.sub(r"\n{2,}", "\n", text).strip()
    return text if len(text) <= n else text[:n].rsplit("\n", 1)[0] + " …"


def _pick(sections, pattern: str) -> str:
    """找第一個標題符合的段落，連同其下層子段落（例：分數計算方式 > 基礎公式 > Genius 常數）。"""
    for i, (lv, h, t) in enumerate(sections):
        if not re.search(pattern, h, re.I):
            continue
        parts = [t] if t else []
        for lv2, h2, t2 in sections[i + 1:]:
            if lv and lv2 <= lv:
                break
            parts.append(f"【{h2}】\n{t2}" if h2 else t2)
        text = "\n".join(p for p in parts if p.strip())
        if text.strip():
            return text
    return ""


def _flow(text: str) -> str:
    """html→md 會把粗體斷成獨立行；把不是清單/表格的短碎行接回同一句。"""
    out: list[str] = []
    for ln in (x.strip() for x in text.splitlines()):
        if not ln:
            continue
        if out and not re.match(r"^([-*•|]|\d+\.|【)", ln) and not re.search(r"[。！？:：]$", out[-1]):
            sep = "" if re.search(r"[㐀-鿿，、]$", out[-1]) or re.match(r"^[㐀-鿿，。、]", ln) else " "
            out[-1] += sep + ln
        else:
            out.append(ln)
    return "\n".join(out)


def _tags(*texts: str) -> list[str]:
    blob = " ".join(texts)
    return [r for r in REGIONS if re.search(rf"(?<![A-Za-z]){r}(?![A-Za-z])", blob)]


# ---------------------------------------------------------------- 各來源
def from_official(con) -> list[dict]:
    items = []
    for r in con.execute("select c.*, d.body_md from competitions_official c "
                         "left join documents d on d.doc_id = 'competition:' || c.id"):
        if not r["start_date"]:
            continue
        desc = (r["body_md"] or "").split("\n\n- 比賽代碼")[0]
        items.append({
            "id": f"official:{r['id']}", "title": r["name"], "kind": "官方比賽",
            "tags": ["官方比賽", *_tags(r["name"], desc)],
            "start": r["start_date"][:10], "end": (r["end_date"] or r["start_date"])[:10],
            "start_at": r["start_date"], "end_at": r["end_date"] or r["start_date"],
            "purpose": _short(desc), "scoring": r["scoring"] or "",
            "prize": "見官方規則頁" + (f"：{r['faq_url']}" if r["faq_url"] else ""),
            "url": f"https://platform.worldquantbrain.com/competition/{r['id']}",
            "source": "官方比賽 API（美東時間）", "audience": "all", "published_at": None,
        })
    return items


def from_events(con) -> list[dict]:
    items = []
    for r in con.execute("select * from events"):
        if not r["start"]:
            continue
        items.append({
            "id": f"event:{r['id']}", "title": r["title"], "kind": "活動", "tags": ["活動", r["type"] or ""],
            "start": r["start"][:10], "end": (r["end"] or r["start"])[:10],
            "start_at": r["start"], "end_at": r["end"] or r["start"],
            "purpose": _short(r["description_md"] or ""), "scoring": "", "prize": "",
            "url": r["register_url"] or f"https://platform.worldquantbrain.com/events/{r['id']}",
            "source": f"官方活動 API（{r['timezone'] or '時區未標示'}）", "audience": "all", "published_at": None,
        })
    return items


def _theme_fields(body: str) -> dict:
    """Theme 公告逐行切欄位：Multiplier / Requirements / Recommended datasets / 獎金（Rank n: USD）。"""
    out = {"multiplier": "", "requirements": [], "datasets": [], "prize": []}
    cur = None
    for raw in body.splitlines():
        ln = re.sub(r"\*\*", "", raw).strip()
        if not ln or ln in {",", ":"}:
            continue
        if re.match(r"^(learn more|for more|faq\b)", ln, re.I):
            cur = None
            continue
        m = re.match(r"^(Duration|Multiplier|Requirements?|Recommended datasets?[^:]*)\s*:?\s*(.*)$", ln, re.I)
        if m:
            key = m.group(1).lower()
            cur = ("multiplier" if key.startswith("multi") else "requirements" if key.startswith("req")
                   else "datasets" if key.startswith("recom") else None)
            rest = m.group(2).strip()
            if cur == "multiplier":
                out["multiplier"] = rest
            elif cur == "requirements" and rest and not re.match(r"^an? .*following:?$", rest, re.I):
                out["requirements"].append(rest)
            continue
        if re.search(r"Rank \d|stipend|USD\s?\d|\$\d", ln, re.I) or re.match(r"^Alphas that match the theme", ln, re.I):
            out["prize"].append(ln)
            cur = "prize"
            continue
        if cur == "datasets":
            out["datasets"] += re.findall(r"\[([^\]]+)\]\(", ln) or ([ln] if re.fullmatch(r"[a-z]+\d+", ln) else [])
        elif cur == "requirements":
            out["requirements"].append(ln)
        elif cur == "multiplier":
            out["multiplier"] += " " + ln
    return {"multiplier": out["multiplier"].strip(), "requirements": "\n".join(out["requirements"]),
            "datasets": list(dict.fromkeys(out["datasets"])), "prize": "\n".join(out["prize"])}


def ppa_rules(con) -> dict | None:
    """Power Pool Alpha 通用規則：每次建置時從官方文件抽「資格條件」與「提交額度」，規則改了會自動跟上。"""
    r = con.execute("select title,url,updated_at,body_md from documents where source='tutorial' "
                    "and lower(title) like '%power pool alpha%' order by updated_at desc limit 1").fetchone()
    if not r:
        return None
    secs = _sections(r["body_md"])
    crit = _pick(secs, r"eligibility criteria")
    quota = _pick(secs, r"submission quota")
    bullets = lambda t: [re.sub(r"^[-*]\s*", "", x).strip() for x in t.splitlines() if re.match(r"^\s*[-*]\s", x)]
    table = [ln for ln in quota.splitlines() if ln.startswith("|")]
    return {"title": r["title"], "url": r["url"], "updated_at": (r["updated_at"] or "")[:10],
            "criteria": bullets(crit.split("\nNote:")[0]),
            "note": next((ln.strip() for ln in crit.splitlines() if ln.strip().startswith("Note:")), ""),
            "quota_table": table, "quota_notes": bullets(quota)[:4]}


def from_theme_announcements(con) -> list[dict]:
    """「Launching a new "X" theme」與「Update - "X" theme」；同名 Theme 以最新公告為準。"""
    latest: dict[str, dict] = {}
    for r in con.execute("select doc_id,title,body_md,published_at from documents "
                         "where source='announcement' and lower(title) like '%theme%' order by published_at"):
        m = re.search(r"[\"“](.+?)[\"”]", r["title"]) or re.search(r"new (.+?) theme", r["title"], re.I)
        lines = r["body_md"].splitlines()
        i = next((k for k, ln in enumerate(lines) if "duration" in ln.lower()), None)
        line = " ".join(lines[i:i + 3]) if i is not None else ""  # 日期可能在 Duration: 的下一行
        rng = en_range(line, r["published_at"]) if line else None
        if not (m and rng):
            continue
        name = re.sub(r"\s*theme$", "", m.group(1).strip(), flags=re.I)
        body = r["body_md"]
        f = _theme_fields(body)
        is_pp = "power pool" in name.lower()
        scoring = "\n".join(filter(None, [
            f"乘數：{f['multiplier']}" if f["multiplier"] else "",
            "條件：\n" + f["requirements"] if f["requirements"] else "",
            "推薦資料集：" + ", ".join(f["datasets"]) if f["datasets"] else "",
        ]))
        latest[name.lower()] = {
            "id": f"theme:{re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')}",
            "title": f"Theme：{name}", "kind": "Theme",
            "tags": ["Theme", *(["Power Pool"] if is_pp else []), *_tags(name, f["requirements"])],
            "start": rng[0], "end": rng[1],
            "purpose": ("Power Pool Theme：期間內提交符合條件的 Power Pool Alpha（PPA）；"
                        "pure PPA 在首次提交 6 週後必須符合進行中的 Theme 才能提交") if is_pp
                       else "平台 Theme：期間內符合條件的 Alpha 享有乘數加成",
            "scoring": _short(scoring, 900),
            "prize": _short(f["prize"], 800) or ("Power Pool Thematic Competition（見公告 / FAQ）" if is_pp
                                    else "Theme 乘數（影響顧問報酬計算）"),
            "url": "https://platform.worldquantbrain.com/messages/announcements",
            "source": "平台公告" + ("（已依更新公告修正）" if "update" in r["title"].lower() else ""),
            "audience": "consultant", "published_at": r["published_at"],
        }
    return list(latest.values())


_TW_ANNOUNCE = re.compile(r"^\W*(🎖|📅|🦸|🏆|🎯|📢)|\[公告\]|開跑")
_WINNER = re.compile(r"^-?\s*[A-Z]{2}\d{5}|恭喜|^(Dear|顧問們|大家好)")


def _headline(body: str) -> tuple[str, list[str]]:
    """挑戰主旨行（例：**🎖️ Bi-Weekly Alpha Challenge #2 - GLB High Margin Alpha**）與其後的說明句。"""
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    for i, ln in enumerate(lines):
        if re.match(r"^\*\*.*(challenge|挑戰).*\*\*$", ln, re.I):
            rest = [x for x in lines[i + 1:i + 8]
                    if not re.fullmatch(r"[*\s👉]*", x) and not x.startswith("#")]
            return re.sub(r"\*\*|^\W+", "", ln).strip(), rest[:3]
    return "", []


def _prize(body: str, section: str) -> str:
    src = section or body
    keep = [ln.strip() for ln in src.splitlines()
            if re.search(r"USD|\$\d|獎金|獎品|獎勵|優勝|名額|各可獲得", ln)
            and not re.match(r"^\d+\.\s*結算", re.sub(r"[*_]", "", ln).strip())]
    return "\n".join(dict.fromkeys(keep))


def _tw_kind(title: str) -> str:
    t = title.lower()
    if "bi-weekly" in t or "biweekly" in t or "雙週" in t:
        return "雙週賽"
    if "weekly" in t or "週賽" in t:
        return "週賽"
    if "agent" in t:
        return "Agent"
    if re.search(r"q[1-4]|季|consultant challenge|台灣挑戰賽", t):
        return "季賽"
    return "台灣活動"


def from_tw_forum(con) -> list[dict]:
    items = []
    for r in con.execute("select doc_id,title,url,body_md,published_at,authority from documents "
                         "where source='forum' and audience='tw_consultant'"):
        title = r["title"].strip()
        if not _TW_ANNOUNCE.search(title) or (title.startswith("[") and not title.startswith("[公告]")):
            continue
        if "office hour" in title.lower():
            continue
        body = r["body_md"].split("\n## 留言")[0]
        secs = _sections(body)
        rng = md_range(title, r["published_at"])
        if not rng:
            period = _pick(secs, r"提交期間|挑戰時間|比賽期間|期間")
            rng = ymd_range(period) or ymd_range(body) or md_range(period, r["published_at"])
        if not rng:  # 時程表：取表內最早與最晚的 M/D
            sched = _pick(secs, r"時程|timeline|schedule")
            mds = [(int(a), int(b)) for a, b in re.findall(r"(?<![\d/])(\d{1,2})/(\d{1,2})(?![\d/])", sched)]
            ds = sorted(filter(None, (_iso(_year_for(m, r["published_at"]), m, d) for m, d in mds)))
            rng = (ds[0], ds[-1]) if len(ds) >= 2 else None
        if not rng:
            continue
        scoring = _pick(secs, r"計分|評分|分數|參賽方式|scor")
        prize = _prize(body, _pick(secs, r"獎"))
        head, rest = _headline(body)
        purpose = _pick(secs, r"前言|目的|介紹|簡介|about")
        if not purpose and head:
            purpose = "\n".join([head, *rest])
        if not purpose:
            lines = [ln for ln in body.splitlines() if ln.strip() and not _WINNER.search(ln.strip())]
            purpose = "\n".join(lines[:3])
        kind = _tw_kind(title)
        items.append({
            "id": r["doc_id"], "title": re.sub(r"^[^\w\[【]+", "", title), "kind": kind,
            # region 只看標題與主旨行（計分段落常有「舉例：EUR/D1/PV」之類的範例，會誤標）
            "tags": ["台灣顧問", kind, *_tags(title, head)],
            "start": rng[0], "end": rng[1], "purpose": _short(_flow(purpose)),
            "scoring": _short(_flow(scoring), 600), "prize": _short(prize, 300), "url": r["url"],
            "source": "台灣顧問論壇（日期依公告，多為美東時間）", "audience": "tw_consultant",
            "published_at": r["published_at"],
        })
    return items


# ---------------------------------------------------------------- 建置
def build() -> dict:
    con = connect()
    con.executescript(SCHEMA)
    items = from_official(con) + from_events(con) + from_theme_announcements(con) + from_tw_forum(con)
    for it in items:
        it["tags"] = list(dict.fromkeys(t for t in it["tags"] if t))
        _add_instants(it)
    built = now()
    con.executemany("insert or replace into calendar_items values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", [
        (it["id"], it["title"], it["kind"], json.dumps(it["tags"], ensure_ascii=False), it["start"], it["end"],
         it["start_at"], it["end_at"], it["time_basis"],
         it["purpose"], it["scoring"], it["prize"], it["url"], it["source"], it["audience"],
         it["published_at"], built) for it in items])
    con.commit()
    payload = {"built_at": built, "items": items, "ppa_rules": ppa_rules(con), "almanac_tips": ALMANAC_TIPS}
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    if TEMPLATE.exists():
        html = TEMPLATE.read_text(encoding="utf-8")
        data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
        OUT_HTML.write_text(html.replace("/*__CALENDAR_DATA__*/null", data), encoding="utf-8")
    kinds: dict[str, int] = {}
    for it in items:
        kinds[it["kind"]] = kinds.get(it["kind"], 0) + 1
    return {"items": len(items), "by_kind": kinds, "html": str(OUT_HTML)}


# ---------------------------------------------------------------- 今日宜忌（Alpha 農民曆）
# 依「現在這一刻」從月曆資料產生；頁面上的 JS（wqbka/web/calendar.html 的 almanac()）是同一套規則。
# 每日提醒只放知識庫裡查得到的官方規則（Power Pool Alphas 文件、提交測試文件）。
ALMANAC_TIPS = [
    ("忌", "self-correlation ≥ 0.7（除非 Sharpe 比相關的 Alpha 高 10% 以上）"),
    ("宜", "提交前先看 IS Ladder、Sub-universe 測試有沒有過"),
    ("忌", "PPA 用超過 8 個運算子（ts_backfill、group_backfill 不算）"),
    ("宜", "分散 region 與資料類別，點亮更多 pyramid"),
    ("忌", "PPA 用超過 3 個資料欄位（分組欄位不算）"),
    ("宜", "提交前確認 Power Pool Correlation < 0.5"),
    ("忌", "只看 IS Sharpe，忽略 Turnover 測試"),
]


def _short_title(t: str) -> str:
    """去掉「Theme：」「[公告]」「開跑！」、標題裡重複的日期，讓宜忌一行讀得完。"""
    t = re.sub(r"^Theme：|^\[公告\]\s*|\s*開跑[！!]?$", "", t.strip())
    t = re.sub(r"\s*-\s*\d{1,2}/\d{1,2}\s*-\s*\d{1,2}/\d{1,2}.*$", "", t)  # 「- 10/27 - 11/9 (日期更正)」
    return t.strip()


def _left_text(seconds: float) -> str:
    h = seconds / 3600
    return f"剩 {int(h // 24)} 天" if h >= 48 else (f"剩 {int(h)} 小時" if h >= 1 else "即將截止")


def almanac(at=None) -> dict:
    """回傳 {'date': 'YYYY-MM-DD（台灣）', '宜': [...], '忌': [...]}；at 預設現在（UTC）。"""
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo
    now = at or datetime.now(timezone.utc)
    con = connect()
    rows = [dict(r) for r in con.execute("select * from calendar_items")]
    for r in rows:
        r["_s"], r["_e"] = datetime.fromisoformat(r["start_at"]), datetime.fromisoformat(r["end_at"])
        r["tags"] = json.loads(r["tags"] or "[]")
    yi, ji = [], []
    active = sorted((r for r in rows if r["_s"] <= now <= r["_e"]), key=lambda r: r["_e"])
    for r in active:
        left = (r["_e"] - now).total_seconds()
        lt, name = _left_text(left), _short_title(r["title"])
        first = lambda key: next((ln.strip(" -") for ln in (r["scoring"] or "").split("\n")
                                  if ln.strip(" -") and not ln.startswith(("乘數", "條件", "推薦"))), "")
        if "Power Pool" in r["tags"]:
            yi.append(f"交 PPA：{name}（{first('條件')}；{lt}）")
        elif r["kind"] == "Theme":
            xs = sorted(set(re.findall(r"\d+(?:\.\d+)?X", r["scoring"] or "")), key=lambda x: float(x[:-1]))
            mult = (xs[0] if len(xs) == 1 else f"{xs[0]}–{xs[-1]}") + " 乘數" if xs else "乘數加成"
            yi.append(f"吃 Theme：{name}（{mult}；{lt}）")
        elif r["kind"] == "活動":
            yi.append(f"參加：{name}（{tw_label(r['start_at'])}）")
        else:
            yi.append(f"衝刺：{name}（{lt}）")
        if left < 48 * 3600 and r["kind"] != "活動":
            ji.append(f"拖延：{name} 只{lt}")
    for r in sorted(rows, key=lambda r: r["_s"]):
        if r["kind"] == "活動" and 0 < (r["_s"] - now).total_seconds() <= 3 * 86400:
            yi.append(f"報名：{r['title']}（{tw_label(r['start_at'])}）")
        if 0 < (now - r["_e"]).total_seconds() <= 3 * 86400 and r["kind"] != "活動":
            ji.append(f"再交：{_short_title(r['title'])}（已於 {tw_label(r['end_at'])} 截止）")
    if not any("Power Pool" in r["tags"] for r in active):
        ji.append("交 pure PPA：目前沒有進行中的 Power Pool Theme（首次提交 6 週後必須符合 Theme）")
    tw_day = now.astimezone(ZoneInfo(TW))
    kind, tip = ALMANAC_TIPS[tw_day.toordinal() % len(ALMANAC_TIPS)]
    (yi if kind == "宜" else ji).append(tip)
    return {"date": tw_day.strftime("%Y-%m-%d") + "（台灣）", "宜": yi, "忌": ji,
            "note": "依月曆資料即時產生；日期以台灣時間計，官方截止以美東時間為準"}


VIEWS = {"all", "comp", "pp", "events", "custom"}
LAUNCHER = ROOT / "data" / "calendar_open.html"


def open_page(view: str | None = None, q: str | None = None, date_: str | None = None,
              theme: str | None = None, item: str | None = None, rebuild: bool = True,
              tz: str | None = None) -> dict:
    """重建後用預設瀏覽器開月曆，並帶入檢視 / 搜尋 / 月份。
    Windows 開本機檔案會丟掉網址 # 後的參數 → 先開一個小跳轉頁，由它帶參數跳到 calendar.html。"""
    info = build() if rebuild else {}
    from urllib.parse import urlencode
    params = {k: v for k, v in {"view": view if view in VIEWS else None, "q": q, "date": date_,
                                "theme": theme, "open": item,
                                "tz": tz if tz in ("tw", "et") else None}.items() if v}
    target = "calendar.html" + ("#" + urlencode(params) if params else "")
    LAUNCHER.write_text(
        "<!doctype html><meta charset='utf-8'><title>開啟活動月曆…</title>"
        f"<script>location.replace({json.dumps(target)});</script>"
        f"<a href={json.dumps(target)}>開啟活動月曆</a>", encoding="utf-8")
    opened = False
    if sys.platform == "win32":
        import os
        try:
            os.startfile(LAUNCHER)  # Windows 原生：用預設瀏覽器開
            opened = True
        except OSError:
            pass
    if not opened:
        opened = webbrowser.open(LAUNCHER.as_uri())
    return {"opened": bool(opened), "file": str(OUT_HTML), "params": params, **info}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="重建活動月曆；--open 直接用瀏覽器開")
    ap.add_argument("--open", action="store_true")
    ap.add_argument("--view", choices=sorted(VIEWS))
    ap.add_argument("--q", help="預先填入搜尋，例如 GLB、Power Pool")
    ap.add_argument("--date", help="跳到某月，例如 2026-12")
    ap.add_argument("--tz", choices=["tw", "et"], help="tw 台灣時間（預設）/ et 美東時間")
    a = ap.parse_args()
    if a.open or a.view or a.q or a.date or a.tz:
        print(open_page(a.view, a.q, a.date, tz=a.tz))
    else:
        print(build())

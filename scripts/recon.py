"""偵察：找出知識來源有哪些可用的 JSON 端點。

只記錄「端點 / 狀態碼 / 欄位結構」，以及白名單欄位（名稱、標題、數量、ID、日期）的值；
不記錄 cookie、內文。結果寫到 data/recon/report.json 並印出摘要。

用法（需先 `python -m wqbka.auth login`）：
    python scripts/recon.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import requests  # noqa: E402

from wqbka.auth import API, ROOT, check_session, load_session, login_time  # noqa: E402
from wqbka.auth import _save as save_cookies  # noqa: E402

SUPPORT = "https://support.worldquantbrain.com"
OUT = ROOT / "data" / "recon"
DELAY = 1.0  # 每次請求間隔秒數，對伺服器客氣一點

# 值可以印出來的欄位（其餘只記型別）
SHOW = {"name", "title", "post_count", "follower_count", "count", "expiry", "id",
        "category", "type", "status", "created_at", "updated_at", "start", "end",
        "startDate", "endDate", "page_count", "next_page", "locale", "featured", "pinned"}

# 來自平台前端 JS 的端點設定（只挑知識/比賽相關、唯讀的；不含 simulations）
API_CANDIDATES = [
    "/tutorials", "/tutorial-pages", "/operators", "/video-courses",
    "/competitions", "/competition-levels", "/events", "/configuration",
    "/search?query=pyramid",
]
SUPPORT_CANDIDATES = [
    "/api/v2/community/topics.json",
    "/api/v2/help_center/categories.json",
    "/api/v2/help_center/sections.json",
    "/api/v2/help_center/articles.json?per_page=5",
    "/api/v2/help_center/en-us/articles/4902349883927.json",  # 詞彙表文章
]


def schema(v, key=None, depth=0):
    """把 JSON 縮成結構描述；白名單欄位保留值（字串截斷 80 字）。"""
    if depth > 4:
        return "…"
    if isinstance(v, dict):
        return {k: schema(x, k, depth + 1) for k, x in list(v.items())[:40]}
    if isinstance(v, list):
        if not v:
            return []
        first = schema(v[0], key, depth + 1)
        if key in SHOW or all(not isinstance(x, (dict, list)) for x in v[:1]):
            return {"len": len(v), "item": first}
        # 物件陣列：額外列出前 30 筆的白名單值（例如論壇主題名稱）
        names = [{k: x.get(k) for k in ("id", "name", "title", "post_count") if k in x}
                 for x in v[:30] if isinstance(x, dict)]
        return {"len": len(v), "item": first, "preview": [n for n in names if n]}
    if key in SHOW:
        return v[:80] if isinstance(v, str) else v
    return type(v).__name__


def probe(sess: requests.Session, url: str) -> dict:
    time.sleep(DELAY)
    try:
        r = sess.get(url, timeout=30, allow_redirects=False)
    except requests.RequestException as e:
        return {"url": url, "error": type(e).__name__}
    res = {"url": url, "status": r.status_code, "content_type": r.headers.get("Content-Type", "")}
    if r.is_redirect:
        res["redirect_host"] = urlparse(urljoin(url, r.headers.get("Location", ""))).netloc
    if "json" in res["content_type"]:
        try:
            res["schema"] = schema(r.json())
        except ValueError:
            pass
    return res


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    sess = load_session()
    report: dict = {"login_time": str(login_time()), "session": check_session(sess)}
    if not report["session"]["valid"]:
        sys.exit(f"session 無效（{report['session']}），請先執行：python -m wqbka.auth login")

    print("[1/3] 探測平台 API 端點 …")
    report["api"] = [probe(sess, API + p) for p in API_CANDIDATES]

    print("[2/3] 用平台 session 換論壇（Zendesk）登入 …")
    time.sleep(DELAY)
    r = sess.get(f"{API}/authentication/support",
                 params={"return_to": SUPPORT + "/hc/en-us"}, timeout=30)
    report["support_sso"] = {
        "final_status": r.status_code,
        "final_host": urlparse(r.url).netloc,
        "hops": [urlparse(h.url).netloc + urlparse(h.url).path for h in r.history],
        "support_cookie_names": sorted({c.name for c in sess.cookies if "support" in c.domain}),
    }
    save_cookies(sess)  # 論壇 cookie 一併存起來

    print("[3/3] 探測論壇 API（帶 SSO 後的 session）…")
    report["support"] = [probe(sess, SUPPORT + p) for p in SUPPORT_CANDIDATES]

    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== 摘要 ===")
    print("session:", report["session"])
    print("support SSO:", report["support_sso"])
    for sec in ("api", "support"):
        for x in report[sec]:
            print(f"{sec:8} {x.get('status', x.get('error')):>5}  {x['url']}")
    print(f"\n完整結果：{(OUT / 'report.json').relative_to(ROOT)}")


if __name__ == "__main__":
    main()

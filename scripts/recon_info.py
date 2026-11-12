"""偵察第二輪：平台前端設定表裡的「資訊類」端點 + Zendesk 搜尋 API（即時搜尋用）。

只記錄狀態碼與欄位結構（沿用 recon.py 的白名單），不記錄 cookie、內文。
刻意排除：/simulations*、/suggest/*、/alphas、/user/*（不碰模擬與個人 alpha）。

    .venv\\Scripts\\python scripts/recon_info.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from recon import OUT, probe  # noqa: E402

from wqbka.auth import API, check_session  # noqa: E402
from wqbka.crawl.client import SUPPORT, Client  # noqa: E402

EQ = "instrumentType=EQUITY&region=USA&delay=1&universe=TOP3000"
API_INFO = [
    "/data-categories",
    f"/data-sets?{EQ}&limit=3",
    f"/data-sets/search?{EQ}&search=analyst&limit=3",
    f"/data-fields?{EQ}&limit=3",
    f"/data-fields/summary?{EQ}",
    "/configuration",
    "/competition-levels",
    "/achievements",
    "/consultant",
    "/users/self/messages?type=ANNOUNCEMENT&limit=3",
    "/users/self/messages?limit=3",
    "/messages?limit=3",
]
ZENDESK_SEARCH = [
    "/api/v2/help_center/articles/search.json?query=pyramid&locale=en-us&per_page=3",
    "/api/v2/help_center/community_posts/search.json?query=pyramid&per_page=3",
]


def main() -> None:
    c = Client()
    info = check_session(c.sess)
    if not info["valid"]:
        sys.exit("session 已過期，請先執行 python -m wqbka.auth login")
    print(f"session 有效，剩 {info.get('expiry_seconds')} 秒\n")
    out = []
    for p in API_INFO:
        r = probe(c.sess, API + p)
        out.append(r)
        print(f"[{r.get('status')}] {p}")
    c.ensure_support_sso()
    for p in ZENDESK_SEARCH:
        r = probe(c.sess, SUPPORT + p)
        out.append(r)
        print(f"[{r.get('status')}] support{p}")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "report_info.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n結構已寫入 {OUT / 'report_info.json'}")


if __name__ == "__main__":
    main()

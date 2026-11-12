"""有禮貌的 HTTP 客戶端：限速、重試、401 時明確報錯，原始回應存到 data/raw/。"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests

from ..auth import API, ROOT, check_session, load_session, _save

SUPPORT = "https://support.worldquantbrain.com"
RAW_DIR = ROOT / "data" / "raw"


class SessionExpired(RuntimeError):
    pass


class Client:
    def __init__(self, delay: float = 1.0):
        self.sess: requests.Session = load_session()
        self.delay = delay
        self._last = 0.0

    def ensure_login(self) -> dict:
        info = check_session(self.sess)
        if not info["valid"]:
            raise SessionExpired("WQB session 已過期，請執行：python -m wqbka.auth login")
        return info

    def ensure_support_sso(self) -> None:
        """用平台 session 換論壇（Zendesk）cookie。"""
        if any(c.name == "_zendesk_session" for c in self.sess.cookies):
            r = self._get(SUPPORT + "/api/v2/community/topics.json")
            if r.status_code == 200:
                return
        r = self._get(f"{API}/authentication/support", params={"return_to": SUPPORT + "/hc/en-us"})
        if "support.worldquantbrain.com" not in r.url:
            raise SessionExpired("論壇 SSO 失敗，請重新登入")
        _save(self.sess)

    def _get(self, url: str, params: dict | None = None) -> requests.Response:
        for attempt in range(4):
            wait = self.delay - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            try:
                r = self.sess.get(url, params=params, timeout=60)
            except requests.RequestException:
                time.sleep(5 * (attempt + 1))
                continue
            if r.status_code == 429:
                time.sleep(int(r.headers.get("Retry-After", 30)))
                continue
            if r.status_code in (502, 503, 504):
                time.sleep(10)
                continue
            return r
        raise RuntimeError(f"多次重試失敗：{url}")

    def get_json(self, url: str, params: dict | None = None, raw_name: str | None = None):
        r = self._get(url, params)
        if r.status_code == 401:
            raise SessionExpired(f"401：{url}")
        r.raise_for_status()
        data = r.json()
        if raw_name:
            save_raw(raw_name, data)
        return data

    def paginate_api(self, path: str, raw_prefix: str):
        """平台 API 分頁（count/next/results）。
        next 連結會指向內部路徑（/content/api/...），所以只取它的 query 參數，套回公開路徑。"""
        bare = path.split("?")[0]
        params = {k: v[0] for k, v in parse_qs(urlparse(path).query).items()}
        base = dict(params)
        i, got = 0, 0
        while True:
            data = self.get_json(API + bare, params or None, raw_name=f"{raw_prefix}/page_{i}")
            results = data.get("results", [])
            yield from results
            got += len(results)
            nxt = data.get("next")
            if nxt:
                params = {k: v[0] for k, v in parse_qs(urlparse(nxt).query).items()}
            elif results and isinstance(data.get("count"), int) and got < data["count"]:
                # 有些端點（如 /data-sets）沒有 next、只給 count → 自己用 offset 翻頁
                params = {**base, "offset": got}
            else:
                return
            i += 1

    def paginate_zendesk(self, path: str, key: str, raw_prefix: str, per_page: int = 100):
        url, params, i = SUPPORT + path, {"per_page": per_page}, 0
        while url:
            data = self.get_json(url, params, raw_name=f"{raw_prefix}/page_{i}")
            yield from data.get(key, [])
            url, params, i = data.get("next_page"), None, i + 1


def save_raw(name: str, data) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_\-/.]", "_", name)
    p = RAW_DIR / f"{safe}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p

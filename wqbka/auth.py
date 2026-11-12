"""WQB 登入：帳密 + 生物辨識（persona），cookie 存在 data/auth/。

流程（WQB 帳密 + 生物辨識）：
POST /authentication（Basic auth）→ 401 + WWW-Authenticate: persona → 使用者在瀏覽器完成掃臉
→ POST persona URL → 取得 cookie。

本模組只做「登入、存取 cookie、檢查 session」，不呼叫任何 simulation API。
"""
from __future__ import annotations

import json
import os
import sys
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
AUTH_DIR = ROOT / "data" / "auth"
COOKIE_FILE = AUTH_DIR / "cookies.json"
API = "https://api.worldquantbrain.com"
UA = "wqb-knowledge-agent/0.1"


def _save(sess: requests.Session) -> None:
    AUTH_DIR.mkdir(parents=True, exist_ok=True)
    cookies = [
        {"name": c.name, "value": c.value, "domain": c.domain, "path": c.path}
        for c in sess.cookies
    ]
    COOKIE_FILE.write_text(
        json.dumps({"login_time": datetime.now(timezone.utc).isoformat(), "cookies": cookies}),
        encoding="utf-8",
    )


def load_session() -> requests.Session:
    """回傳帶有已存 cookie 的 session（不保證仍有效，請用 check_session）。"""
    sess = requests.Session()
    sess.headers["User-Agent"] = UA
    if COOKIE_FILE.exists():
        data = json.loads(COOKIE_FILE.read_text(encoding="utf-8"))
        for c in data.get("cookies", []):
            sess.cookies.set(c["name"], c["value"], domain=c["domain"], path=c["path"])
    return sess


def login_time() -> datetime | None:
    if not COOKIE_FILE.exists():
        return None
    return datetime.fromisoformat(json.loads(COOKIE_FILE.read_text(encoding="utf-8"))["login_time"])


def check_session(sess: requests.Session) -> dict:
    """GET /authentication：有效時回傳剩餘秒數（只取 token.expiry，不回傳個資）。"""
    r = sess.get(f"{API}/authentication", timeout=30)
    if r.status_code != 200:
        return {"valid": False, "status": r.status_code}
    expiry = None
    try:
        expiry = r.json().get("token", {}).get("expiry")
    except ValueError:
        pass
    return {"valid": True, "expiry_seconds": expiry}


# ---------------------------------------------------------------- 兩段式登入（給 MCP / agent 用）
# 第一段開啟掃臉頁並記住 persona URL；使用者掃完後第二段完成登入。帳密只從本機 .env 讀，不經過對話。
PENDING_FILE = AUTH_DIR / "pending.json"
_pending: dict = {}  # 同一個 server 程序內保留 session（persona 那一步要沿用同一個 session 的 cookie）


def _credentials() -> tuple[str, str] | None:
    load_dotenv(ROOT / ".env")
    user, pwd = os.getenv("WQ_ACCOUNT"), os.getenv("WQ_PASSWORD")
    return (user, pwd) if user and pwd else None


def _open_url(url: str) -> bool:
    if sys.platform == "win32":
        try:
            os.startfile(url)  # Windows 原生：用預設瀏覽器開
            return True
        except OSError:
            pass
    return webbrowser.open(url)


def start_login(open_browser: bool = True) -> dict:
    """已登入就直接回報；否則送帳密，需要掃臉時打開掃臉頁並回傳 persona URL。"""
    info = check_session(load_session())
    if info["valid"]:
        return {"status": "already_logged_in", "expiry_seconds": info.get("expiry_seconds")}
    cred = _credentials()
    if not cred:
        return {"status": "missing_credentials",
                "message": "請在專案資料夾的 .env 填入 WQ_ACCOUNT / WQ_PASSWORD（參考 .env.example）"}
    sess = requests.Session()
    sess.headers["User-Agent"] = UA
    sess.auth = cred  # persona 那一步也要帶 Basic auth，否則會 403
    r = sess.post(f"{API}/authentication", timeout=30)
    if r.ok:
        sess.auth = None
        _save(sess)
        return {"status": "logged_in", "expiry_seconds": check_session(sess).get("expiry_seconds")}
    if r.status_code == 401 and r.headers.get("WWW-Authenticate") == "persona":
        persona_url = urljoin(r.url, r.headers["Location"])
        _pending.update(sess=sess, persona_url=persona_url)
        AUTH_DIR.mkdir(parents=True, exist_ok=True)
        PENDING_FILE.write_text(json.dumps({"persona_url": persona_url,
                                            "created": datetime.now(timezone.utc).isoformat()}),
                                encoding="utf-8")
        opened = _open_url(persona_url) if open_browser else False
        return {"status": "face_scan_required", "browser_opened": opened, "persona_url": persona_url,
                "message": "請在瀏覽器完成掃臉，完成後再呼叫 login_finish（CLI 則按 Enter）"}
    return {"status": "failed", "http_status": r.status_code, "detail": r.text[:200]}


def finish_login() -> dict:
    """掃臉完成後呼叫：向 persona URL 確認，成功就存 cookie。"""
    sess, persona_url = _pending.get("sess"), _pending.get("persona_url")
    if not persona_url and PENDING_FILE.exists():  # server 重啟過：用存下的 URL 重建 session
        persona_url = json.loads(PENDING_FILE.read_text(encoding="utf-8"))["persona_url"]
    if not persona_url:
        return {"status": "no_pending_login", "message": "請先呼叫 login_start"}
    if sess is None:
        cred = _credentials()
        if not cred:
            return {"status": "missing_credentials"}
        sess = requests.Session()
        sess.headers["User-Agent"] = UA
        sess.auth = cred
    r = sess.post(persona_url, timeout=30)
    if not r.ok:
        return {"status": "not_completed", "http_status": r.status_code,
                "message": "還沒完成掃臉（或掃臉頁已過期）。完成後再試一次；若持續失敗，請重新呼叫 login_start"}
    sess.auth = None  # 之後只靠 cookie，不再每次送帳密
    _save(sess)
    _pending.clear()
    PENDING_FILE.unlink(missing_ok=True)
    return {"status": "logged_in", "expiry_seconds": check_session(sess).get("expiry_seconds")}


def login(interactive: bool = True) -> requests.Session:
    """CLI 版：python -m wqbka.auth login"""
    res = start_login()
    if res["status"] == "missing_credentials":
        sys.exit(res["message"])
    if res["status"] == "failed":
        sys.exit(f"登入失敗：HTTP {res['http_status']} {res['detail']}")
    if res["status"] == "face_scan_required":
        print("\n需要生物辨識登入，請在瀏覽器完成掃臉：")
        print(res["persona_url"])
        if interactive:
            input("\n完成掃臉後按 Enter 繼續...")
        res = finish_login()
        if res["status"] != "logged_in":
            sys.exit(f"登入失敗：{res}")
    print(f"登入成功（{res['status']}），cookie 存在 {COOKIE_FILE.relative_to(ROOT)}；"
          f"session 剩 {int(res.get('expiry_seconds') or 0) // 60} 分鐘")
    return load_session()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "login"
    if cmd == "login":
        login()
    elif cmd == "status":
        print({"login_time": str(login_time()), **check_session(load_session())})
    else:
        sys.exit("用法：python -m wqbka.auth [login|status]")

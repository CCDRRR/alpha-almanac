"""python -m wqbka.crawl [來源 ...]   不指定就全部爬（增量）。"""
from __future__ import annotations

import sys
import time
import traceback

from ..store import connect, now
from .client import Client, SessionExpired
from .sources import SOURCES


def run(names: list[str]) -> int:
    con = connect()
    c = Client()
    try:
        info = c.ensure_login()
    except SessionExpired as e:
        print(e)
        return 2
    print(f"session 有效，剩 {int(info.get('expiry_seconds') or 0) // 60} 分鐘")

    for name in names:
        t0, started = time.time(), now()
        print(f"→ {name} …", flush=True)
        try:
            seen, new, changed = SOURCES[name](c, con)
            con.execute("INSERT INTO crawl_runs (source, started_at, finished_at, status, n_seen, n_new, n_changed)"
                        " VALUES (?,?,?,?,?,?,?)", (name, started, now(), "ok", seen, new, changed))
            con.commit()
            print(f"  完成：{seen} 筆（新 {new}、變更 {changed}），{time.time() - t0:.0f}s", flush=True)
        except SessionExpired as e:
            con.commit()
            print(f"  中止：{e}")
            return 2
        except Exception as e:  # 單一來源失敗不影響其他來源
            con.rollback()
            con.execute("INSERT INTO crawl_runs (source, started_at, finished_at, status, error)"
                        " VALUES (?,?,?,?,?)", (name, started, now(), "error", repr(e)[:500]))
            con.commit()
            print(f"  失敗：{e!r}")
            traceback.print_exc()
    # 月曆只讀本地資料、幾秒就好 → 每次爬完都重建
    from ..calendar import build as build_calendar
    print("→ 月曆", build_calendar())
    return 0


if __name__ == "__main__":
    args = sys.argv[1:] or list(SOURCES)
    bad = [a for a in args if a not in SOURCES]
    if bad:
        sys.exit(f"未知來源 {bad}；可用：{list(SOURCES)}")
    sys.exit(run(args))

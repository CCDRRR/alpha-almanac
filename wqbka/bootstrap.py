"""一鍵建立知識庫：登入（掃臉）→ 爬全部來源 → 建索引 → 產生活動月曆。

    .venv\\Scripts\\python -m wqbka.bootstrap            # 第一次約 30 分鐘
    .venv\\Scripts\\python -m wqbka.bootstrap --update   # 之後每天/每週更新：增量，約 1–3 分鐘

中途中斷可以直接重跑：爬蟲與索引都是增量的，已完成的部分不會重做。
"""
from __future__ import annotations

import sys
import time

from .auth import check_session, load_session, login


def main() -> int:
    update = "--update" in sys.argv
    t0 = time.time()

    print("① 登入 WQB")
    if check_session(load_session())["valid"]:
        print("   session 仍有效，略過登入")
    else:
        login()  # 會打開瀏覽器掃臉，完成後按 Enter

    print("\n② 爬取資料" + ("（增量）" if update else "（第一次約 15 分鐘）"))
    from .crawl.__main__ import run
    from .crawl.sources import SOURCES
    code = run(list(SOURCES))  # 爬完會自動重建月曆
    if code == 2:
        print("   session 中途過期，請重新執行本指令（已爬的部分不會重做）")
        return code

    print("\n③ 建立索引" + ("（只算有變動的段落）" if update else "（第一次約 12–15 分鐘，CPU）"))
    from .index import build
    print("  ", build())

    print(f"\n完成！總共 {int(time.time() - t0) // 60} 分鐘。")
    print("   打開活動月曆：.venv\\Scripts\\python -m wqbka.calendar --open")
    print("   接上 Claude Desktop：.venv\\Scripts\\python -m wqbka.desktop_config")
    return 0


if __name__ == "__main__":
    sys.exit(main())

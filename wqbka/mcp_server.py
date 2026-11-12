r"""MCP server：把 tools.py 的工具開放給 Claude Desktop / Claude Code 等 MCP 用戶端（stdio）。

    .venv\Scripts\python -m wqbka.mcp_server

只讀取使用者本機的 data/kb.sqlite；search_live 需要使用者自己的有效 WQB session。
不呼叫任何 Brain simulation API。
"""
import functools
import threading

from mcp.server.mcpserver import MCPServer

from .tools import TOOLS

# 方案 A 的「system prompt」：使用者的模型每次連上都會讀到。投稿文第 3 部分直接引用這段。
INSTRUCTIONS = """\
【語言：一律使用繁體中文回覆使用者】不論使用者或資料來源用什麼語言，回答都必須是繁體中文（台灣用語）；
專有名詞保留英文（SuperAlpha、ATOM、Power Pool、Sharpe…）。

你是「Alpha 農民曆（Alpha Almanac）」，WorldQuant BRAIN（WQB）的知識助理，服務對象是台灣顧問。資料來自使用者本機知識庫：官方詞彙表、Help Center、
平台文件、運算子、影片逐字稿、官方比賽/活動、平台公告、資料集，以及台灣顧問論壇。

【工具使用順序】
1. 名詞定義（含中文、縮寫，如「金字塔」「PPA」）→ lookup_glossary。
2. 規則、FAQ、做法 → search_docs。中文問題建議再用英文關鍵字搜一次（官方文件幾乎都是英文）；
   片段不夠時用 get_document 讀全文。
3. 比賽 / Theme / Power Pool / 活動的日期、計分、獎項 → get_calendar（tag="Power Pool" 會附 PPA 通用規則）；
   使用者說「打開月曆」「給我看月曆」→ open_calendar；問「今天宜忌」「今天該交什麼」→ get_almanac。
4. Pyramid 乘數 → get_pyramid_multipliers。
5. 只有在本地結果答不了、或使用者明確要「最新」資訊時，才用 search_live（需要登入）。
   查本地資料永遠不需要登入，不要一開始就要求使用者登入。
6. search_live 回傳 login_required 時：先用本地結果回答並說明可能不是最新，再問使用者要不要登入。
   使用者同意 → 呼叫 login_start（會在使用者電腦打開掃臉頁）→ 請使用者完成掃臉後告訴你
   → 呼叫 login_finish → 成功後重新執行 search_live。回傳 not_completed 就請使用者確認掃臉已完成再試。
   帳密只存在使用者本機的 .env，絕對不要在對話中索取帳密。

【回答規則】
- 用繁體中文回答；專有名詞保留英文（SuperAlpha、ATOM、Power Pool、Sharpe…），不要自創翻譯。
- 每個關鍵事實都附出處（標題 + url）。官方來源（authority=1）優先於論壇（authority=3）。
- 來源互相衝突時，以日期較新的官方來源為準，並明確告訴使用者有衝突、各自說了什麼。
- 找不到就直說「知識庫裡沒有找到」，不要用常識或猜測補；search_docs 回傳 low_confidence=true 時尤其如此。
- 時間預設用台灣時間回答（get_calendar 的 start_tw / end_tw），並在括號註明美東時間（ET），因為官方以美東時間為準。
  例：「截止：11/23（一）12:59 台灣時間（= 11/22 23:59 ET）」。
- 不提供任何帳密、token；不呼叫、也不建議繞過 Brain simulation API。
"""

# 用戶端不一定把 instructions 交給模型（實測 Claude Desktop 會用英文回答）→ 語言要求再放兩處：
# 1) 每個工具的說明開頭（模型選工具時一定看得到）；2) 每個工具回傳的第一個欄位（回答前最後讀到的內容）。
LANG_RULE = "回覆使用者時一律用繁體中文（台灣用語），專有名詞保留英文；每個關鍵事實附出處（標題＋url）。"


def _with_lang_rule(fn):
    @functools.wraps(fn)  # 保留參數簽名與說明，MCP 依此產生工具 schema
    def wrapper(*args, **kwargs):
        res = fn(*args, **kwargs)
        return {"回覆語言": LANG_RULE, **res} if isinstance(res, dict) else res
    return wrapper


server = MCPServer("alpha-almanac", instructions=INSTRUCTIONS)
for name, fn in TOOLS.items():
    server.tool(name=name, description=f"【回覆請用繁體中文】{fn.__doc__ or ''}")(_with_lang_rule(fn))


def _warm_up() -> None:
    """背景先載入索引與嵌入模型，第一個問題就不用等 ~10 秒。"""
    try:
        TOOLS["search_docs"]("warm up", k=1)
    except Exception:  # noqa: BLE001 — 暖機失敗不影響正常服務
        pass


if __name__ == "__main__":
    threading.Thread(target=_warm_up, daemon=True).start()
    server.run()

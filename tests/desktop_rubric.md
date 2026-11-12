# Claude Desktop 端到端測試：題目與評分標準

每題 2 分：**工具**（呼叫了對的工具）1 分 + **答案**（關鍵事實正確且附出處）1 分。
知識庫資料日期：2026-11-12。

| # | 題目 | 預期工具 | 關鍵事實（答案分） |
|---|---|---|---|
| 1 | PPA 是什麼？提交條件有哪些？ | lookup_glossary + search_docs / get_document | Power Pool Alpha；Sharpe ≥ 1.0、運算子 ≤ 8、資料欄位 ≤ 3、PP Correlation < 0.5、Turnover/Sub-universe/Robust-universe PASS；**加分：指出詞彙表「三個月」與文件「6 週」衝突、採較新的文件** |
| 2 | 金字塔乘數是什麼？USA D1 的 Analyst 類現在是多少？ | lookup_glossary / search_docs + get_pyramid_multipliers | Pyramid = region × delay × 資料類別；USA/D1/Analyst = **1.2** |
| 3 | 現在有哪些 Power Pool Theme？規則是什麼？ | get_calendar(tag="Power Pool") | **GLB/D1 Power Pool Nov\`26**，10/26–11/22；GLB、Delay 1、AMER Sharpe > 1；附 PPA 通用規則或獎金表 |
| 4 | Bi-Weekly #2 怎麼計分？獎金多少？ | search_docs 或 get_calendar | GLB；Turnover < 11% / Return > 6.5% / Margin > 12bps 任一得 1 分；30 USD；需 10 支；10/27–11/9（ET） |
| 5 | 2026 Q4 台灣挑戰賽的分數怎麼算？ | search_docs / get_calendar | (ARC child×3 + high quality×2 + normal) × Genius 常數（Gold 1.6 / Expert 1.4 / Master 1.2 / Grandmaster 1.0）；USA/GLB；10/1–12/6 |
| 6 | self-correlation 的門檻是多少？ | search_docs | PnL 相關 < **0.7**，或 Sharpe 比相關的 Alpha 高至少 10%；prod-correlation 同標準但對全平台 |
| 7 | SuperAlpha 跟一般 Alpha 差在哪？ | lookup_glossary + search_docs | SuperAlpha = 組合多支已提交的 Alpha（selection + combo expression）；一般 Alpha 是單一訊號 |
| 8 | ts_rank 和 rank 差在哪？ | lookup_glossary / search_docs | rank：橫截面（同一天跨股票）排名 0~1；ts_rank：時間序列（單一股票過去 d 天）排名 |
| 9 | 打開月曆，只看 Power Pool | open_calendar(view="pp") | 瀏覽器開出月曆且停在 Power Pool 檢視 |
| 10 | 2027 Q1 的 Agent 比賽獎金是多少？ | search_docs →（可選）search_live | **應回答找不到 / 尚未公布**，不可編造金額 |
| 11 | 最近一週有什麼平台公告？ | search_docs(source_types=["announcement"], since=…) 或 get_calendar | USA/D1 TOP1000 Theme（11/6）、ARC 2026 final leaderboard（11/10）、D1 Power Pool Oct\`26 2 leaderboard（11/5） |
| 12 | 如何烤戚風蛋糕？ | search_docs（low_confidence）或不呼叫 | 說明超出知識庫範圍，不給食譜 |
| 13 | 幫我查最新的 Agent 比賽公告（session 過期時測） | search_live → login_required → 問使用者 → login_start → login_finish → search_live | 先給本地答案並徵求同意才登入；打開掃臉頁；不索取帳密；登入後重新查詢成功 |

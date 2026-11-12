# [2026 Q4 Local Agent Challenge][Info & Rule,Others] Alpha 農民曆：規則、名詞、比賽、Power Pool 一句話問到，今日宜忌一眼看完

> 一個跑在自己電腦上的 WQB 知識庫 + MCP agent：把散落在平台文件、Help Center、論壇、公告裡的知識和活動爬下來，
> 以後想知道什麼，直接問它；它會附上出處，找不到就老實說找不到。

---

## 💡 為什麼做這個

剛當顧問的時候，我最常卡住的不是寫 Alpha，而是**找資料**：

- **資料散在好多地方**：名詞定義在詞彙表、規則在 Help Center、做法在平台文件和影片、台灣挑戰在論壇、Theme 和 Power Pool 在平台公告。像「Pyramid 乘數怎麼算」「PPA 的提交條件」，常常要開四五個分頁才拼得出答案。
- **每次都要登入才看得到**：大部分資料都在登入後，臨時想查一個規則，得先登入、掃臉，再一頁一頁翻。
- **活動太多記不住**：雙週挑戰、季賽、Power Pool Theme、官方比賽，各有各的期間和計分方式，很容易錯過。

所以我做了一個 agent 幫我做知識管理：**登入一次，把重要的知識、活動、比賽爬回本機，整理好；之後有需要就直接問它。**

---

## 1. 名稱 / Category / 一句話介紹

| | |
|---|---|
| **名稱** | Alpha 農民曆（Alpha Almanac） |
| **Category** | Info & Rule、Others |
| **一句話** | 把 WQB 的文件、論壇、公告、比賽爬到本機建成知識庫，用任何支援 MCP 的 AI 直接問規則、名詞、比賽和 Power Pool，答案附出處。 |

---

## 2. 它能做什麼

### 🔎 問答（附出處、找不到就說）
- 名詞、規則、做法都能問，中英文皆可：「PPA 是什麼？」「self-correlation 門檻多少？」「換手率太高怎麼辦？」
- 每個關鍵事實附**標題 + 連結**；官方來源優先於論壇。
- **來源衝突會提醒你**：例如 PPA 的額度規則，詞彙表寫「三個月後」、平台文件（2026/9/22 更新）寫「6 週後」，它會採用較新的官方文件並告訴你有衝突。
- 知識庫沒有的就回答「沒有找到」，不會用常識亂補。

### 🈶 中英對照
- 內建約 150 個名詞的中英對照與縮寫表：問「金字塔乘數」會自動帶上 *Pyramid multiplier*，問「PPA」會找到 *Power Pool Alphas*。
- 平台專有名詞（SuperAlpha、ATOM、Power Pool…）依台灣論壇的實際用法保留英文，不自創翻譯。

### 📅 活動月曆
- 自動整理 **官方比賽、台灣挑戰（季賽 / 雙週賽 / 週賽）、Agent 比賽、Power Pool Theme、一般 Theme、官方活動**，共 70 多項。
- 每項都有 **名稱、期間、目的、計分方式、獎項、原文連結**。
- **預設顯示台灣時間**，右上角可切換成**美東時間**（官方以美東時間為準）；點開項目會同時列出兩種時間。
- 五種檢視：**全部 / 比賽 / Power Pool / 活動 / 自訂**；可搜尋（例如「GLB」「USD」）。
- 「**今天進行中**」清單，顯示還剩幾天。
- 「**Power Pool 現況**」：進行中的 PP Theme 條件 + PPA 通用資格與提交額度（每次更新都從官方文件重新抽取）。
- 三種主題（黑 / 白 / 藍），顏色可自訂。
- 跟 agent 說「**打開月曆，只看 Power Pool**」，它會直接在瀏覽器打開對應的檢視。

### 🧧 今日宜忌
- 打開月曆或問 agent「今天宜忌？」，就像翻農民曆：
  - **宜**：交 PPA（進行中的 Power Pool Theme 與條件）、吃 Theme 乘數、衝刺進行中的比賽、報名即將開始的活動
  - **忌**：拖延（48 小時內截止）、再交（剛截止）、交 pure PPA（目前沒有 PP Theme 時）
  - 外加一則每日官方規則提醒，例如「忌：self-correlation ≥ 0.7」「忌：PPA 用超過 8 個運算子」
- 依「現在這一刻」即時計算，資料就是活動月曆本身，不會亂編。

### 🔺 Pyramid 乘數查詢
- 從資料集資訊彙整出 **region × delay × 資料類別** 的乘數表：「USA D1 的 Analyst 是多少？」→ 1.2。

### 🌐 本地優先，需要時才上網
- 平常**只查本機**：不用登入、不花 token、回應約 0.05 秒。
- 本機找不到、或你要「最新」資訊時，才即時搜尋 Help Center 與論壇，**抓回來的文章會存進知識庫**，下次直接查得到。
- 只有這時 session 過期才會問你要不要登入：**在對話裡就能完成**，agent 幫你打開掃臉頁，掃完跟它說一聲就好，不用另外開終端機。帳密只從你本機的 `.env` 讀取，不會出現在對話裡。

---

## 3. 環境設定（Setup）

### 架構

```
你的 AI 用戶端（Claude Desktop / Claude Code / 其他支援 MCP 的用戶端）
        │  使用你自己的訂閱或本地模型
        ▼
MCP server（alpha-almanac，12 個工具）
        ▼
本機知識庫 data/kb.sqlite（只在你的電腦，不上傳、不分享）
        ▲ 每天增量更新
爬蟲：登入（帳密 + 掃臉）→ 平台 API / Help Center / 論壇
```

### 使用的模型與工具

| 項目 | 內容 |
|---|---|
| **回答用的模型** | 你自己的 MCP 用戶端的模型。我實測用 **Claude Desktop**；理論上任何支援 MCP 的用戶端都能接（例如接 gpt-oss 的用戶端），但我**還沒實測**其他用戶端 |
| **向量模型** | `intfloat/multilingual-e5-base`（本機 CPU 執行，免費） |
| **檢索** | 向量 + BM25 混合檢索；中文問題另以英文關鍵字檢索官方文件 |
| **MCP 工具** | `lookup_glossary`、`search_docs`、`get_document`、`get_competitions`、`get_pyramid_multipliers`、`get_calendar`、`get_almanac`、`open_calendar`、`search_live`、`login_start`、`login_finish`、`kb_status` |
| **語言 / 套件** | Python 3.11+；requests、beautifulsoup4、sentence-transformers、rank-bm25、mcp |
| **原始碼** | https://github.com/CCDRRR/alpha-almanac （只有程式碼，不含任何爬下來的資料） |

### 安裝步驟（Windows，約 40 分鐘，大多是等待）

需要：Windows 10/11、Python 3.11 以上、Claude Desktop、你自己的 WQB 帳號。

```powershell
# 1. 下載程式、一鍵安裝（建 venv、裝 CPU 版 torch 與套件，約 5–10 分鐘）
git clone https://github.com/CCDRRR/alpha-almanac.git
cd alpha-almanac
powershell -ExecutionPolicy Bypass -File setup.ps1

# 2. 填入自己的 WQB 帳密（只存在本機 .env，不會上傳）
notepad .env

# 3. 一鍵建立知識庫：打開瀏覽器掃臉 → 爬資料 → 建索引 → 產生月曆（第一次約 30 分鐘）
.venv\Scripts\python -m wqbka.bootstrap

# 4. 自動接上 Claude Desktop（自動找設定檔位置、保留原設定並先備份）
.venv\Scripts\python -m wqbka.desktop_config
```

**5.** 在系統匣的 Claude 圖示按右鍵 →「Quit」，再重新打開 Claude Desktop，就能開始問了。

<details><summary>想手動設定 Claude Desktop 的話</summary>

在設定檔的 `mcpServers` 加入下面這段（路徑換成你的資料夾；檔案裡原有的設定要保留）。
設定檔位置：新版（設定裡沒有 Developer 選單）在 `%LOCALAPPDATA%\Claude-Data\claude_*\claude_desktop_config.json`；舊版是「設定 → Developer → Edit Config」。

```json
{
  "mcpServers": {
    "alpha-almanac": {
      "command": "C:\\你的路徑\\alpha-almanac\\.venv\\Scripts\\python.exe",
      "args": ["-m", "wqbka.mcp_server"],
      "env": {
        "PYTHONPATH": "C:\\你的路徑\\alpha-almanac",
        "PYTHONIOENCODING": "utf-8",
        "HF_HUB_OFFLINE": "1"
      }
    }
  }
}
```
</details>

### 每次執行的成本

| 項目 | 成本 |
|---|---|
| 額外 API 費用 | **US$0**：不需要另外申請 API key，用你現有的 Claude 訂閱（或其他用戶端的模型） |
| 向量計算 | 本機 CPU，免費 |
| 每次問答 | 消耗你用戶端本身的額度；工具回傳的是精簡片段（每段 ≤ 600 字），不會把整篇文件塞給模型 |
| 每日更新 | 增量爬取 + 增量索引，約 1–2 分鐘 |

---

## 4. System prompt 與知識來源

### System prompt

這段寫在 MCP server 的 `instructions`，用戶端連上時會交給模型。
實測發現 Claude Desktop 不一定會把它當成最高優先（曾經用英文回答），所以語言要求另外加在**每個工具的說明**和**每次工具回傳的第一個欄位**，三層一起確保回答是繁體中文。

```text
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
```

### 知識來源（約 2,700 篇、9,100 段）

| 來源 | 內容 | 權威等級 |
|---|---|---|
| 官方詞彙表 | 112 個名詞 | 官方 |
| Help Center | 各比賽規則、FAQ、顧問文件，約 630 篇 | 官方 |
| 平台文件、運算子、影片逐字稿 | Learn 頁面、84 個運算子、50 部影片 | 官方 |
| 官方比賽、活動 | 比賽 API、活動 API | 官方 |
| 平台公告 | 約 845 則（Theme、Power Pool、排行榜…） | 官方 |
| 資料集 | 444 個資料集，含各 region 的 Pyramid 乘數 | 官方 |
| 論壇 | 台灣研究顧問論壇、台灣顧問討論區、BRAIN TIPS | 置頂 / 社群 |

⚠️ **合規說明**
- 只使用**唯讀的資訊類**端點，**不呼叫任何 Brain simulation API**，也不讀取個人 Alpha。
- 帳密只存在你本機的 `.env`，cookie 和爬下來的資料只存在本機 `data/`，兩者都不會進到 git。
- 我只分享程式碼，不分享爬下來的資料，每個人用自己的帳號建自己的知識庫。

### 檢索品質（自建題庫）

| 指標 | 結果 |
|---|---|
| 正確文件在前 3 名（52 題，含 22 組中英同義題） | 94.2%（中文 90.9%、英文 95.5%） |
| 正確文件在前 6 名 | 96.2% |
| 詞彙表（含中文 / 縮寫） | 100% |
| 比賽 / Pyramid 等結構化查詢 | 100% |
| 離題問題辨識 | 6/7，領域內誤判 0/52 |

*題庫和權重是同一份資料調的，數字偏樂觀；歡迎大家提供實際遇到的問題，我會加進驗證集。*

---

## 5. 實際執行範例

〔待補：Claude Desktop 實測紀錄，預計放「PPA 是什麼？提交條件有哪些？」與「現在有哪些 Power Pool Theme？規則是什麼？」兩題的完整輸入、工具呼叫與輸出。〕

---

## 6. 已知限制

1. **資料新鮮度取決於你多久更新一次**：預設要自己執行爬蟲（或排程）；即時搜尋可以補，但需要有效的 session。
2. **登入需要掃臉**：WQB 的 session 約 4 小時，爬蟲和即時搜尋都需要先登入（可在對話中完成）；平常查詢本機資料不需要。
3. **月曆是規則解析**：台灣挑戰公告格式改了可能抓不到；官方比賽的獎項多半在圖片裡，目前只附官方規則頁連結。
4. **圖片內容還沒解析**：部分比賽總覽圖已下架；之後會讓有看圖能力的用戶端自己讀圖並寫回知識庫。
5. **中文問題的排名仍略遜英文**：正確文件多半在前 3 名，但不一定是第 1 名。
6. **「查無資料」偵測不完美**：明顯離題的問題擋得住，但「看起來像 WQB 的問題卻其實沒有資料」時，仍要靠模型判斷。
7. **只實測 Claude Desktop（Windows）**：其他 MCP 用戶端、macOS / Linux 尚未實測。
8. **第一次安裝較久**：爬取加建索引約 30 分鐘，向量模型約 1 GB。

---

## 📖 使用說明書

### 日常使用

直接在 Claude Desktop 問就好，例如：

| 想知道 | 可以這樣問 |
|---|---|
| 名詞 | 「PPA 是什麼？」「金字塔是什麼？」「SuperAlpha 跟一般 Alpha 差在哪？」 |
| 規則 | 「self-correlation 門檻多少？」「IS ladder 沒過怎麼辦？」 |
| 比賽 | 「Bi-Weekly #2 怎麼計分？」「Q4 台灣挑戰賽分數怎麼算？」 |
| Power Pool | 「現在有哪些 Power Pool Theme？規則是什麼？」 |
| Pyramid | 「USA D1 的 Analyst 乘數是多少？」 |
| 最新消息 | 「最近一週有什麼平台公告？」「幫我查最新的 ○○」（需要登入） |
| 今日宜忌 | 「今天宜忌？」「今天該交什麼？」 |
| 月曆 | 「打開月曆」「打開月曆，只看比賽」「給我看 12 月 GLB 相關的活動」 |
| 運算子 | 「ts_rank 和 rank 差在哪？」 |

### 更新資料（建議每天或每週一次）

```powershell
.venv\Scripts\python -m wqbka.bootstrap --update   # 掃臉（session 還有效就略過）→ 增量爬取 → 增量索引 → 重建月曆，約 1–3 分鐘
```

### 月曆操作
- **打開**：跟 agent 說「打開月曆」，或直接雙擊 `data\calendar.html`。
- **檢視**：上方「全部 / 比賽 / Power Pool / 活動 / 自訂」；「自訂」可勾選類別。
- **搜尋**：輸入 GLB、USD、Power Pool 等關鍵字。
- **今日宜忌**：右側最上方的卡片，點「宜 / 忌」項目可看詳情。
- **詳情**：點任一項目，右側顯示目的、計分方式、獎項與原文連結。
- **時區**：預設**台灣時間**，右上角「台灣時間 / 美東時間」可切換。
  - WQB 官方的比賽、Theme 截止時間都**以美東時間（ET）為準**。想對照官方公告就切到美東時間；平常直接看換算好的台灣時間即可。
  - 換算範例：美東 11/22 23:59 截止 = **台灣 11/23（一）中午 12:59**（美國冬令時間差 13 小時；夏令時間差 12 小時，程式會自動判斷）。
  - 所以在台灣時間檢視下，月曆上的結束日常會比官方公告**多一天**，這是正常的。
  - 公告只寫日期、沒寫時間的項目（大部分 Theme 與論壇公告），視為美東當天 00:00 開始、23:59 結束。
  - 問 agent 時，它也會先給台灣時間，括號附上美東時間。
- **外觀**：右上角切換黑 / 白 / 藍，齒輪可改各類別顏色；設定會記在你的瀏覽器。

### 常見問題

| 狀況 | 解法 |
|---|---|
| 回答變成英文 | 新版已在工具說明與回傳中強制繁體中文；若仍出現，可在 Claude Desktop 設定 → Your Claude（個人偏好）加一句「請一律用繁體中文回答」 |
| Claude Desktop 看不到工具 | 確認改的是正確版本的設定檔（見安裝步驟 5）；改完要從系統匣完全結束再開；記錄檔 `%LOCALAPPDATA%\Claude\logs\main.log` 若顯示 `no stdio servers connected` 代表沒讀到設定 |
| 回答說「需要登入」 | 跟 agent 說「好，登入」，它會打開掃臉頁；掃完告訴它即可（或在終端機執行 `python -m wqbka.auth login`） |
| 月曆沒有最新活動 | 重新執行爬蟲；或請 agent「查最新的…」 |
| 月曆上的截止日跟官方公告差一天 | 正常：預設顯示台灣時間，美東 23:59 截止＝台灣隔天中午；切到「美東時間」就會和官方一致 |
| 第一次問比較慢 | 模型載入約 10 秒，之後每次約 0.05 秒 |

---

歡迎大家試用、回報問題，或提供你常卡住的問題，我會持續改進 🙌

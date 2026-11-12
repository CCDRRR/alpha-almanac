# Alpha 農民曆（Alpha Almanac）

把 WorldQuant BRAIN 散落在平台文件、Help Center、論壇、公告裡的知識與活動爬到本機建成知識庫，
透過 MCP 讓 Claude Desktop（或其他 MCP 用戶端）直接問規則、名詞、比賽與 Power Pool，答案附出處；另附活動月曆（預設台灣時間）。
參加 2026 Q4 Agent Creation Mini Challenge（Info & Rule, Others）。介紹與使用說明書：[docs/forum_post.md](docs/forum_post.md)。

> 只用唯讀資訊類 API，**不呼叫 Brain simulation API**、不讀個人 Alpha。帳密與 cookie 只存在本機 `.env` 與 `data/`（皆不提交）。
> 本 repo 只有程式碼，不含任何爬下來的資料：每個人用自己的帳號建自己的知識庫。

## 快速開始（Windows）

```powershell
git clone https://github.com/CCDRRR/alpha-almanac.git
cd alpha-almanac
powershell -ExecutionPolicy Bypass -File setup.ps1   # 建 venv、裝套件（約 5–10 分鐘）
notepad .env                                          # 填入 WQ_ACCOUNT / WQ_PASSWORD
.venv\Scripts\python -m wqbka.bootstrap               # 掃臉登入 → 爬資料 → 建索引 → 產生月曆（約 30 分鐘）
.venv\Scripts\python -m wqbka.desktop_config          # 自動加入 Claude Desktop 設定（會先備份）
```

最後從系統匣「Quit」Claude Desktop 再重開，就能在對話中問「PPA 是什麼？」「打開月曆」。
之後更新資料：`.venv\Scripts\python -m wqbka.bootstrap --update`（增量，約 1–3 分鐘）。

## 個別指令

```powershell
copy .env.example .env          # 填入 WQ_ACCOUNT / WQ_PASSWORD
python -m wqbka.auth login      # 會開瀏覽器做生物辨識，完成後按 Enter（session 4 小時）
python -m wqbka.auth status     # 查看 session 剩餘時間
python -m wqbka.crawl           # 增量爬全部來源 → data/kb.sqlite（首次約 10 分鐘，之後約 30 秒）
python -m wqbka.crawl forum     # 只爬指定來源：competitions events operators tutorials videos help_center forum announcements data_categories datasets

# 索引（需專案 venv：pip install -r requirements.txt；首次約 12 分鐘 CPU，之後只算變動段落）
.venv\Scripts\python -m wqbka.index build
.venv\Scripts\python -m wqbka.index search "pyramid 是什麼"
.venv\Scripts\python -m wqbka.index term "super alpha"
.venv\Scripts\python scripts\search_smoke.py   # 10 題檢索冒煙測試
```

檢索：`intfloat/multilingual-e5-base` 向量 + BM25（中文單字/雙字）以 RRF 融合，依權威等級加權；
另開「只看官方」候選池並保留一半名額，避免中文問題只撈到論壇。詞彙表另建精確查詢表（112 詞）。

**中英對照查詢擴充**：[`wqbka/aliases.csv`](wqbka/aliases.csv)（人工整理，約 150 詞，隨 repo 提供，歡迎 PR 補充）。
查詢中出現中文說法或別名（例：金字塔乘數、自相關、換手率、雙週挑戰、ARC）時自動補上英文正式名詞；
官方候選池另以「純英文」查詢檢索。平台專有名詞（SuperAlpha、ATOM、Power Pool…）依台灣論壇實際用法保留英文、不自創翻譯。

## 工具（`wqbka/tools.py`，Web agent 與 MCP 共用）

| 工具 | 用途 | 需要登入？ |
|---|---|---|
| `lookup_glossary` | 官方詞彙表 / 運算子精確定義 | 否 |
| `search_docs` | 本地混合檢索，可篩來源類型與日期（`since`） | 否 |
| `get_document` | 讀整篇文件 | 否 |
| `get_competitions` | 官方比賽與活動（結構化，可查某天進行中） | 否 |
| `get_pyramid_multipliers` | 官方 Pyramid 乘數（region × delay × 資料類別） | 否 |
| `get_almanac` | 今日宜忌：進行中的 PP Theme / Theme / 比賽（宜）、快截止與剛截止（忌）、每日規則提醒 | 否 |
| `get_calendar` | 活動月曆（官方比賽、Theme、Power Pool、台灣挑戰、活動），含目的 / 計分 / 獎項 | 否 |
| `open_calendar` | 在使用者電腦用瀏覽器打開活動月曆，可指定檢視（全部 / 比賽 / Power Pool / 活動）、搜尋字、月份 | 否 |

## 活動月曆

```powershell
.venv\Scripts\python -m wqbka.calendar --open             # 產生 data/calendar.html（靜態頁，雙擊即可開）；爬蟲結束後也會自動重建
.venv\Scripts\python -m wqbka.calendar --view pp --q GLB  # 直接開在 Power Pool 檢視並搜尋 GLB（agent 的 open_calendar 也是這樣做）
```

規則解析（不用 LLM）：官方比賽 / 活動 API 的結構化日期；平台 Theme 公告的「Duration:」行（同名 Theme 以最新的 Update 公告為準）；
台灣顧問論壇主辦方公告（標題 🎖️📅🦸 / [公告]，日期依序取標題 M/D-M/D → 內文「提交期間」→「時程」表），
並抽出「目的 / 計分方式 / 獎項」段落。參賽者投稿（`[2026 Q3 Challenge] …`）不列入。

**時區**：頁面預設台灣時間，可切換美東時間（官方以美東為準）。官方比賽 / 活動 API 有精確時刻（含時區位移）；只有日期的項目（Theme、論壇公告）視為美東當天 00:00:00–23:59:59，再換算台灣時間（`calendar_items.time_basis`：`exact` / `et_date`）。`get_calendar` 會多回 `start_tw` / `end_tw`。
| `kb_status` | 知識庫涵蓋範圍、最後更新時間 | 否 |
| `search_live` | 本地沒有或要求最新時，即時搜 Help Center + 論壇，**寫回本地並建索引** | 是（過期才提示掃臉） |
| `login_start` / `login_finish` | 在對話中登入：開啟掃臉頁 → 使用者掃完 → 完成登入（帳密只從本機 .env 讀） | — |

## MCP（Claude Desktop / Claude Code）

Claude Desktop：在設定檔的 `mcpServers` 加入下面這段（路徑換成你的專案位置；保留檔案裡原有的其他設定）。用 `PYTHONPATH` 指定專案根目錄，不依賴 cwd。

```json
{
  "mcpServers": {
    "alpha-almanac": {
      "command": "C:\\path\\to\\alpha-almanac\\.venv\\Scripts\\python.exe",
      "args": ["-m", "wqbka.mcp_server"],
      "env": {
        "PYTHONPATH": "C:\\path\\to\\alpha-almanac",
        "PYTHONIOENCODING": "utf-8",
        "HF_HUB_OFFLINE": "1"
      }
    }
  }
}
```

設定檔位置依版本不同：
- 新版（5.x，設定裡沒有 Developer 選單）：`%LOCALAPPDATA%\Claude-Data\claude_*\claude_desktop_config.json`
- 舊版：設定 → Developer → Edit Config（`%APPDATA%\Claude\claude_desktop_config.json`）

存檔後**從系統匣完全結束** Claude Desktop 再開。確認是否連上：`%LOCALAPPDATA%\Claude\logs\main.log` 不應再出現
`no stdio servers connected`。
使用規則（等同 system prompt）寫在 `wqbka/mcp_server.py` 的 `INSTRUCTIONS`，連上時自動送給模型。

## 知識來源

| 來源 | 端點 | 權威等級 |
|---|---|---|
| Help Center（FAQ、詞彙表、各比賽規則） | support `/api/v2/help_center/en-us/articles.json` | 1 官方 |
| 平台文件 | api `/tutorials` → `/tutorial-pages/{id}` | 1 官方 |
| 運算子 | api `/operators` | 1 官方 |
| 影片逐字稿 | api `/video-courses` | 1 官方 |
| 官方比賽、活動 | api `/competitions`、`/events` | 1 官方 |
| 論壇（台灣研究顧問論壇、台灣顧問討論區、BRAIN TIPS） | support `/api/v2/community/topics/{id}/posts.json` | 2 置頂 / 3 一般 |
| 平台公告（只收 ANNOUNCEMENT） | api `/users/self/messages?type=ANNOUNCEMENT` | 1 官方 |
| 資料集（含各 region/delay 的 Pyramid 乘數）、資料類別 | api `/data-sets`、`/data-categories` | 1 官方 |

刻意不碰：`/simulations*`、`/suggest/*`、`/alphas`、`/user/*`（模擬、個人 alpha、帳號操作）。

論壇登入：用平台 session 呼叫 `api /authentication/support?return_to=…` 換取 Zendesk cookie（SSO）。

## 評測

```powershell
.venv\Scripts\python scripts\eval_kb.py      # 題庫 tests/kb_golden.json：52 題檢索（22 組中英同義）、10 個詞彙、4 個結構化工具、7 個離題問題
```

最近一次（2026-11-12）：檢索 Hit@1 75.0%、Hit@3 94.2%、Hit@6 96.2%、MRR 0.848（中文 Hit@3 90.9%、英文 95.5%）；
詞彙表 100%；結構化工具 100%；離題偵測 6/7、領域內誤判 0/52；單次檢索平均約 50 ms。
注意：權重與門檻是用同一份題庫調的，數字偏樂觀；之後會用真實使用者問題另建驗證集。

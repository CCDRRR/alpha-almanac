"""把 docs/forum_post.md 轉成可直接複製貼到 WQB 論壇（Zendesk 所見即所得編輯器）的網頁。

    .venv\\Scripts\\python scripts/render_post.py          # 產生 data/forum_post.html 並打開
需要：pip install markdown（只有發文時用，不在 requirements.txt）
"""
from __future__ import annotations

import html
import os
import re
import sys
import webbrowser
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent.parent
SRC, OUT = ROOT / "docs" / "forum_post.md", ROOT / "data" / "forum_post.html"

md = SRC.read_text(encoding="utf-8")
title = re.match(r"^# (.+)$", md, re.M).group(1).strip()
body_md = re.sub(r"^# .+\n", "", md, count=1)
body = markdown.markdown(body_md, extensions=["tables", "fenced_code", "sane_lists"])

page = f"""<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>論壇貼文預覽</title>
<style>
  body {{ margin: 0; background: #f4f5f7; color: #1d2330;
         font: 15px/1.7 system-ui, "Segoe UI", "Noto Sans TC", "Microsoft JhengHei", sans-serif; }}
  .wrap {{ max-width: 860px; margin: 0 auto; padding: 24px 16px 60px; }}
  .howto {{ background: #fff8e6; border: 1px solid #f0d58a; border-radius: 10px; padding: 14px 16px; margin-bottom: 18px; }}
  .howto ol {{ margin: 6px 0 0; padding-left: 20px; }}
  .row {{ display: flex; gap: 8px; margin: 8px 0; }}
  .row input {{ flex: 1; font: inherit; padding: 6px 8px; border: 1px solid #ccc; border-radius: 6px; }}
  button {{ font: inherit; padding: 6px 14px; border-radius: 6px; border: 1px solid #3b5bdb; background: #3b5bdb;
           color: #fff; cursor: pointer; }}
  .ok {{ color: #2f9e44; margin-left: 8px; }}
  #post {{ background: #fff; border: 2px dashed #b8c0cc; border-radius: 10px; padding: 8px 24px 24px; }}
  #post table {{ border-collapse: collapse; margin: 10px 0; }}
  #post th, #post td {{ border: 1px solid #d0d5dd; padding: 6px 10px; vertical-align: top; }}
  #post th {{ background: #f0f2f5; }}
  #post pre {{ background: #f6f8fa; border: 1px solid #e3e6ea; border-radius: 6px; padding: 10px 12px;
              overflow-x: auto; font-size: 13px; line-height: 1.5; }}
  #post code {{ font-family: Consolas, "Courier New", monospace; }}
  #post blockquote {{ border-left: 4px solid #d0d5dd; margin: 10px 0; padding: 2px 14px; color: #555; }}
</style></head>
<body><div class="wrap">
  <div class="howto">
    <b>發文步驟</b>（WQB 論壇 → 台灣顧問討論區 → 新增文章）
    <ol>
      <li>標題：按「複製標題」，貼到論壇的標題欄。</li>
      <li>內文：按「複製內文」，到論壇內文編輯區按 Ctrl+V（表格、粗體、標題都會保留）。</li>
      <li>貼上後捲動檢查一次，特別是表格與程式碼區塊，再按發佈。</li>
    </ol>
    <div class="row"><input id="title" readonly value="{html.escape(title)}"><button onclick="copyTitle()">複製標題</button></div>
    <button onclick="copyBody()">複製內文</button><span class="ok" id="msg"></span>
  </div>
  <div id="post">{body}</div>
</div>
<script>
  const msg = t => {{ const m = document.getElementById("msg"); m.textContent = t; setTimeout(() => m.textContent = "", 2500); }};
  function copyTitle() {{ const i = document.getElementById("title"); i.select(); document.execCommand("copy"); msg("標題已複製"); }}
  async function copyBody() {{
    const el = document.getElementById("post");
    try {{
      await navigator.clipboard.write([new ClipboardItem({{
        "text/html": new Blob([el.innerHTML], {{ type: "text/html" }}),
        "text/plain": new Blob([el.innerText], {{ type: "text/plain" }}) }})]);
    }} catch (e) {{   // 舊瀏覽器：選取後複製
      const r = document.createRange(); r.selectNodeContents(el);
      const s = getSelection(); s.removeAllRanges(); s.addRange(r); document.execCommand("copy"); s.removeAllRanges();
    }}
    msg("內文已複製，到論壇按 Ctrl+V");
  }}
</script></body></html>"""

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(page, encoding="utf-8")
print(f"已產生 {OUT}（標題 {len(title)} 字、內文約 {len(re.sub(r'<[^>]+>', '', body))} 字）")
if "--no-open" not in sys.argv:
    if sys.platform == "win32":
        os.startfile(OUT)
    else:
        webbrowser.open(OUT.as_uri())

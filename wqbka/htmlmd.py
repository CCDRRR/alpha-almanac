"""輕量 HTML → Markdown（只用 bs4），保留標題、清單、表格、連結，丟掉 style/script/圖片。"""
from __future__ import annotations

import re
import warnings

from bs4 import BeautifulSoup, MarkupResemblesLocatorWarning, NavigableString, Tag

warnings.filterwarnings("ignore", category=MarkupResemblesLocatorWarning)

_BLOCK = {"p", "div", "section", "article", "blockquote", "br"}


def _inline(node) -> str:
    if isinstance(node, NavigableString):
        return str(node)
    if not isinstance(node, Tag):
        return ""
    name = node.name
    if name in ("style", "script", "img", "svg", "iframe"):
        return ""
    inner = "".join(_inline(c) for c in node.children)
    if name == "a" and node.get("href") and inner.strip():
        return f"[{inner.strip()}]({node['href']})"
    if name in ("strong", "b") and inner.strip():
        return f"**{inner.strip()}**"
    if name == "code":
        return f"`{inner}`"
    if name == "br":
        return "\n"
    return inner


def _table(t: Tag) -> str:
    rows = []
    for tr in t.find_all("tr"):
        cells = [re.sub(r"\s+", " ", _inline(c)).strip().replace("|", "\\|")
                 for c in tr.find_all(["th", "td"])]
        if cells:
            rows.append(cells)
    return rows_to_md(rows)


def rows_to_md(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    out = ["| " + " | ".join(rows[0]) + " |", "|" + " --- |" * width]
    out += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join(out)


def _block(node, out: list[str], depth: int = 0) -> None:
    for c in node.children:
        if isinstance(c, NavigableString):
            if c.strip():
                out.append(c.strip())
            continue
        if not isinstance(c, Tag) or c.name in ("style", "script", "img", "svg", "iframe"):
            continue
        name = c.name
        if re.fullmatch(r"h[1-6]", name):
            out.append("#" * int(name[1]) + " " + _inline(c).strip())
        elif name in ("ul", "ol"):
            for i, li in enumerate(c.find_all("li", recursive=False), 1):
                bullet = f"{i}." if name == "ol" else "-"
                out.append("  " * depth + f"{bullet} " + _inline(li).strip())
        elif name == "table":
            out.append(_table(c))
        elif name == "pre":
            out.append("```\n" + c.get_text() + "\n```")
        elif name in _BLOCK or c.find(["p", "ul", "ol", "table", "h1", "h2", "h3", "div"]):
            _block(c, out, depth)
        else:
            t = _inline(c).strip()
            if t:
                out.append(t)


def html_to_md(html: str | None) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    out: list[str] = []
    _block(soup.body or soup, out)
    text = "\n\n".join(s for s in out if s.strip())
    return re.sub(r"\n{3,}", "\n\n", text).strip()

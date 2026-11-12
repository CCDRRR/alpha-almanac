"""切段 + 混合檢索（multilingual-e5 向量 + BM25），以及詞彙表精確查詢。

    python -m wqbka.index build              # 重建 chunks，只對新/改過的段落算向量
    python -m wqbka.index search "pyramid 是什麼"
    python -m wqbka.index term "super alpha"
"""
from __future__ import annotations

import hashlib
import re
import sys
import time

import numpy as np

from .store import connect

MODEL_NAME = "intfloat/multilingual-e5-base"
TARGET, MAX_CHARS, MAX_CHUNKS_PER_DOC = 800, 1200, 80
AUTHORITY_WEIGHT = {1: 1.0, 2: 0.95, 3: 0.85}
OFFICIAL_POOL_WEIGHT = 0.5      # 英文問題：官方池的 RRF 加權
OFFICIAL_POOL_WEIGHT_CJK = 1.0  # 中文問題：官方池（純英文查詢）的 RRF 加權，見 scripts/eval_kb.py
_STOP = set("什麼 怎麼 如何 可以 the and are what how does with for".split())
_DATASET_INTENT = re.compile(r"dataset|data set|資料集|數據集|datafield|data field|資料欄位|欄位", re.I)

SCHEMA = """
create table if not exists chunks(
  chunk_id text primary key, doc_id text, ord int, heading text, text text, hash text);
create index if not exists chunks_doc on chunks(doc_id);
create table if not exists emb_cache(hash text primary key, vec blob);
create table if not exists glossary(
  norm text primary key, term text, note text, definition text, doc_id text, url text);
"""


# ---------- 切段 ----------
def _units(md: str):
    """(heading_path, paragraph)；heading_path 依 markdown 標題層級組成。"""
    stack: dict[int, str] = {}
    for block in re.split(r"\n\s*\n", md):
        block = block.strip()
        if not block:
            continue
        m = re.match(r"^(#{1,6}) (.+)$", block)
        if m and "\n" not in block:
            lv = len(m.group(1))
            stack = {k: v for k, v in stack.items() if k < lv}
            stack[lv] = m.group(2).strip()
            continue
        path = " > ".join(stack[k] for k in sorted(stack))
        # 過長段落硬切（表格、程式碼常見）
        while len(block) > MAX_CHARS:
            cut = block.rfind("\n", 0, MAX_CHARS)
            cut = cut if cut > MAX_CHARS // 2 else MAX_CHARS
            yield path, block[:cut]
            block = block[cut:].lstrip()
        yield path, block


def chunk_doc(doc: dict) -> list[tuple[str, str]]:
    """回傳 [(heading, text)]。標題換了且累積夠長就切；詞彙表每個名詞一段。"""
    per_heading = doc["source_type"] == "glossary"
    out, buf, head = [], [], None
    size = 0
    for path, para in _units(doc["body_md"] or ""):
        changed = head is not None and path != head
        if buf and ((changed and (per_heading or size >= 300)) or size + len(para) > TARGET):
            out.append((head, "\n\n".join(buf)))
            # 少量重疊：帶上一段的最後一個短段落
            buf = [buf[-1]] if (not changed and len(buf[-1]) < 250) else []
            size = sum(len(b) for b in buf)
        if not buf:
            head = path
        buf.append(para)
        size += len(para)
    if buf:
        out.append((head, "\n\n".join(buf)))
    out = [(h, t) for h, t in out if t.count("](#") < 5]  # 去掉頁內錨點導覽列
    if not out:  # 只有標題的短文件（例如 FAQ 只有 "Yes"）
        out = [("", doc["body_md"] or "")]
    return out[:MAX_CHUNKS_PER_DOC]


def embed_text(doc: dict, heading: str, text: str) -> str:
    ctx = " | ".join(x for x in (doc["title"], doc["section_path"], heading) if x)
    return f"passage: {ctx}\n{text}"


# ---------- 詞彙表 ----------
def norm_term(s: str) -> str:
    s = re.sub(r"\(.*?\)", "", s.lower())
    return re.sub(r"[\s\-_]+", "", s).strip()


def build_glossary(con) -> int:
    con.execute("delete from glossary")
    n = 0
    for doc_id, url, body in con.execute(
            "select doc_id,url,body_md from documents where source_type='glossary'").fetchall():
        for m in re.finditer(r"^### (.+?)\n(.*?)(?=^#{1,3} |\Z)", body, re.M | re.S):
            raw, definition = m.group(1).strip(), m.group(2).strip()
            note = "; ".join(re.findall(r"\((.*?)\)", raw))
            term = re.sub(r"\s*\(.*?\)", "", raw).strip()
            con.execute("insert or replace into glossary values (?,?,?,?,?,?)",
                        (norm_term(term), term, note, definition, doc_id, url))
            n += 1
    con.commit()
    return n


def lookup_term(con, term: str) -> list[dict]:
    """詞彙表精確 → 中英對照 / 縮寫（aliases.csv）→ 包含比對；再查運算子名稱。"""
    q = norm_term(term)
    rows = con.execute("select term,note,definition,url from glossary where norm=?", (q,)).fetchall()
    if not rows:  # 「金字塔」「換手率」「PPA」→ 先換成英文正式名詞再查
        for en in expand_query(term)[1]:
            rows += con.execute("select term,note,definition,url from glossary where norm=?",
                                (norm_term(en),)).fetchall()
    if not rows and len(q) >= 3:
        rows = con.execute("select term,note,definition,url from glossary where norm like ? limit 5",
                           (f"%{q}%",)).fetchall()
    out = [{"term": t, "note": nt, "definition": d, "url": u, "source": "Glossary"}
           for t, nt, d, u in rows]
    op = con.execute("select title,body_md,url from documents where source_type='operator' "
                     "and lower(title)=?", (f"operator: {term.strip().lower()}",)).fetchone()
    if op:
        out.append({"term": op[0], "note": "", "definition": op[1], "url": op[2], "source": "Operators"})
    return out


# ---------- 中英對照查詢擴充（wqbka/aliases.csv，人工整理、隨 repo 提供） ----------
_ALIASES: list[tuple[str, re.Pattern]] | None = None
_CJK = re.compile(r"[㐀-鿿]")


def _alias_patterns() -> list[tuple[str, re.Pattern]]:
    global _ALIASES
    if _ALIASES is None:
        import csv
        from pathlib import Path
        _ALIASES = []
        with open(Path(__file__).with_name("aliases.csv"), encoding="utf-8") as f:
            for r in csv.DictReader(f):
                keys = [k.strip() for k in [r["zh"], *r["aliases"].split(";")] if k.strip()]
                for k in keys:
                    if _CJK.search(k):          # 中文：子字串比對
                        pat = re.compile(re.escape(k))
                    elif len(k) <= 3:          # 短英文縮寫（SA、IS、IQC）：大小寫完全相同且整字
                        pat = re.compile(rf"(?<![A-Za-z]){re.escape(k)}(?![A-Za-z])")
                    else:                      # 一般英文別名：整字、不分大小寫
                        pat = re.compile(rf"(?<![a-z]){re.escape(k.lower())}(?![a-z])", re.I)
                    _ALIASES.append((r["en"], pat))
    return _ALIASES


def expand_query(q: str) -> tuple[str, list[str]]:
    """查詢裡出現中文說法 / 別名時，補上英文正式名詞（官方文件多為英文）。"""
    added: list[str] = []
    for en, pat in _alias_patterns():
        if en not in added and en.lower() not in q.lower() and pat.search(q):
            added.append(en)
    return (f"{q} {' '.join(added)}" if added else q), added


# ---------- BM25 斷詞（英文單字 + 中文單字/雙字） ----------
_TOK = re.compile(r"[a-z0-9_]+|[㐀-鿿]+")


def tokenize(text: str) -> list[str]:
    toks: list[str] = []
    for m in _TOK.finditer(text.lower()):
        s = m.group()
        if s[0] < "㐀":
            toks.append(s)
        else:
            toks.extend(s)
            toks.extend(s[i:i + 2] for i in range(len(s) - 1))
    return toks


# ---------- 建索引 ----------
_model = None


def model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(MODEL_NAME, device="cpu")
        _model.max_seq_length = 512
    return _model


def build(batch: int = 32) -> dict:
    con = connect()
    con.executescript(SCHEMA)
    docs = [dict(zip(("doc_id", "source_type", "title", "section_path", "body_md"), r))
            for r in con.execute("select doc_id,source_type,title,section_path,body_md from documents")]
    rows = []
    for d in docs:
        for i, (h, t) in enumerate(chunk_doc(d)):
            et = embed_text(d, h, t)
            hsh = hashlib.sha256((MODEL_NAME + et).encode()).hexdigest()[:24]
            rows.append((f"{d['doc_id']}#{i}", d["doc_id"], i, h, t, hsh, et))
    con.execute("delete from chunks")
    con.executemany("insert into chunks values (?,?,?,?,?,?)", [r[:6] for r in rows])
    con.commit()

    have = {h for (h,) in con.execute("select hash from emb_cache")}
    todo = list({r[5]: r[6] for r in rows if r[5] not in have}.items())
    t0 = time.time()
    if todo:
        m = model()
        for s in range(0, len(todo), batch):
            part = todo[s:s + batch]
            vecs = m.encode([t for _, t in part], normalize_embeddings=True, batch_size=batch)
            con.executemany("insert or replace into emb_cache values (?,?)",
                            [(h, v.astype(np.float16).tobytes()) for (h, _), v in zip(part, vecs)])
            con.commit()
            done = s + len(part)
            el = time.time() - t0
            print(f"\r  向量 {done}/{len(todo)}  {el:.0f}s，預估剩 {el / done * (len(todo) - done):.0f}s",
                  end="", flush=True)
        print()
    # 清掉沒用到的快取
    con.execute("delete from emb_cache where hash not in (select hash from chunks)")
    con.commit()
    g = build_glossary(con)
    return {"docs": len(docs), "chunks": len(rows), "embedded": len(todo), "glossary_terms": g,
            "seconds": round(time.time() - t0)}


def index_docs(con, doc_ids: list[str]) -> int:
    """只重切、重算指定文件（即時搜尋寫回用）。回傳新算的向量數。"""
    con.executescript(SCHEMA)
    n = 0
    for doc_id in doc_ids:
        r = con.execute("select doc_id,source_type,title,section_path,body_md from documents "
                        "where doc_id=?", (doc_id,)).fetchone()
        if not r:
            continue
        d = dict(zip(("doc_id", "source_type", "title", "section_path", "body_md"), tuple(r)))
        con.execute("delete from chunks where doc_id=?", (doc_id,))
        for i, (h, t) in enumerate(chunk_doc(d)):
            et = embed_text(d, h, t)
            hsh = hashlib.sha256((MODEL_NAME + et).encode()).hexdigest()[:24]
            con.execute("insert into chunks values (?,?,?,?,?,?)", (f"{doc_id}#{i}", doc_id, i, h, t, hsh))
            if not con.execute("select 1 from emb_cache where hash=?", (hsh,)).fetchone():
                v = model().encode(et, normalize_embeddings=True, show_progress_bar=False)
                con.execute("insert into emb_cache values (?,?)", (hsh, v.astype(np.float16).tobytes()))
                n += 1
    con.commit()
    return n


# ---------- 檢索 ----------
class Index:
    def __init__(self):
        self.con = connect()
        self.reload()

    def reload(self) -> None:
        from rank_bm25 import BM25Okapi
        rows = self.con.execute(
            """select c.chunk_id,c.doc_id,c.heading,c.text,d.title,d.section_path,d.url,
                      d.source,d.source_type,d.authority,d.audience,d.published_at,d.updated_at,e.vec
               from chunks c join documents d using(doc_id) join emb_cache e on e.hash=c.hash
               order by c.chunk_id""").fetchall()
        keys = ("chunk_id", "doc_id", "heading", "text", "title", "section_path", "url", "source",
                "source_type", "authority", "audience", "published_at", "updated_at")
        self.meta = [dict(zip(keys, r[:-1])) for r in rows]
        self.M = np.vstack([np.frombuffer(r[-1], dtype=np.float16) for r in rows]).astype(np.float32)
        self.not_dataset = np.array([m["source_type"] != "dataset" for m in self.meta])
        self.bm25 = BM25Okapi([tokenize(f"{m['title']} {m['heading'] or ''} {m['text']}")
                               for m in self.meta])
        self.df: dict[str, int] = {}
        for doc in self.bm25.doc_freqs:
            for t in doc:
                self.df[t] = self.df.get(t, 0) + 1

    def coverage(self, query: str) -> float:
        """問題裡的實詞（英文字、中文雙字）有多少比例在知識庫出現 ≥3 次。
        「烤戚風蛋糕」「台北下雨」這類離題問題通常 < 0.45；題庫 52 題最低 0.5（scripts/eval_kb.py 校準）。"""
        toks = []
        for m in re.finditer(r"[a-z0-9_]+|[㐀-鿿]+", query.lower()):
            s = m.group()
            if s[0] < "㐀":
                if len(s) > 2 and s not in _STOP:
                    toks.append(s)
            else:
                toks += [s[i:i + 2] for i in range(len(s) - 1) if s[i:i + 2] not in _STOP]
        if not toks:
            return 1.0
        return sum(1 for t in toks if self.df.get(t, 0) >= 3) / len(toks)

    def search(self, query: str, k: int = 8, source_types: list[str] | None = None,
               per_doc: int = 2, pool: int = 50, official_quota: bool = True, since: str | None = None,
               expand: bool = True) -> list[dict]:
        self.last_expansion: list[str] = []
        original = query
        if expand:
            query, self.last_expansion = expand_query(query)
        qv = model().encode(f"query: {query}", normalize_embeddings=True, show_progress_bar=False)
        dense = self.M @ qv
        sparse = self.bm25.get_scores(tokenize(query))
        # 中文問題：官方池另用「純英文」查詢（原句裡的英文字 + 擴充名詞）。官方文件幾乎都是英文，
        # 就算原句已含英文名詞（「SuperAlpha 是什麼」）也要做，否則中文虛詞會拉偏向量。
        dense_off, sparse_off = dense, sparse
        is_cjk = bool(_CJK.search(original))
        if is_cjk:
            q_en = " ".join(dict.fromkeys(re.findall(r"[A-Za-z0-9_\-]+", original) + self.last_expansion))
            if q_en.strip():
                dense_off = self.M @ model().encode(f"query: {q_en}", normalize_embeddings=True, show_progress_bar=False)
                sparse_off = self.bm25.get_scores(tokenize(q_en))
        mask = np.ones(len(self.meta), bool)
        if source_types:
            mask &= np.array([m["source_type"] in source_types for m in self.meta])
        elif not _DATASET_INTENT.search(original):
            # 資料集文件的可用性表格滿是 TOP3000 / USA / D1 等字，會洗掉一般問題 → 沒問資料集就不納入
            mask &= self.not_dataset
        if since:
            mask &= np.array([(m["updated_at"] or m["published_at"] or "") >= since for m in self.meta])
        official = np.array([m["authority"] == 1 for m in self.meta])
        def rrf(pmask, arrays) -> dict[int, float]:
            s: dict[int, float] = {}
            for arr in arrays:
                masked = np.where(pmask, arr, -np.inf)
                for rank, i in enumerate(np.argsort(-masked)[:pool]):
                    if np.isfinite(masked[i]):
                        s[i] = s.get(i, 0.0) + 1.0 / (60 + rank)
            return s

        # 兩個候選池：全部來源 + 只看官方（中文問題時官方英文文件常擠不進全體前 50）
        s_all, s_off = rrf(mask, (dense, sparse)), rrf(mask & official, (dense_off, sparse_off))
        w_off = OFFICIAL_POOL_WEIGHT_CJK if is_cjk else OFFICIAL_POOL_WEIGHT
        score = {i: s_all.get(i, 0.0) + w_off * s_off.get(i, 0.0) for i in set(s_all) | set(s_off)}
        final = {i: s * AUTHORITY_WEIGHT.get(self.meta[i]["authority"], .8) for i, s in score.items()}
        ranked = sorted(final, key=lambda i: -final[i])
        # 官方文件多為英文、論壇多為中文且量大 → 保留一半名額給官方來源
        n_official = (k + 1) // 2 if official_quota else 0
        picked, seen = [], {}

        def take(cands, limit):
            for i in cands:
                if len(picked) >= limit:
                    return
                m = self.meta[i]
                if i in picked or seen.get(m["doc_id"], 0) >= per_doc:
                    continue
                seen[m["doc_id"]] = seen.get(m["doc_id"], 0) + 1
                picked.append(i)

        take([i for i in ranked if self.meta[i]["authority"] == 1], n_official)
        take(ranked, k)
        picked.sort(key=lambda i: -final[i])
        return [{**self.meta[i], "score": round(final[i], 4), "dense": round(float(dense[i]), 3)}
                for i in picked]


def _cli() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"
    if cmd == "build":
        print(build())
    elif cmd == "search":
        q = " ".join(sys.argv[2:])
        for r in Index().search(q):
            print(f"[{r['score']:.4f} d={r['dense']}] ({r['source_type']}/A{r['authority']}) "
                  f"{r['title']}  ›  {r['heading'] or ''}\n    {r['text'][:160].replace(chr(10), ' ')}")
    elif cmd == "term":
        con = connect()
        for r in lookup_term(con, " ".join(sys.argv[2:])):
            print(f"[{r['source']}] {r['term']} {r['note']}\n{r['definition'][:500]}\n")


if __name__ == "__main__":
    _cli()

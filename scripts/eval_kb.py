"""知識庫檢索評測：直接呼叫 agent 用的工具函式（search_docs / lookup_glossary / 結構化工具）。

    .venv\\Scripts\\python scripts/eval_kb.py            # 跑全部，結果存 data/eval/
    .venv\\Scripts\\python scripts/eval_kb.py --k 6      # Hit@k 的 k（預設 6，與 search_docs 預設相同）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from wqbka import tools as T  # noqa: E402


def rank_of(results: list[dict], expect: dict) -> int | None:
    """回傳第一個命中的名次（1 起算），沒命中回 None。"""
    t_re = re.compile(expect["title"], re.I) if expect.get("title") else None
    h_re = re.compile(expect["heading"], re.I) if expect.get("heading") else None
    for n, r in enumerate(results, 1):
        if (t_re and t_re.search(r["title"])) or (h_re and h_re.search(r.get("section") or "")):
            return n
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=6)
    ap.add_argument("--w-cjk", type=float, help="覆寫中文問題的官方池權重（調參用）")
    args = ap.parse_args()
    k = args.k
    if args.w_cjk is not None:
        import wqbka.index as I
        I.OFFICIAL_POOL_WEIGHT_CJK = args.w_cjk
    gold = json.loads((ROOT / "tests" / "kb_golden.json").read_text(encoding="utf-8"))
    T._idx(); T.search_docs("warm up")  # 先載入索引與模型，避免第一題計時失真

    # ---------- 檢索 ----------
    rows, lat = [], []
    for case in gold["search"]:
        t0 = time.perf_counter()
        res = T.search_docs(case["q"], k=k)
        lat.append(time.perf_counter() - t0)
        r = rank_of(res["results"], case["expect"])
        rows.append({**case, "rank": r, "expanded": res["expanded_terms"], "low": res["low_confidence"],
                     "top3": [f"{x['source']}:{x['title'][:60]}" for x in res["results"][:3]]})

    def summarize(rs):
        n = len(rs)
        return {"n": n,
                "hit@1": sum(1 for r in rs if r["rank"] == 1) / n,
                "hit@3": sum(1 for r in rs if r["rank"] and r["rank"] <= 3) / n,
                f"hit@{k}": sum(1 for r in rs if r["rank"]) / n,
                "mrr": sum(1 / r["rank"] for r in rs if r["rank"]) / n}

    overall = summarize(rows)
    by_cat = defaultdict(list)
    for r in rows:
        by_cat[r["cat"]].append(r)
    zh = [r for r in rows if r.get("pair") and r["id"].endswith("-zh")]
    en = [r for r in rows if r.get("pair") and r["id"].endswith("-en")]

    # ---------- 詞彙表 ----------
    gl = []
    for g in gold["glossary"]:
        terms = [x["term"] for x in T.lookup_glossary(g["q"])["results"]]
        gl.append({**g, "got": terms, "ok": g["expect"] in terms})

    # ---------- 結構化工具 ----------
    st = []
    for s in gold["structured"]:
        out = getattr(T, s["tool"])(**s["args"])
        env = {"items": out.get("items") or out.get("results") or [], "ppa_rules": out.get("ppa_rules"),
               "multiplier": (out.get("results") or [{}])[0].get("multiplier") if out.get("results") else None}
        try:
            ok = bool(eval(s["check"], {"any": any}, env))
        except Exception as e:  # noqa: BLE001
            ok = False
            env["error"] = repr(e)
        st.append({"id": s["id"], "ok": ok})

    # ---------- 離題問題（只記錄，目前沒有可靠的「查無資料」門檻） ----------
    off = []
    for q in gold["off_topic"]:
        res = T.search_docs(q, k=3)
        off.append({"q": q, "low_confidence": res["low_confidence"],
                    "top": res["results"][0]["title"][:50] if res["results"] else ""})

    report = {"run_at": datetime.now().isoformat(timespec="seconds"), "k": k,
              "search": {"overall": overall, "by_category": {c: summarize(v) for c, v in by_cat.items()},
                         "zh": summarize(zh), "en": summarize(en),
                         "latency_ms": {"avg": round(1000 * sum(lat) / len(lat)), "max": round(1000 * max(lat))},
                         "cases": rows},
              "glossary": {"acc": sum(g["ok"] for g in gl) / len(gl), "cases": gl},
              "structured": {"acc": sum(s["ok"] for s in st) / len(st), "cases": st},
              "off_topic": off}
    out_dir = ROOT / "data" / "eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"kb_eval_{datetime.now():%Y%m%d_%H%M}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---------- 印摘要 ----------
    pct = lambda x: f"{100 * x:5.1f}%"
    s = report["search"]
    print(f"\n=== 檢索（{overall['n']} 題，k={k}）===")
    print(f"整體   Hit@1 {pct(overall['hit@1'])}  Hit@3 {pct(overall['hit@3'])}  Hit@{k} {pct(overall[f'hit@{k}'])}  MRR {overall['mrr']:.3f}")
    print(f"中文   Hit@1 {pct(s['zh']['hit@1'])}  Hit@3 {pct(s['zh']['hit@3'])}  Hit@{k} {pct(s['zh'][f'hit@{k}'])}  ({s['zh']['n']} 題)")
    print(f"英文   Hit@1 {pct(s['en']['hit@1'])}  Hit@3 {pct(s['en']['hit@3'])}  Hit@{k} {pct(s['en'][f'hit@{k}'])}  ({s['en']['n']} 題)")
    print(f"延遲   平均 {s['latency_ms']['avg']} ms，最慢 {s['latency_ms']['max']} ms")
    print("\n分類：")
    for c, v in s["by_category"].items():
        print(f"  {c:6s} n={v['n']:2d}  Hit@1 {pct(v['hit@1'])}  Hit@{k} {pct(v[f'hit@{k}'])}")
    print("\n沒有進前 3 名的題目：")
    for r in rows:
        if not r["rank"] or r["rank"] > 3:
            print(f"  [{r['rank'] or '✗'}] {r['id']:14s} {r['q']}  擴充={r['expanded']}")
            for t in r["top3"]:
                print(f"         · {t}")
    print(f"\n=== 詞彙表 {pct(report['glossary']['acc'])} ===")
    for g in gl:
        if not g["ok"]:
            print(f"  ✗ {g['q']!r} → 期望 {g['expect']}，得到 {g['got']}")
    print(f"\n=== 結構化工具 {pct(report['structured']['acc'])} ===")
    for x in st:
        print(f"  {'✓' if x['ok'] else '✗'} {x['id']}")
    fp = [r["q"] for r in rows if r["low"]]
    print(f"\n=== 誤判離題（領域內題目被標 low_confidence）：{len(fp)} / {len(rows)} === {fp}")
    print("\n=== 離題問題（low_confidence 應為 True）===")
    for o in off:
        print(f"  {'✓' if o['low_confidence'] else '✗'} {o['q']}  → 第一名：{o['top']}")
    print(f"\n完整結果：{out}")


if __name__ == "__main__":
    main()

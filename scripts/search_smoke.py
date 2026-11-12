"""檢索冒煙測試：python scripts/search_smoke.py"""
import sys
sys.path.insert(0, ".")
from wqbka.index import Index

QUERIES = [
    "pyramid 是什麼",
    "super alpha 跟 alpha 差在哪",
    "Bi-Weekly 挑戰怎麼計分",
    "ATOM alpha 的提交條件",
    "什麼是 self-correlation，門檻多少",
    "how is the IQC scored",
    "台灣顧問 11月 AQP 競賽規則",
    "ts_rank 怎麼用",
    "顧問的 base payment 怎麼算",
    "如何申請成為 consultant",
]
idx = Index()
for q in QUERIES:
    print(f"\n### {q}")
    for r in idx.search(q, k=5):
        print(f"  [{r['score']:.4f} d={r['dense']}] {r['source_type']}/A{r['authority']}  {r['title'][:70]}  › {(r['heading'] or '')[:40]}")

"""Retrieval-based parts-estimate draft agent (fictional data, stdlib only).

Given a free-text part name / spec, retrieve the most similar parts from
data/parts_master.csv with TF-IDF cosine similarity over word tokens and
character n-grams, collect their past estimates from data/past_estimates.csv,
and draft an estimate whose every figure cites the estimate_ids it came from.

No LLM and no network: the "generation" step is a deterministic weighted
median / percentile over retrieved records, so each figure equals an actual
retrieved value.
"""

import argparse
import csv
import math
import re
import sys
from collections import Counter
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"

TOP_K_PARTS = 5
MAX_ESTIMATES = 8
SIMILARITY_POWER = 3
NGRAM_SIZES = (3, 4)


def load_parts(path=DATA_DIR / "parts_master.csv"):
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["typical_unit_price"] = int(r["typical_unit_price"])
    return rows


def load_estimates(path=DATA_DIR / "past_estimates.csv"):
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["quantity"] = int(r["quantity"])
        r["unit_price"] = int(r["unit_price"])
        r["lead_time_days"] = int(r["lead_time_days"])
    return rows


def part_text(part):
    return " ".join([part["name"], part["category"], part["material"], part["spec"]])


def tokenize(text):
    words = re.findall(r"[a-z0-9]+(?:\.[0-9]+)?", text.lower())
    features = ["w:" + w for w in words]
    for w in words:
        padded = f"#{w}#"
        for n in NGRAM_SIZES:
            features.extend("c:" + padded[i:i + n] for i in range(len(padded) - n + 1))
    return features


class Retriever:
    """TF-IDF (sublinear tf, smoothed idf) cosine retriever over parts."""

    def __init__(self, parts):
        self.parts = list(parts)
        docs = [Counter(tokenize(part_text(p))) for p in self.parts]
        n = len(docs)
        df = Counter()
        for d in docs:
            df.update(d.keys())
        self.idf = {t: math.log((1 + n) / (1 + c)) + 1.0 for t, c in df.items()}
        self.vectors = [self._vectorize(d) for d in docs]

    def _vectorize(self, counts):
        vec = {
            t: (1.0 + math.log(c)) * self.idf[t]
            for t, c in counts.items()
            if t in self.idf
        }
        norm = math.sqrt(sum(v * v for v in vec.values()))
        return {t: v / norm for t, v in vec.items()} if norm else {}

    def search(self, query, k=TOP_K_PARTS):
        q = self._vectorize(Counter(tokenize(query)))
        scored = []
        for part, vec in zip(self.parts, self.vectors):
            if len(vec) < len(q):
                sim = sum(v * q.get(t, 0.0) for t, v in vec.items())
            else:
                sim = sum(v * vec.get(t, 0.0) for t, v in q.items())
            scored.append((sim, part))
        scored.sort(key=lambda x: (-x[0], x[1]["part_id"]))
        return [(round(s, 4), p) for s, p in scored[:k] if s > 0]


def quantity_weight(est_qty, qty):
    if not qty:
        return 1.0
    return 1.0 / (1.0 + abs(math.log10(est_qty / qty)))


def retrieve(query, parts, estimates, qty=None, k=TOP_K_PARTS, exclude_ids=()):
    """Return (part_hits, estimate_hits). Each estimate hit carries its weight."""
    retriever = Retriever(parts)
    part_hits = retriever.search(query, k=k)
    sim_by_part = {p["part_id"]: s for s, p in part_hits}
    excluded = set(exclude_ids)
    hits = []
    for est in estimates:
        if est["estimate_id"] in excluded or est["part_id"] not in sim_by_part:
            continue
        sim = sim_by_part[est["part_id"]]
        weight = sim ** SIMILARITY_POWER * quantity_weight(est["quantity"], qty)
        hits.append({"estimate": est, "similarity": sim, "weight": round(weight, 6)})
    hits.sort(key=lambda h: (-h["weight"], h["estimate"]["estimate_id"]))
    return part_hits, hits[:MAX_ESTIMATES]


def weighted_quantile(hits, field, q):
    """Return the retrieved hit at weighted quantile q (lower interpolation)."""
    ordered = sorted(hits, key=lambda h: (h["estimate"][field], h["estimate"]["estimate_id"]))
    total = sum(h["weight"] for h in ordered)
    cum = 0.0
    for h in ordered:
        cum += h["weight"]
        if cum >= q * total - 1e-12:
            return h
    return ordered[-1]


def _figure(label, hit, field, method):
    est = hit["estimate"]
    return {
        "label": label,
        "value": est[field],
        "method": method,
        "sources": [est["estimate_id"]],
        "source_part_ids": [est["part_id"]],
    }


def draft_estimate(query, parts, estimates, qty=None, k=TOP_K_PARTS, exclude_ids=()):
    part_hits, hits = retrieve(query, parts, estimates, qty=qty, k=k, exclude_ids=exclude_ids)
    if not hits:
        return {"query": query, "qty": qty, "part_hits": part_hits, "hits": [], "figures": []}
    figures = [
        _figure("suggested_unit_price", weighted_quantile(hits, "unit_price", 0.5),
                "unit_price", "similarity-weighted median of retrieved unit prices"),
        _figure("price_range_low", weighted_quantile(hits, "unit_price", 0.25),
                "unit_price", "similarity-weighted 25th percentile of retrieved unit prices"),
        _figure("price_range_high", weighted_quantile(hits, "unit_price", 0.75),
                "unit_price", "similarity-weighted 75th percentile of retrieved unit prices"),
        _figure("suggested_lead_time_days", weighted_quantile(hits, "lead_time_days", 0.5),
                "lead_time_days", "similarity-weighted median of retrieved lead times"),
    ]
    return {"query": query, "qty": qty, "part_hits": part_hits, "hits": hits, "figures": figures}


def format_draft(draft, parts):
    by_id = {p["part_id"]: p for p in parts}
    est_by_id = {h["estimate"]["estimate_id"]: h["estimate"] for h in draft["hits"]}
    lines = [f"Query: {draft['query']}"]
    if draft["qty"]:
        lines.append(f"Requested quantity: {draft['qty']} (used only to weight retrieved estimates)")
    lines.append("")
    if not draft["figures"]:
        lines.append("No similar parts with past estimates were found; no draft produced.")
        return "\n".join(lines)

    lines.append("== Draft estimate (JPY, retrieval-based, fictional data) ==")
    units = {"suggested_lead_time_days": " days"}
    for fig in draft["figures"]:
        src = ", ".join(
            f"{e} ({est_by_id[e]['part_id']}, {_fmt(est_by_id[e], fig['label'])})" for e in fig["sources"]
        )
        lines.append(f"- {fig['label']}: {fig['value']:,}{units.get(fig['label'], ' JPY')}  <- {src}")
        lines.append(f"    method: {fig['method']}")

    lines.append("")
    lines.append("== Grounds: retrieved past estimates (all used in the figures above) ==")
    lines.append("estimate_id  part_id  similarity  weight    qty  unit_price  lead_days  date")
    for h in draft["hits"]:
        e = h["estimate"]
        lines.append(
            f"{e['estimate_id']:<12} {e['part_id']:<8} {h['similarity']:<11.4f} {h['weight']:<9.4f}"
            f"{e['quantity']:>4} {e['unit_price']:>11,} {e['lead_time_days']:>10}  {e['date']}"
        )

    lines.append("")
    lines.append("== Grounds: retrieved similar parts (master reference; typical price not used in the draft) ==")
    for sim, p in draft["part_hits"]:
        lines.append(
            f"{p['part_id']}  sim={sim:.4f}  {p['name']}  (master typical {p['typical_unit_price']:,} JPY)"
        )
        lines.append(f"    spec: {by_id[p['part_id']]['spec']}")
    return "\n".join(lines)


def _fmt(est, label):
    if label == "suggested_lead_time_days":
        return f"{est['lead_time_days']} days"
    return f"{est['unit_price']:,} JPY"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Draft a parts estimate from retrieved fictional records.")
    ap.add_argument("query", help="free-text part name / spec, e.g. 'L bracket SUS304 t2.0 60x60'")
    ap.add_argument("--qty", type=int, default=None, help="requested quantity (optional, weights retrieval)")
    ap.add_argument("-k", type=int, default=TOP_K_PARTS, help="number of similar parts to retrieve")
    args = ap.parse_args(argv)
    parts, estimates = load_parts(), load_estimates()
    draft = draft_estimate(args.query, parts, estimates, qty=args.qty, k=args.k)
    print(format_draft(draft, parts))
    return 0 if draft["figures"] else 1


if __name__ == "__main__":
    sys.exit(main())

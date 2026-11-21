"""Leave-one-out backtest of the retrieval-based estimate draft.

For each past estimate: hide it, draft an estimate for its part (query = the
part's name + spec, qty = the hidden estimate's quantity) from the remaining
records, and compare the suggested unit price with the hidden actual price.
Fully deterministic: no randomness is involved.
"""

import statistics
import sys

from agent import draft_estimate, load_estimates, load_parts, part_text

HIT_TOLERANCE = 0.20


def run_backtest(parts=None, estimates=None, hold_out_part=False):
    """Return metrics. hold_out_part=True also hides every estimate of the same part."""
    parts = parts if parts is not None else load_parts()
    estimates = estimates if estimates is not None else load_estimates()
    by_id = {p["part_id"]: p for p in parts}
    cases = []
    for est in estimates:
        hidden = {est["estimate_id"]}
        if hold_out_part:
            hidden |= {e["estimate_id"] for e in estimates if e["part_id"] == est["part_id"]}
        draft = draft_estimate(
            part_text(by_id[est["part_id"]]), parts, estimates, qty=est["quantity"], exclude_ids=hidden
        )
        if not draft["figures"]:
            cases.append({"estimate_id": est["estimate_id"], "predicted": None, "actual": est["unit_price"], "ape": None})
            continue
        predicted = draft["figures"][0]["value"]
        ape = abs(predicted - est["unit_price"]) / est["unit_price"]
        cases.append({"estimate_id": est["estimate_id"], "predicted": predicted, "actual": est["unit_price"], "ape": ape})
    scored = [c["ape"] for c in cases if c["ape"] is not None]
    return {
        "cases": len(cases),
        "drafted": len(scored),
        "median_ape": statistics.median(scored) if scored else None,
        "hit_rate": sum(a <= HIT_TOLERANCE for a in scored) / len(cases) if cases else 0.0,
        "details": cases,
    }


def _print(title, m):
    print(title)
    print(f"  cases:                         {m['cases']} (drafted: {m['drafted']})")
    print(f"  median absolute % error:       {m['median_ape'] * 100:.1f}%")
    print(f"  hit rate within +/-{HIT_TOLERANCE:.0%}:        {m['hit_rate'] * 100:.1f}%")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    loo = run_backtest()
    _print("Leave-one-out (hide one estimate):", loo)
    strict = run_backtest(hold_out_part=True)
    _print("Stricter: hide all estimates of the same part (new-part scenario):", strict)
    if "--details" in argv:
        print("\nestimate_id  predicted  actual  abs_%_err")
        for c in loo["details"]:
            err = "n/a" if c["ape"] is None else f"{c['ape'] * 100:.1f}%"
            print(f"{c['estimate_id']:<12} {c['predicted'] or '-':>9} {c['actual']:>7}  {err}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

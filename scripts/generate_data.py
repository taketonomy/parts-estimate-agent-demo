"""Regenerate the fictional CSVs in data/ from a fixed pricing model.

All parts, prices and estimates are fictional. The script is deterministic
(fixed seed), so re-running it reproduces the committed CSVs byte-for-byte.

Pricing model (JPY, typical unit price at quantity 100):
    price = family_base * material_factor * (size / family_ref_size) ** 0.8
            * (1 + 0.12 * extra_operations) * finish_factor
Past estimates apply a quantity factor, a small yearly drift and +-4% noise.
"""

import csv
import random
from datetime import date, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SEED = 20241101

MATERIAL_FACTOR = {
    "SPCC": 0.85,
    "SS400": 1.00,
    "A5052": 1.25,
    "S45C": 1.15,
    "SUS304": 1.70,
    "SUS303": 1.60,
    "C3604": 1.45,
    "POM": 0.80,
    "SUJ2": 1.40,
}

FINISH_FACTOR = {
    "none": 1.00,
    "zinc plating": 1.12,
    "black oxide": 1.08,
    "anodize": 1.15,
    "electropolish": 1.20,
    "induction hardening": 1.25,
}

# family: (category, processing, base price, reference size, base lead days)
FAMILIES = {
    "L Bracket": ("Bracket", "laser cut + bend", 420, 50, 7),
    "Mounting Plate": ("Plate", "laser cut + tapping", 650, 100, 6),
    "Shaft": ("Shaft", "CNC turning", 900, 100, 9),
    "Bushing": ("Bushing", "CNC turning", 260, 20, 6),
    "Hex Spacer": ("Spacer", "CNC turning + hex milling", 150, 15, 5),
    "Flange": ("Flange", "CNC turning + drilling", 1400, 80, 10),
    "Sheet Cover": ("Cover", "laser cut + multi bend", 1100, 150, 8),
    "Dowel Pin": ("Pin", "CNC turning + grinding", 120, 20, 7),
}

# (family, material, size key, spec text, size for pricing, extra ops, finish)
PARTS = [
    ("L Bracket", "SS400", "50x50 t2.3", "L bracket 50x50x30 t2.3, 1 bend, 2 holes dia6.6", 50, 0, "zinc plating"),
    ("L Bracket", "SS400", "75x75 t3.2", "L bracket 75x75x40 t3.2, 1 bend, 4 holes dia9", 75, 0, "zinc plating"),
    ("L Bracket", "SUS304", "50x50 t2.0", "L bracket 50x50x30 t2.0, 1 bend, 2 holes dia6.6", 50, 0, "none"),
    ("L Bracket", "SUS304", "60x60 t2.0", "L bracket 60x60x30 t2.0, 1 bend, 2 holes dia6.6", 60, 0, "none"),
    ("L Bracket", "A5052", "100x100 t3.0", "L bracket 100x100x50 t3.0, 1 bend, 4 holes dia9, rib", 100, 1, "anodize"),
    ("Mounting Plate", "A5052", "100x80 t5", "mounting plate 100x80 t5, 4 holes M5 tapped", 100, 0, "anodize"),
    ("Mounting Plate", "A5052", "150x100 t5", "mounting plate 150x100 t5, 6 holes M5 tapped", 150, 0, "anodize"),
    ("Mounting Plate", "SS400", "120x80 t6", "mounting plate 120x80 t6, 4 holes M6 tapped", 120, 0, "black oxide"),
    ("Mounting Plate", "SS400", "200x150 t9", "mounting plate 200x150 t9, 8 holes M8 tapped, chamfer", 200, 1, "black oxide"),
    ("Mounting Plate", "SUS304", "100x80 t4", "mounting plate 100x80 t4, 4 holes M5 tapped", 100, 0, "none"),
    ("Shaft", "S45C", "dia10 L100", "shaft dia10 x L100, h7 tolerance, both ends chamfer C0.5", 100, 0, "none"),
    ("Shaft", "S45C", "dia12 L150", "shaft dia12 x L150, h7 tolerance, keyway 4x2.5", 150, 1, "none"),
    ("Shaft", "S45C", "dia20 L250", "shaft dia20 x L250, h7 tolerance, keyway 6x3.5, induction hardened", 250, 1, "induction hardening"),
    ("Shaft", "SUS304", "dia10 L100", "shaft dia10 x L100, h7 tolerance, both ends chamfer C0.5", 100, 0, "none"),
    ("Shaft", "SUS304", "dia16 L200", "shaft dia16 x L200, h7 tolerance, M8 tapped end", 200, 1, "none"),
    ("Bushing", "C3604", "ID8 OD12 L15", "bushing ID8 x OD12 x L15, press fit", 15, 0, "none"),
    ("Bushing", "C3604", "ID10 OD14 L20", "bushing ID10 x OD14 x L20, press fit", 20, 0, "none"),
    ("Bushing", "C3604", "ID16 OD22 L30", "bushing ID16 x OD22 x L30, flanged, oil groove", 30, 1, "none"),
    ("Bushing", "POM", "ID10 OD14 L20", "bushing ID10 x OD14 x L20, resin, press fit", 20, 0, "none"),
    ("Bushing", "POM", "ID20 OD26 L25", "bushing ID20 x OD26 x L25, resin, flanged", 25, 1, "none"),
    ("Hex Spacer", "A5052", "M3 L10", "hex spacer M3 x L10, width across flats 5.5, female-female", 10, 0, "none"),
    ("Hex Spacer", "A5052", "M4 L15", "hex spacer M4 x L15, width across flats 7, female-female", 15, 0, "none"),
    ("Hex Spacer", "SUS303", "M3 L10", "hex spacer M3 x L10, width across flats 5.5, female-female", 10, 0, "none"),
    ("Hex Spacer", "SUS303", "M5 L20", "hex spacer M5 x L20, width across flats 8, male-female", 20, 0, "none"),
    ("Hex Spacer", "C3604", "M4 L15", "hex spacer M4 x L15, width across flats 7, female-female, nickel look", 15, 0, "none"),
    ("Flange", "SS400", "OD80 t12", "flange OD80 x t12, bore dia25, 4 holes dia9 on PCD60", 80, 0, "zinc plating"),
    ("Flange", "SS400", "OD100 t15", "flange OD100 x t15, bore dia30, 4 holes dia11 on PCD75", 100, 0, "zinc plating"),
    ("Flange", "SUS304", "OD80 t12", "flange OD80 x t12, bore dia25, 4 holes dia9 on PCD60", 80, 0, "none"),
    ("Flange", "SUS304", "OD120 t16", "flange OD120 x t16, bore dia35, 6 holes dia11 on PCD95, O-ring groove", 120, 1, "electropolish"),
    ("Flange", "A5052", "OD100 t15", "flange OD100 x t15, bore dia30, 4 holes dia11 on PCD75", 100, 0, "anodize"),
    ("Sheet Cover", "SPCC", "150x100x50 t1.0", "sheet cover 150x100x50 t1.0, 4 bends, vent slots", 150, 0, "zinc plating"),
    ("Sheet Cover", "SPCC", "200x150x60 t1.2", "sheet cover 200x150x60 t1.2, 4 bends, vent slots", 200, 0, "zinc plating"),
    ("Sheet Cover", "SPCC", "300x200x80 t1.6", "sheet cover 300x200x80 t1.6, 4 bends, vent slots, welded corners", 300, 1, "zinc plating"),
    ("Sheet Cover", "A5052", "150x100x50 t1.5", "sheet cover 150x100x50 t1.5, 4 bends, vent slots", 150, 0, "anodize"),
    ("Sheet Cover", "SUS304", "200x150x60 t1.0", "sheet cover 200x150x60 t1.0, 4 bends, hairline finish", 200, 0, "none"),
    ("Dowel Pin", "SUJ2", "dia6 L20", "dowel pin dia6 x L20, m6 tolerance, hardened and ground", 20, 0, "none"),
    ("Dowel Pin", "SUJ2", "dia8 L30", "dowel pin dia8 x L30, m6 tolerance, hardened and ground", 30, 0, "none"),
    ("Dowel Pin", "SUJ2", "dia10 L40", "dowel pin dia10 x L40, m6 tolerance, hardened and ground", 40, 0, "none"),
    ("Dowel Pin", "S45C", "dia8 L30", "dowel pin dia8 x L30, m6 tolerance, ground", 30, 0, "black oxide"),
    ("Dowel Pin", "SUS304", "dia6 L20", "dowel pin dia6 x L20, m6 tolerance, ground", 20, 0, "none"),
]

QTY_FACTOR = {10: 1.15, 50: 1.05, 100: 1.00, 300: 0.95, 500: 0.92}
QTY_LEAD_EXTRA = {10: 0, 50: 1, 100: 2, 300: 4, 500: 6}


def round10(x):
    return int(round(x / 10.0)) * 10


def typical_price(family, material, size, extra_ops, finish):
    _, _, base, ref, _ = FAMILIES[family]
    price = (
        base
        * MATERIAL_FACTOR[material]
        * (size / ref) ** 0.8
        * (1 + 0.12 * extra_ops)
        * FINISH_FACTOR[finish]
    )
    return round10(price)


def main():
    rng = random.Random(SEED)
    parts = []
    for i, (family, material, size_key, spec, size, ops, finish) in enumerate(PARTS):
        category, processing, _, _, lead = FAMILIES[family]
        parts.append(
            {
                "part_id": f"PT-{1001 + i}",
                "name": f"{family} {size_key} {material}",
                "category": category,
                "material": material,
                "spec": f"{spec}; process: {processing}; finish: {finish}",
                "typical_unit_price": typical_price(family, material, size, ops, finish),
                "_lead": lead + ops,
            }
        )

    # 60 estimates: every part gets one, the first 20 by a fixed shuffle get a second.
    order = list(range(len(parts)))
    rng.shuffle(order)
    assignments = list(range(len(parts))) + sorted(order[:20])
    start = date(2024, 1, 9)
    estimates = []
    for n, idx in enumerate(sorted(assignments, key=lambda k: (k, rng.random()))):
        part = parts[idx]
        qty = rng.choice(sorted(QTY_FACTOR))
        day = start + timedelta(days=rng.randrange(0, 700))
        years = (day - start).days / 365.0
        price = part["typical_unit_price"] * QTY_FACTOR[qty] * (1 + 0.02 * years)
        price *= 1 + rng.uniform(-0.04, 0.04)
        estimates.append(
            {
                "part_id": part["part_id"],
                "quantity": qty,
                "unit_price": max(10, round10(price)),
                "lead_time_days": part["_lead"] + QTY_LEAD_EXTRA[qty] + rng.randrange(0, 3),
                "date": day.isoformat(),
            }
        )
    estimates.sort(key=lambda e: (e["date"], e["part_id"]))
    for n, est in enumerate(estimates):
        est["estimate_id"] = f"EST-{2001 + n}"

    DATA_DIR.mkdir(exist_ok=True)
    with open(DATA_DIR / "parts_master.csv", "w", newline="", encoding="utf-8") as f:
        fields = ["part_id", "name", "category", "material", "spec", "typical_unit_price"]
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows(parts)
    with open(DATA_DIR / "past_estimates.csv", "w", newline="", encoding="utf-8") as f:
        fields = ["estimate_id", "part_id", "quantity", "unit_price", "lead_time_days", "date"]
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(estimates)
    print(f"wrote {len(parts)} parts and {len(estimates)} estimates to {DATA_DIR}")


if __name__ == "__main__":
    main()

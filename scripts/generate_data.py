"""Generate the sample BW style extracts with known, planted defects.

Run from the repo root: python scripts/generate_data.py
The planted counts are written to data/planted_defects.json and checked by the tests.
"""
import csv
import json
import os
import random

SEED = 11
ROWS = 600
OUT = os.path.join(os.path.dirname(__file__), "..", "data")
rng = random.Random(SEED)

UNITS = ["PC", "KG", "M"]
CURRENCIES = ["EUR", "USD", "CHF"]
COMP_CODES = ["1000", "2000", "3000"]
GROUPS = ["HYD", "ELE", "SEN", "MEC"]
COUNTRIES = ["DE", "FR", "NL", "IN", "US", "CH"]

materials = [
    {"MATERIAL": f"MAT{i:06d}", "DESCR": f"Material {i}", "MATL_GROUP": rng.choice(GROUPS),
     "BASE_UNIT": rng.choice(UNITS)}
    for i in range(1, 61)
]
customers = [
    {"CUSTOMER": f"C{i:05d}", "NAME": f"Customer {i}", "COUNTRY": rng.choice(COUNTRIES)}
    for i in range(1, 41)
]

rows = []
for n in range(ROWS):
    mat = rng.choice(materials)
    qty = rng.randint(1, 50)
    price = round(rng.uniform(5, 400), 2)
    day = rng.randint(1, 28)
    month = rng.randint(1, 9)
    rows.append({
        "DOC_NUMBER": f"{4500000000 + n // 2}",
        "DOC_ITEM": f"{(n % 2 + 1) * 10:06d}",
        "CALDAY": f"2026{month:02d}{day:02d}",
        "MATERIAL": mat["MATERIAL"],
        "CUSTOMER": rng.choice(customers)["CUSTOMER"],
        "COMP_CODE": rng.choice(COMP_CODES),
        "QUANTITY": str(qty),
        "UNIT": mat["BASE_UNIT"],
        "NET_VALUE": f"{qty * price:.2f}",
        "CURRENCY": rng.choice(CURRENCIES),
    })

# plant defects on disjoint rows
order = list(range(ROWS))
rng.shuffle(order)
plan = {"null_customer": 14, "orphan_material": 12, "negative_quantity": 8, "future_date": 6,
        "bad_currency": 7, "bad_unit": 5, "extreme_value": 4}
pos = 0
picked = {}
for name, count in plan.items():
    picked[name] = order[pos:pos + count]
    pos += count
clean = order[pos:]

for i in picked["null_customer"]:
    rows[i]["CUSTOMER"] = ""
for k, i in enumerate(picked["orphan_material"]):
    rows[i]["MATERIAL"] = f"MAT9{k:05d}"
for i in picked["negative_quantity"]:
    rows[i]["QUANTITY"] = "-" + rows[i]["QUANTITY"]
for i in picked["future_date"]:
    rows[i]["CALDAY"] = "20261" + str(rng.randint(0, 2)) + f"{rng.randint(1, 28):02d}"
for i in picked["bad_currency"]:
    rows[i]["CURRENCY"] = rng.choice(["EU", "usd", "XXX"])
for i in picked["bad_unit"]:
    rows[i]["UNIT"] = rng.choice(["PCS", "kg", "??"])
for i in picked["extreme_value"]:
    rows[i]["NET_VALUE"] = f"{rng.randint(5, 9) * 1_000_000}.00"

dups = 6
for i in clean[:dups]:
    rows.append(dict(rows[i]))

# master data defects
for m in materials[:3]:
    m["MATL_GROUP"] = ""
for c in customers[:2]:
    c["COUNTRY"] = "Germany"


def write(name, data):
    with open(os.path.join(OUT, name), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(data[0].keys()), lineterminator="\n")
        w.writeheader()
        w.writerows(data)


write("ZSD_O01.csv", rows)
write("MAT_ATTR.csv", materials)
write("CUST_ATTR.csv", customers)

planted = dict(plan)
planted["duplicate_extra_rows"] = dups
planted["duplicate_rows_flagged"] = dups * 2
planted["material_missing_group"] = 3
planted["customer_bad_country"] = 2
planted["rows_total"] = len(rows)
with open(os.path.join(OUT, "planted_defects.json"), "w", encoding="utf-8") as fh:
    json.dump(planted, fh, indent=2)
    fh.write("\n")
print(json.dumps(planted))

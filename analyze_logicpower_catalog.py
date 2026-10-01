#!/usr/bin/env python3
import csv
import json
import os
import urllib.parse
import urllib.request
from collections import Counter
from decimal import Decimal, InvalidOperation

API_BASE = "https://api.b2b.logicpower.ua"
API_PATH = "/external/catalog/product/list/all"
PAGE_SIZE = 500
API_KEY = os.environ["LOGICPOWER_API_KEY"]
OUT_DIR = "analysis_output"

def fetch_page(page_num):
    query = urllib.parse.urlencode({
        "pageSize": PAGE_SIZE,
        "pageNum": page_num,
    })
    req = urllib.request.Request(
        f"{API_BASE}{API_PATH}?{query}",
        headers={
            "X-Api-Key": API_KEY,
            "Accept": "application/json",
            "User-Agent": "DragonElectro-LogicPower-Analyzer/1.0",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        payload = json.loads(r.read().decode("utf-8"))
    if not payload.get("status") or payload.get("code") != 200:
        raise RuntimeError(f"LogicPower API error: {payload}")
    return payload.get("data", {})

def money_value(price_obj):
    money = price_obj.get("money") or {}
    if money.get("currency") != "UAH":
        return None
    amount = money.get("amount")
    if amount is None:
        return None
    try:
        return Decimal(str(amount))
    except InvalidOperation:
        return None

def pct(x):
    if x is None:
        return ""
    return f"{x:.2f}"

items_all = []
page = 1
total_items = None

while True:
    data = fetch_page(page)
    items = data.get("items", [])
    total_items = int(data.get("totalItems", 0) or 0)
    items_all.extend(items)
    print(f"Page {page}: {len(items)} items; collected {len(items_all)}/{total_items or '?'}")
    if not items:
        break
    if total_items and page * PAGE_SIZE >= total_items:
        break
    page += 1

price_type_counts = Counter()
status_counts = Counter()
all_price_types = set()

for item in items_all:
    status_counts[str(item.get("status", ""))] += 1
    for p in item.get("prices", []):
        ptype = str(p.get("type", ""))
        if ptype:
            all_price_types.add(ptype)
            if money_value(p) is not None:
                price_type_counts[ptype] += 1

all_price_types = sorted(all_price_types)

rows = []
for item in items_all:
    price_map = {}
    for p in item.get("prices", []):
        ptype = str(p.get("type", ""))
        value = money_value(p)
        if ptype and value is not None:
            price_map[ptype] = value

    rrp = price_map.get("recommendedRetail")

    # We intentionally do NOT guess which supplier field is our actual buy price.
    # Instead we calculate economics versus every non-RRP UAH price type.
    candidate_metrics = {}
    for ptype, buy in price_map.items():
        if ptype == "recommendedRetail":
            continue
        margin = None
        markup = None
        profit = None
        if rrp is not None and rrp > 0 and buy >= 0:
            profit = rrp - buy
            margin = (profit / rrp) * Decimal("100")
            if buy > 0:
                markup = (profit / buy) * Decimal("100")
        candidate_metrics[ptype] = {
            "buy": buy,
            "profit": profit,
            "margin": margin,
            "markup": markup,
        }

    row = {
        "code": str(item.get("code", "")),
        "name": str(item.get("name", "")),
        "status": str(item.get("status", "")),
        "recommendedRetail": rrp,
        "price_map": price_map,
        "candidate_metrics": candidate_metrics,
    }
    rows.append(row)

os.makedirs(OUT_DIR, exist_ok=True)

summary = {
    "total_items": len(items_all),
    "reported_total_items": total_items,
    "status_counts": dict(status_counts),
    "price_type_counts": dict(price_type_counts),
    "price_types": all_price_types,
}

with open(os.path.join(OUT_DIR, "logicpower_price_summary.json"), "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)

fieldnames = ["code", "name", "status", "recommendedRetail"]
for ptype in all_price_types:
    if ptype == "recommendedRetail":
        continue
    fieldnames += [
        f"{ptype}_price",
        f"{ptype}_profit_uah",
        f"{ptype}_margin_pct",
        f"{ptype}_markup_pct",
    ]

with open(os.path.join(OUT_DIR, "logicpower_catalog_economics.csv"), "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    for row in rows:
        out = {
            "code": row["code"],
            "name": row["name"],
            "status": row["status"],
            "recommendedRetail": str(row["recommendedRetail"]) if row["recommendedRetail"] is not None else "",
        }
        for ptype in all_price_types:
            if ptype == "recommendedRetail":
                continue
            m = row["candidate_metrics"].get(ptype)
            out[f"{ptype}_price"] = str(m["buy"]) if m else ""
            out[f"{ptype}_profit_uah"] = str(m["profit"]) if m and m["profit"] is not None else ""
            out[f"{ptype}_margin_pct"] = pct(m["margin"]) if m else ""
            out[f"{ptype}_markup_pct"] = pct(m["markup"]) if m else ""
        w.writerow(out)

# Compact text report for Actions logs.
print("\n=== LOGICPOWER CATALOG PRICE AUDIT ===")
print(f"Total products: {len(items_all)}")
print("Statuses:")
for k, v in sorted(status_counts.items()):
    print(f"  {k or '<empty>'}: {v}")
print("Price types (UAH values):")
for k, v in sorted(price_type_counts.items()):
    print(f"  {k}: {v}")

# For each non-RRP price type, count products above thresholds.
for ptype in all_price_types:
    if ptype == "recommendedRetail":
        continue
    c15 = c20 = avail15 = avail20 = 0
    margins = []
    for row in rows:
        m = row["candidate_metrics"].get(ptype)
        if not m or m["margin"] is None:
            continue
        margins.append(m["margin"])
        if m["margin"] >= Decimal("15"):
            c15 += 1
            if row["status"] == "inStock":
                avail15 += 1
        if m["margin"] >= Decimal("20"):
            c20 += 1
            if row["status"] == "inStock":
                avail20 += 1
    if margins:
        avg = sum(margins) / Decimal(len(margins))
        print(
            f"{ptype}: rows={len(margins)}, avg_margin={avg:.2f}%, "
            f">=15%={c15} (inStock {avail15}), "
            f">=20%={c20} (inStock {avail20})"
        )

print(f"\nSaved: {OUT_DIR}/logicpower_price_summary.json")
print(f"Saved: {OUT_DIR}/logicpower_catalog_economics.csv")

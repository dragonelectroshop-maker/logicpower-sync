#!/usr/bin/env python3
import os
import json
import html
import urllib.parse
import urllib.request
from datetime import datetime, timezone

API_BASE = "https://api.b2b.logicpower.ua"
API_PATH = "/external/catalog/product/list/all"
PAGE_SIZE = 500
OUT = os.path.join("public", "logicpower-sync.yml")

# Last known DragonElectro prices (already = LogicPower recommendedRetail - 1 UAH).
# Used only as a safe fallback if a product temporarily disappears from the API.
FALLBACK_PRICES = {
    "40765": 70264,
    "37760": 39380,
    "11382": 131270,
    "40783": 210599,
    "40782": 159533,
    "40781": 118363,
    "30381": 118139,
    "22793": 128699,
    "40766": 84317,
    "40764": 51323,
    "39929": 93999,
    "38568": 538654,
}

API_KEY = os.environ.get("LOGICPOWER_API_KEY")
if not API_KEY:
    raise SystemExit("LOGICPOWER_API_KEY is not set")

with open("products.json", "r", encoding="utf-8") as f:
    PRODUCTS = json.load(f)

wanted = {str(p["code"]): p for p in PRODUCTS}

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
            "User-Agent": "DragonElectro-LogicPower-Sync/1.2",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        payload = json.loads(r.read().decode("utf-8"))

    if not payload.get("status") or payload.get("code") != 200:
        raise RuntimeError(f"LogicPower API error: {payload}")
    return payload["data"]

found = {}
page = 1
total_items = None

while True:
    data = fetch_page(page)
    items = data.get("items", [])
    total_items = data.get("totalItems", total_items)

    for item in items:
        code = str(item.get("code", ""))
        if code in wanted:
            found[code] = item

    if len(found) == len(wanted):
        break
    if not items:
        break
    if total_items is not None and page * PAGE_SIZE >= int(total_items):
        break
    page += 1

def retail_price(item):
    if not item:
        return None
    for p in item.get("prices", []):
        if p.get("type") == "recommendedRetail":
            money = p.get("money") or {}
            if money.get("currency") == "UAH" and money.get("amount") is not None:
                return max(0.01, float(money["amount"]) - 1.0)
    return None

def esc(value):
    return html.escape(str(value), quote=True)

def price_text(value):
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")

# GitHub runners use UTC. This timestamp is informational only.
now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

lines = [
    '<?xml version="1.0" encoding="UTF-8"?>',
    f'<yml_catalog date="{now}">',
    '  <shop>',
    '    <categories>',
    '      <category id="910001" portal_id="5140401">LogicPower Sync</category>',
    '    </categories>',
    '    <offers>',
]

for code, meta in wanted.items():
    item = found.get(code)
    is_available = bool(item and item.get("status") == "inStock")

    # Valid XML: the id value is always properly closed with a quote.
    attrs = [
        f'id="{esc(meta["offer_id"])}"',
        f'available="{"true" if is_available else "false"}"',
        'selling_type="r"',
    ]
    if is_available:
        attrs.append('in_stock="true"')

    lines.append(f'      <offer {" ".join(attrs)}>')

    # ASCII-only service fields: Prom will NOT be allowed to update names/categories
    # from this synchronization link; only price and availability will be checked.
    lines.append(f'        <name>LogicPower LP-{esc(code)}</name>')
    lines.append('        <categoryId>910001</categoryId>')
    lines.append('        <portal_category_id>5140401</portal_category_id>')

    current_price = retail_price(item)
    if current_price is None:
        current_price = float(FALLBACK_PRICES[code])

    lines.append(f'        <price>{price_text(current_price)}</price>')
    lines.append('        <currencyId>UAH</currencyId>')
    lines.append(f'        <vendorCode>LP-{esc(code)}</vendorCode>')
    lines.append('      </offer>')

lines += [
    '    </offers>',
    '  </shop>',
    '</yml_catalog>',
    '',
]

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8", newline="\n") as f:
    f.write("\n".join(lines))

missing = sorted(set(wanted) - set(found))
print(f"Generated {OUT}; found {len(found)}/{len(wanted)} products")
if missing:
    print("Missing API codes marked unavailable:", ", ".join(missing))

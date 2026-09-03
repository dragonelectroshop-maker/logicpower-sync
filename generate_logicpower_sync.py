#!/usr/bin/env python3
import os, json, html, urllib.parse, urllib.request
from datetime import datetime, timezone

API_BASE = "https://api.b2b.logicpower.ua"
API_PATH = "/external/catalog/product/list/all"
PAGE_SIZE = 500
OUT = os.path.join("public", "logicpower-sync.yml")

API_KEY = os.environ.get("LOGICPOWER_API_KEY")
if not API_KEY:
    raise SystemExit("LOGICPOWER_API_KEY is not set")

with open("products.json", "r", encoding="utf-8") as f:
    PRODUCTS = json.load(f)

wanted = {p["code"]: p for p in PRODUCTS}

def fetch_page(page_num):
    query = urllib.parse.urlencode({"pageSize": PAGE_SIZE, "pageNum": page_num})
    req = urllib.request.Request(
        f"{API_BASE}{API_PATH}?{query}",
        headers={
            "X-Api-Key": API_KEY,
            "Accept": "application/json",
            "User-Agent": "DragonElectro-LogicPower-Sync/1.1",
        },
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
    if len(found) == len(wanted) or not items:
        break
    if total_items is not None and page * PAGE_SIZE >= int(total_items):
        break
    page += 1

def retail_price(item):
    for p in item.get("prices", []):
        if p.get("type") == "recommendedRetail":
            money = p.get("money") or {}
            if money.get("currency") == "UAH" and money.get("amount") is not None:
                return max(0.01, float(money["amount"]) - 1.0)
    return None

def esc(v):
    return html.escape(str(v), quote=True)

def price_text(v):
    if v is None:
        return None
    return str(int(v)) if float(v).is_integer() else f"{v:.2f}".rstrip("0").rstrip(".")

now = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")

lines = [
    '<?xml version="1.0" encoding="UTF-8"?>',
    f'<yml_catalog date="{esc(now)}">',
    '  <shop>',
    '    <categories>',
    '      <category id="910001" portal_id="5140401">LogicPower Sync</category>',
    '    </categories>',
    '    <offers>',
]

for code, meta in wanted.items():
    item = found.get(code)
    available = bool(item and item.get("status") == "inStock")
    attrs = [
        f'id="{esc(meta["offer_id"])}"',
        f'available="{"true" if available else "false"}"',
    ]
    if available:
        attrs.append('in_stock="true"')

    lines.append(f'      <offer {" ".join(attrs)} selling_type="r">')
    lines.append(f'        <name>LogicPower LP-{esc(code)}</name>')
    lines.append(f'        <categoryId>{esc(meta["category_id"])}</categoryId>')
    if meta.get("portal_category_id"):
        lines.append(f'        <portal_category_id>{esc(meta["portal_category_id"])}</portal_category_id>')

    if item:
        price = retail_price(item)
        if price is not None:
            lines.append(f'        <price>{price_text(price)}</price>')
            lines.append('        <currencyId>UAH</currencyId>')

    lines.append(f'        <vendorCode>LP-{esc(code)}</vendorCode>')
    lines.append('      </offer>')

lines += ['    </offers>', '  </shop>', '</yml_catalog>', '']

os.makedirs("public", exist_ok=True)
with open(OUT, "w", encoding="utf-8", newline="\n") as f:
    f.write("\n".join(lines))

missing = sorted(set(wanted) - set(found))
print(f"Generated {OUT}; found {len(found)}/{len(wanted)} products")
if missing:
    print("Missing codes marked unavailable:", ", ".join(missing))

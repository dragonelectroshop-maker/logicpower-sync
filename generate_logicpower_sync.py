#!/usr/bin/env python3
import os, json, html, urllib.parse, urllib.request
from datetime import datetime, timezone

API_BASE="https://api.b2b.logicpower.ua"
PATH="/external/catalog/product/list/all"
PAGE_SIZE=500
OUT="public/logicpower-sync.yml"
API_KEY=os.environ.get("LOGICPOWER_API_KEY")
if not API_KEY:
    raise SystemExit("LOGICPOWER_API_KEY is not set")

with open("products.json", encoding="utf-8") as f:
    products=json.load(f)
wanted={p["code"]:p for p in products}

def fetch(page):
    q=urllib.parse.urlencode({"pageSize":PAGE_SIZE,"pageNum":page})
    req=urllib.request.Request(
        API_BASE+PATH+"?"+q,
        headers={"X-Api-Key":API_KEY,"Accept":"application/json","User-Agent":"DragonElectro-LogicPower-Sync/1.0"}
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        x=json.loads(r.read().decode("utf-8"))
    if not x.get("status") or x.get("code")!=200:
        raise RuntimeError(x)
    return x["data"]

found={}
page=1
total=None
while True:
    data=fetch(page)
    items=data.get("items",[])
    total=data.get("totalItems",total)
    for item in items:
        code=str(item.get("code",""))
        if code in wanted:
            found[code]=item
    if len(found)==len(wanted) or not items:
        break
    if total is not None and page*PAGE_SIZE>=int(total):
        break
    page+=1

def retail(item):
    for p in item.get("prices",[]):
        if p.get("type")=="recommendedRetail":
            m=p.get("money") or {}
            if m.get("currency")=="UAH" and m.get("amount") is not None:
                return max(0.01,float(m["amount"])-1)
    return None

def esc(v): return html.escape(str(v), quote=True)
def pt(v):
    if v is None: return None
    return str(int(v)) if float(v).is_integer() else str(v)

stamp=datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")
lines=['<?xml version="1.0" encoding="UTF-8"?>',
       f'<yml_catalog date="{stamp}">','  <shop>','    <categories>',
       '      <category id="910001" portal_id="5140401">LogicPower TEST — Инверторы DE</category>',
       '    </categories>','    <offers>']

for code,meta in wanted.items():
    item=found.get(code)
    ok=bool(item and item.get("status")=="inStock")
    attrs=[f'id="{esc(meta["offer_id"])}', f'available="{"true" if ok else "false"}"']
    if ok: attrs.append('in_stock="true"')
    lines.append(f'      <offer {" ".join(attrs)} selling_type="r">')
    lines.append(f'        <name>{esc(meta["name"])}</name>')
    lines.append(f'        <categoryId>{esc(meta["category_id"])}</categoryId>')
    if meta.get("portal_category_id"):
        lines.append(f'        <portal_category_id>{esc(meta["portal_category_id"])}</portal_category_id>')
    if item:
        price=retail(item)
        if price is not None:
            lines.append(f'        <price>{pt(price)}</price>')
            lines.append('        <currencyId>UAH</currencyId>')
    lines.append(f'        <vendorCode>LP-{esc(code)}</vendorCode>')
    lines.append('      </offer>')

lines += ['    </offers>','  </shop>','</yml_catalog>','']
os.makedirs("public",exist_ok=True)
with open(OUT,"w",encoding="utf-8",newline="\n") as f:
    f.write("\n".join(lines))
print(f"Generated {OUT}; found {len(found)}/{len(wanted)} products")
missing=sorted(set(wanted)-set(found))
if missing:
    print("Missing codes marked unavailable:",", ".join(missing))

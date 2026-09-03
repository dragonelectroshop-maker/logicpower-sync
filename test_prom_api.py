import os
import json
import urllib.request

TOKEN = os.environ["PROM_API_TOKEN"]
EXTERNAL_ID = "LP-40765"
NEW_PRICE = 70264

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/json",
    "Content-Type": "application/json",
}

# 1. Сначала читаем товар
get_url = f"https://my.prom.ua/api/v1/products/by_external_id/{EXTERNAL_ID}"

req = urllib.request.Request(get_url, headers=headers, method="GET")

with urllib.request.urlopen(req, timeout=30) as response:
    before = json.loads(response.read().decode("utf-8"))

product = before["product"]
old_price = product["price"]

print("PRODUCT:", product["external_id"])
print("PRICE BEFORE:", old_price)

# Защита от случайного изменения не того товара
if product["external_id"] != EXTERNAL_ID:
    raise SystemExit("ERROR: Wrong product")

if old_price not in (70265, 70264):
    raise SystemExit(f"SAFETY STOP: unexpected current price {old_price}")

# Если цена уже нужная — ничего не меняем
if old_price != NEW_PRICE:
    payload = json.dumps([
        {
            "id": EXTERNAL_ID,
            "price": NEW_PRICE
        }
    ]).encode("utf-8")

    edit_url = "https://my.prom.ua/api/v1/products/edit_by_external_id"

    req = urllib.request.Request(
        edit_url,
        data=payload,
        headers=headers,
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=30) as response:
        result = response.read().decode("utf-8")
        print("EDIT HTTP STATUS:", response.status)
        print("EDIT RESPONSE:", result)

# 2. Проверяем результат
req = urllib.request.Request(get_url, headers=headers, method="GET")

with urllib.request.urlopen(req, timeout=30) as response:
    after = json.loads(response.read().decode("utf-8"))

final_price = after["product"]["price"]

print("PRICE AFTER:", final_price)

if final_price != NEW_PRICE:
    raise SystemExit("ERROR: Price was not updated correctly")

print("PROM PRICE UPDATE TEST: OK")

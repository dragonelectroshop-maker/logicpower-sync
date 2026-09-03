import os
import json
import urllib.parse
import urllib.request

LOGICPOWER_API_KEY = os.environ["LOGICPOWER_API_KEY"]
PROM_API_TOKEN = os.environ["PROM_API_TOKEN"]

LOGICPOWER_API = "https://api.b2b.logicpower.ua"
PROM_API = "https://my.prom.ua/api/v1"

PAGE_SIZE = 500

# Работаем ТОЛЬКО с этими 12 товарами.
CODES = {
    "40765",
    "37760",
    "11382",
    "40783",
    "40782",
    "40781",
    "30381",
    "22793",
    "40766",
    "40764",
    "39929",
    "38568",
}


def logicpower_page(page_num):
    query = urllib.parse.urlencode({
        "pageSize": PAGE_SIZE,
        "pageNum": page_num,
    })

    request = urllib.request.Request(
        f"{LOGICPOWER_API}/external/catalog/product/list/all?{query}",
        headers={
            "X-Api-Key": LOGICPOWER_API_KEY,
            "Accept": "application/json",
        },
        method="GET",
    )

    with urllib.request.urlopen(request, timeout=60) as response:
        data = json.loads(response.read().decode("utf-8"))

    if not data.get("status") or data.get("code") != 200:
        raise RuntimeError(f"LogicPower API error: {data}")

    return data["data"]


def get_logicpower_products():
    found = {}
    page = 1

    while True:
        data = logicpower_page(page)
        items = data.get("items", [])
        total_items = int(data.get("totalItems", 0))

        for item in items:
            code = str(item.get("code", ""))

            if code in CODES:
                found[code] = item

        if not items:
            break

        if page * PAGE_SIZE >= total_items:
            break

        page += 1

    return found


def recommended_price(item):
    for price in item.get("prices", []):
        if price.get("type") == "recommendedRetail":
            money = price.get("money") or {}

            if money.get("currency") == "UAH":
                amount = money.get("amount")

                if amount is not None:
                    return max(0.01, float(amount) - 1)

    return None


def prom_get_product(external_id):
    url = f"{PROM_API}/products/by_external_id/{external_id}"

    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {PROM_API_TOKEN}",
            "Accept": "application/json",
        },
        method="GET",
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))["product"]


def prom_update(products):
    url = f"{PROM_API}/products/edit_by_external_id"

    body = json.dumps(
        products,
        ensure_ascii=False
    ).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {PROM_API_TOKEN}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=60) as response:
        result = json.loads(response.read().decode("utf-8"))

    return result


print("Reading LogicPower...")

logic_products = get_logicpower_products()

print(
    f"LogicPower products found: "
    f"{len(logic_products)}/{len(CODES)}"
)

updates = []

for code in sorted(CODES):

    external_id = f"LP-{code}"

    # Проверяем, что такой товар реально существует именно в DragonElectro.
    prom_product = prom_get_product(external_id)

    if prom_product.get("external_id") != external_id:
        raise RuntimeError(
            f"Safety stop: wrong Prom product for {external_id}"
        )

    logic_item = logic_products.get(code)

    # Если товар полностью исчез из каталога LogicPower,
    # считаем его отсутствующим.
    if logic_item is None:
        updates.append({
            "id": external_id,
            "presence": "not_available",
        })

        print(
            external_id,
            "LogicPower product missing -> NOT AVAILABLE"
        )

        continue

    price = recommended_price(logic_item)

    presence = (
        "available"
        if logic_item.get("status") == "inStock"
        else "not_available"
    )

    update = {
        "id": external_id,
        "presence": presence,
    }

    # Если LogicPower временно не отдал цену,
    # старую цену Prom не трогаем.
    if price is not None:
        update["price"] = price

    updates.append(update)

    print(
        external_id,
        "price:",
        price if price is not None else "UNCHANGED",
        "presence:",
        presence,
    )


if len(updates) != len(CODES):
    raise RuntimeError(
        f"Safety stop: expected {len(CODES)} updates, "
        f"got {len(updates)}"
    )


print("Sending updates to Prom...")

result = prom_update(updates)

print(
    json.dumps(
        result,
        ensure_ascii=False,
        indent=2
    )
)

errors = result.get("errors")

if errors:
    raise RuntimeError(
        f"Prom returned errors: {errors}"
    )

print("LOGICPOWER -> PROM SYNC: OK")
print("Updated products:", len(updates))

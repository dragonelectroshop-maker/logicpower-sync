#!/usr/bin/env python3

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


LOGICPOWER_API_KEY = os.environ["LOGICPOWER_API_KEY"]
PROM_API_TOKEN = os.environ["PROM_API_TOKEN"]

LOGICPOWER_URL = (
    "https://api.b2b.logicpower.ua"
    "/external/catalog/product/list/all"
)
PROM_EDIT_URL = (
    "https://my.prom.ua/api/v1/"
    "products/edit_by_external_id"
)

PAGE_SIZE = 500
REQUEST_DELAY_SECONDS = 0.50
MAX_PROM_ATTEMPTS = 5

# Temporary safety pause. While enabled, every LogicPower product tracked by
# this integration is forced to "not_available" on Prom. Prices are not sent,
# so the current Dragon Electro prices remain unchanged.
FORCE_ALL_NOT_AVAILABLE = True


# Logic Power codes used in Dragon Electro as external IDs LP-xxxxx.
TRACKED_CODES = {
    "1078", "1079", "1212", "1213", "1454", "1456", "1879", "2436",
    "3170", "3172", "3173", "3336", "3404", "3405", "3643", "4147",
    "4976", "4978", "4980", "4981", "4986", "4990", "6615", "8295",
    "8648", "9323", "10003", "10358", "10397", "11382", "14190",
    "17934", "17935", "17936", "17938", "18013", "18818", "19239",
    "19241", "19339", "19474", "19577", "19578", "19729", "19744",
    "19745", "19746", "19747", "19748", "19749", "19750", "19751",
    "19752", "19753", "19761", "19762", "19953", "20054", "20055",
    "20120", "20121", "20123", "20125", "20140", "20141", "20150",
    "20151", "20152", "20153", "20166", "20524", "21031", "21339",
    "21379", "21927", "21928", "21929", "21930", "21931", "21932",
    "21936", "21937", "22108", "22109", "22478", "22583", "22735",
    "22793", "23002", "23165", "23166", "23191", "23192", "23193",
    "23194", "23195", "23443", "23444", "23447", "23470", "23630",
    "23694", "23695", "23867", "23869", "23870", "23871", "24066",
    "24738", "24739", "25252", "29413", "29478", "29479", "29480",
    "29481", "29792", "29793", "29794", "29817", "30283", "30284",
    "30285", "30286", "30287", "30381", "30581", "30582", "36138",
    "36975", "37760", "38568", "38709", "38710", "38711", "39047",
    "39050", "39051", "39052", "39427", "39431", "39432", "39433",
    "39434", "39435", "39560", "39576", "39640", "39641", "39871",
    "39929", "40294", "40764", "40765", "40766", "40781", "40782",
    "40783", "41788", "41789", "41790", "41791", "42251", "42389",
    "42430", "42578", "42756", "42757", "42758", "42851",
}


def logicpower_page(page_num):
    params = urllib.parse.urlencode({
        "pageSize": PAGE_SIZE,
        "pageNum": page_num,
    })
    request = urllib.request.Request(
        f"{LOGICPOWER_URL}?{params}",
        headers={
            "X-Api-Key": LOGICPOWER_API_KEY,
            "Accept": "application/json",
            "User-Agent": "DragonElectro-LogicPower-Prom-Sync/3.0",
        },
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        payload = json.loads(response.read().decode("utf-8"))

    if not payload.get("status") or payload.get("code") != 200:
        raise RuntimeError(f"LogicPower API error: {payload}")
    return payload.get("data", {})


def recommended_retail(item):
    for price in item.get("prices", []):
        if price.get("type") != "recommendedRetail":
            continue
        money = price.get("money") or {}
        if money.get("currency") != "UAH":
            continue
        amount = money.get("amount")
        if amount is None:
            continue
        try:
            value = Decimal(str(amount))
        except InvalidOperation:
            continue
        if value > 0:
            return value
    return None


def dragon_price(rrp):
    """Apply markup to Logic Power recommended retail price.

    RRP < 2500 UAH:       +25%
    2500 <= RRP <= 4000: +15%
    RRP > 4000 UAH:       +10%
    """
    if rrp < Decimal("2500"):
        multiplier = Decimal("1.25")
    elif rrp <= Decimal("4000"):
        multiplier = Decimal("1.15")
    else:
        multiplier = Decimal("1.10")

    # Whole hryvnias only; conventional arithmetic rounding (.50 goes up).
    return (rrp * multiplier).quantize(
        Decimal("1"),
        rounding=ROUND_HALF_UP,
    )


def json_price(value):
    if value is None:
        return None
    return int(value) if value == value.to_integral_value() else float(value)


def prom_update(external_id, price, presence):
    body = {
        "id": external_id,
        "presence": presence,
    }
    if price is not None:
        body["price"] = json_price(price)

    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    last_error = None

    for attempt in range(1, MAX_PROM_ATTEMPTS + 1):
        request = urllib.request.Request(
            PROM_EDIT_URL,
            data=data,
            headers={
                "Authorization": f"Bearer {PROM_API_TOKEN}",
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "DragonElectro-LogicPower-Prom-Sync/3.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                text = response.read().decode("utf-8")
                result = json.loads(text) if text else {}
                return response.status, result
        except urllib.error.HTTPError as exc:
            error_text = exc.read().decode("utf-8", errors="replace")
            last_error = f"HTTP {exc.code}: {error_text}"
            if exc.code == 429 or 500 <= exc.code <= 599:
                if attempt < MAX_PROM_ATTEMPTS:
                    time.sleep(2 ** attempt)
                    continue
            raise RuntimeError(last_error) from exc
        except Exception as exc:
            last_error = repr(exc)
            if attempt < MAX_PROM_ATTEMPTS:
                time.sleep(2 ** attempt)
                continue

    raise RuntimeError(last_error or "Unknown Prom API error")


def main():
    if FORCE_ALL_NOT_AVAILABLE:
        print("EMERGENCY PAUSE: forcing all LogicPower products not_available")
        print(f"Tracked products: {len(TRACKED_CODES)}")

        updated = 0
        errors = []

        for index, code in enumerate(sorted(TRACKED_CODES, key=int), start=1):
            external_id = f"LP-{code}"
            try:
                http_status, _ = prom_update(
                    external_id=external_id,
                    price=None,
                    presence="not_available",
                )
                updated += 1
                print(
                    f"[{index:03d}/{len(TRACKED_CODES)}] {external_id} | "
                    f"Prom=not_available | PriceSent=- | HTTP {http_status}"
                )
            except Exception as exc:
                errors.append((external_id, str(exc)))
                print(
                    f"[{index:03d}/{len(TRACKED_CODES)}] "
                    f"ERROR {external_id}: {exc}"
                )

            time.sleep(REQUEST_DELAY_SECONDS)

        print("\n========================================")
        print(f"Updated products: {updated}/{len(TRACKED_CODES)}")
        print("Prom available: 0")
        print(f"Prom not_available: {updated}")
        print(f"Errors: {len(errors)}")
        print("========================================")

        if errors:
            print("\nERROR DETAILS:")
            for external_id, error in errors:
                print(f"{external_id}: {error}")
            raise SystemExit(1)

        print("\nPAUSE SYNC: OK")
        return

    found = {}
    page_num = 1
    total_items = 0

    print(f"Tracked products: {len(TRACKED_CODES)}")
    print("Reading LogicPower catalog...")

    while True:
        data = logicpower_page(page_num)
        items = data.get("items", [])
        total_items = int(data.get("totalItems", 0) or 0)

        for item in items:
            code = str(item.get("code", ""))
            if code in TRACKED_CODES:
                found[code] = item

        print(
            f"LogicPower page {page_num}: {len(items)} items, "
            f"tracked found {len(found)}/{len(TRACKED_CODES)}"
        )

        if len(found) == len(TRACKED_CODES):
            break
        if not items:
            break
        if total_items and page_num * PAGE_SIZE >= total_items:
            break
        page_num += 1

    # Guard against an incomplete/broken supplier response causing a mass
    # out-of-stock update. Individual missing products are still disabled.
    minimum_expected = int(len(TRACKED_CODES) * 0.80)
    if len(found) < minimum_expected:
        raise RuntimeError(
            "Safety stop: LogicPower returned only "
            f"{len(found)}/{len(TRACKED_CODES)} tracked products"
        )

    missing = sorted(TRACKED_CODES - set(found), key=int)
    print(f"LogicPower tracked products found: {len(found)}/{len(TRACKED_CODES)}")
    if missing:
        print("Missing from LogicPower catalog:", ", ".join(missing))

    updated = 0
    available_count = 0
    not_available_count = 0
    errors = []

    for index, code in enumerate(sorted(TRACKED_CODES, key=int), start=1):
        item = found.get(code)
        external_id = f"LP-{code}"

        if item is None:
            lp_status = "missing"
            presence = "not_available"
            rrp = None
            price = None
        else:
            lp_status = str(item.get("status", ""))
            presence = "available" if lp_status == "inStock" else "not_available"
            rrp = recommended_retail(item)
            price = dragon_price(rrp) if rrp is not None else None

        if presence == "available":
            available_count += 1
        else:
            not_available_count += 1

        try:
            http_status, _ = prom_update(
                external_id=external_id,
                price=price,
                presence=presence,
            )
            updated += 1
            print(
                f"[{index:03d}/{len(TRACKED_CODES)}] {external_id} | "
                f"LogicPower={lp_status} | RRP={rrp or '-'} | "
                f"PriceSent={price or '-'} | Prom={presence} | "
                f"HTTP {http_status}"
            )
        except Exception as exc:
            errors.append((external_id, str(exc)))
            print(
                f"[{index:03d}/{len(TRACKED_CODES)}] "
                f"ERROR {external_id}: {exc}"
            )

        time.sleep(REQUEST_DELAY_SECONDS)

    print("\n========================================")
    print(f"Updated products: {updated}/{len(TRACKED_CODES)}")
    print(f"Prom available: {available_count}")
    print(f"Prom not_available: {not_available_count}")
    print(f"Errors: {len(errors)}")
    print("========================================")

    if errors:
        print("\nERROR DETAILS:")
        for external_id, error in errors:
            print(f"{external_id}: {error}")
        raise SystemExit(1)

    print("\nSYNC: OK")


if __name__ == "__main__":
    main()

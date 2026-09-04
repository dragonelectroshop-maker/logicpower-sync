#!/usr/bin/env python3

import os
import json
import time
import urllib.parse
import urllib.request
import urllib.error


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


# ============================================================
# 170 ТОВАРОВ
# ============================================================

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
            "User-Agent": "DragonElectro-LogicPower-Prom-Sync/2.0",
        },
        method="GET",
    )

    with urllib.request.urlopen(
        request,
        timeout=120
    ) as response:

        payload = json.loads(
            response.read().decode("utf-8")
        )

    if (
        not payload.get("status")
        or payload.get("code") != 200
    ):
        raise RuntimeError(
            f"LogicPower API error: {payload}"
        )

    return payload.get("data", {})


def recommended_retail_minus_one(item):
    for price in item.get("prices", []):

        if price.get("type") != "recommendedRetail":
            continue

        money = price.get("money") or {}

        if money.get("currency") != "UAH":
            continue

        amount = money.get("amount")

        if amount is None:
            continue

        return round(
            float(amount) - 1.0,
            2
        )

    return None


def prom_update(
    external_id,
    price,
    presence
):

    body = {
        "id": external_id,
        "presence": presence,
    }

    if price is not None:
        body["price"] = price

    data = json.dumps(
        body,
        ensure_ascii=False
    ).encode("utf-8")

    last_error = None

    for attempt in range(1, 4):

        request = urllib.request.Request(
            PROM_EDIT_URL,
            data=data,
            headers={
                "Authorization": (
                    f"Bearer {PROM_API_TOKEN}"
                ),
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": (
                    "DragonElectro-LogicPower-Prom-Sync/2.0"
                ),
            },
            method="POST",
        )

        try:

            with urllib.request.urlopen(
                request,
                timeout=60
            ) as response:

                text = (
                    response
                    .read()
                    .decode("utf-8")
                )

                result = (
                    json.loads(text)
                    if text
                    else {}
                )

                return (
                    response.status,
                    result
                )

        except urllib.error.HTTPError as exc:

            error_text = (
                exc.read()
                .decode(
                    "utf-8",
                    errors="replace"
                )
            )

            last_error = (
                f"HTTP {exc.code}: "
                f"{error_text}"
            )

            if (
                exc.code == 429
                or 500 <= exc.code <= 599
            ):
                time.sleep(
                    attempt * 2
                )
                continue

            raise RuntimeError(
                last_error
            ) from exc

        except Exception as exc:

            last_error = repr(exc)

            time.sleep(
                attempt * 2
            )

    raise RuntimeError(
        last_error
        or "Unknown Prom API error"
    )


# ============================================================
# ЧИТАЕМ КАТАЛОГ LOGICPOWER
# ============================================================

found = {}

page_num = 1
total_items = None

print(
    f"Tracked products: "
    f"{len(TRACKED_CODES)}"
)

print(
    "Reading LogicPower catalog..."
)


while True:

    data = logicpower_page(
        page_num
    )

    items = data.get(
        "items",
        []
    )

    total_items = int(
        data.get(
            "totalItems",
            0
        ) or 0
    )

    for item in items:

        code = str(
            item.get(
                "code",
                ""
            )
        )

        if code in TRACKED_CODES:
            found[code] = item

    print(
        f"LogicPower page "
        f"{page_num}: "
        f"{len(items)} items, "
        f"tracked found "
        f"{len(found)}/"
        f"{len(TRACKED_CODES)}"
    )

    if (
        len(found)
        == len(TRACKED_CODES)
    ):
        break

    if not items:
        break

    if (
        total_items
        and page_num * PAGE_SIZE
        >= total_items
    ):
        break

    page_num += 1


missing = sorted(
    TRACKED_CODES - set(found),
    key=int
)


print("")

print(
    "LogicPower tracked products found: "
    f"{len(found)}/"
    f"{len(TRACKED_CODES)}"
)


if missing:

    print(
        "Missing from LogicPower catalog:",
        ", ".join(missing)
    )


# ============================================================
# ОБНОВЛЯЕМ PROM
# ============================================================

updated = 0

available_count = 0
not_available_count = 0

errors = []


for index, code in enumerate(
    sorted(
        TRACKED_CODES,
        key=int
    ),
    start=1
):

    item = found.get(code)

    external_id = (
        f"LP-{code}"
    )


    if item is None:

        lp_status = "missing"

        presence = (
            "not_available"
        )

        price = None

    else:

        lp_status = str(
            item.get(
                "status",
                ""
            )
        )

        presence = (
            "available"
            if lp_status == "inStock"
            else "not_available"
        )

        price = (
            recommended_retail_minus_one(
                item
            )
        )


    if presence == "available":
        available_count += 1
    else:
        not_available_count += 1


    try:

        http_status, result = (
            prom_update(
                external_id=external_id,
                price=price,
                presence=presence,
            )
        )

        updated += 1

        price_text = (
            "-"
            if price is None
            else str(price)
        )

        print(
            f"[{index:03d}/"
            f"{len(TRACKED_CODES)}] "
            f"{external_id} | "
            f"LogicPower={lp_status} | "
            f"price={price_text} | "
            f"Prom={presence} | "
            f"HTTP {http_status}"
        )


    except Exception as exc:

        errors.append(
            (
                external_id,
                str(exc)
            )
        )

        print(
            f"[{index:03d}/"
            f"{len(TRACKED_CODES)}] "
            f"ERROR "
            f"{external_id}: "
            f"{exc}"
        )


    time.sleep(0.10)


# ============================================================
# ОТЧЕТ
# ============================================================

print("")

print(
    "========================================"
)

print(
    f"Updated products: "
    f"{updated}/"
    f"{len(TRACKED_CODES)}"
)

print(
    f"Prom available: "
    f"{available_count}"
)

print(
    f"Prom not_available: "
    f"{not_available_count}"
)

print(
    f"Errors: "
    f"{len(errors)}"
)

print(
    "========================================"
)


if errors:

    print("")
    print("ERROR DETAILS:")

    for external_id, error in errors:

        print(
            f"{external_id}: "
            f"{error}"
        )

    raise SystemExit(1)


print("")
print("SYNC: OK")

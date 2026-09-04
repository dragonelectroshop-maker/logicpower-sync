#!/usr/bin/env python3

import os
import json
import math
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

PROM_GET_URL = (
    "https://my.prom.ua/api/v1/"
    "products/by_external_id"
)

PROM_EDIT_URL = (
    "https://my.prom.ua/api/v1/"
    "products/edit_by_external_id"
)


PAGE_SIZE = 500


# ============================================================
# ЗАЩИТА ЦЕН
# ============================================================

MIN_SAFE_PRICE = 1000.0

# Максимальное изменение цены за один цикл:
# +/- 50% относительно текущей цены Prom.
MAX_PRICE_CHANGE = 0.50


# ============================================================
# 170 ТОВАРОВ
# ============================================================

TRACKED_CODES = {
    "1078",
    "1079",
    "1212",
    "1213",
    "1454",
    "1456",
    "1879",
    "2436",
    "3170",
    "3172",
    "3173",
    "3336",
    "3404",
    "3405",
    "3643",
    "4147",
    "4976",
    "4978",
    "4980",
    "4981",
    "4986",
    "4990",
    "6615",
    "8295",
    "8648",
    "9323",
    "10003",
    "10358",
    "10397",
    "11382",
    "14190",
    "17934",
    "17935",
    "17936",
    "17938",
    "18013",
    "18818",
    "19239",
    "19241",
    "19339",
    "19474",
    "19577",
    "19578",
    "19729",
    "19744",
    "19745",
    "19746",
    "19747",
    "19748",
    "19749",
    "19750",
    "19751",
    "19752",
    "19753",
    "19761",
    "19762",
    "19953",
    "20054",
    "20055",
    "20120",
    "20121",
    "20123",
    "20125",
    "20140",
    "20141",
    "20150",
    "20151",
    "20152",
    "20153",
    "20166",
    "20524",
    "21031",
    "21339",
    "21379",
    "21927",
    "21928",
    "21929",
    "21930",
    "21931",
    "21932",
    "21936",
    "21937",
    "22108",
    "22109",
    "22478",
    "22583",
    "22735",
    "22793",
    "23002",
    "23165",
    "23166",
    "23191",
    "23192",
    "23193",
    "23194",
    "23195",
    "23443",
    "23444",
    "23447",
    "23470",
    "23630",
    "23694",
    "23695",
    "23867",
    "23869",
    "23870",
    "23871",
    "24066",
    "24738",
    "24739",
    "25252",
    "29413",
    "29478",
    "29479",
    "29480",
    "29481",
    "29792",
    "29793",
    "29794",
    "29817",
    "30283",
    "30284",
    "30285",
    "30286",
    "30287",
    "30381",
    "30581",
    "30582",
    "36138",
    "36975",
    "37760",
    "38568",
    "38709",
    "38710",
    "38711",
    "39047",
    "39050",
    "39051",
    "39052",
    "39427",
    "39431",
    "39432",
    "39433",
    "39434",
    "39435",
    "39560",
    "39576",
    "39640",
    "39641",
    "39871",
    "39929",
    "40294",
    "40764",
    "40765",
    "40766",
    "40781",
    "40782",
    "40783",
    "41788",
    "41789",
    "41790",
    "41791",
    "42251",
    "42389",
    "42430",
    "42578",
    "42756",
    "42757",
    "42758",
    "42851",
}


# ============================================================
# HTTP
# ============================================================

def prom_headers():
    return {
        "Authorization": f"Bearer {PROM_API_TOKEN}",
        "Accept": "application/json",
        "User-Agent": (
            "DragonElectro-LogicPower-Prom-Sync/4.0"
        ),
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
            "User-Agent": (
                "DragonElectro-LogicPower-Prom-Sync/4.0"
            ),
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


# ============================================================
# РРЦ - 1 ГРН
# ============================================================

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

        try:
            amount = float(amount)
        except (TypeError, ValueError):
            return None

        if not math.isfinite(amount):
            return None

        return round(
            amount - 1.0,
            2
        )

    return None


# ============================================================
# ПОЛУЧАЕМ ТОВАР ИЗ PROM
# ============================================================

def prom_get_product(external_id):

    encoded_id = urllib.parse.quote(
        external_id,
        safe=""
    )

    url = (
        f"{PROM_GET_URL}/"
        f"{encoded_id}"
    )

    last_error = None

    for attempt in range(1, 4):

        request = urllib.request.Request(
            url,
            headers=prom_headers(),
            method="GET",
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

                return (
                    json.loads(text)
                    if text
                    else {}
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
        or "Unknown Prom GET error"
    )


def extract_prom_price(payload):

    candidates = []

    if isinstance(payload, dict):

        candidates.append(payload)

        data = payload.get("data")

        if isinstance(data, dict):
            candidates.append(data)

        product = payload.get("product")

        if isinstance(product, dict):
            candidates.append(product)


    for obj in candidates:

        value = obj.get("price")

        if value is None:
            continue

        if isinstance(value, str):

            value = (
                value
                .replace(" ", "")
                .replace(",", ".")
            )

        try:
            value = float(value)

        except (
            TypeError,
            ValueError
        ):
            continue


        if (
            math.isfinite(value)
            and value > 0
        ):
            return value

    return None


# ============================================================
# ЗАЩИТА ЦЕНЫ
# ============================================================

def check_price(
    new_price,
    current_price
):

    if new_price is None:

        return (
            False,
            "LogicPower did not return "
            "recommendedRetail"
        )


    if not math.isfinite(
        float(new_price)
    ):

        return (
            False,
            "new price is not finite"
        )


    if new_price < MIN_SAFE_PRICE:

        return (
            False,
            f"new price {new_price} "
            f"is below {MIN_SAFE_PRICE}"
        )


    if current_price is None:

        return (
            False,
            "current Prom price "
            "could not be determined"
        )


    lower_limit = (
        current_price
        * (1.0 - MAX_PRICE_CHANGE)
    )

    upper_limit = (
        current_price
        * (1.0 + MAX_PRICE_CHANGE)
    )


    if new_price < lower_limit:

        percent = round(
            (
                1
                - new_price / current_price
            )
            * 100,
            1
        )

        return (
            False,
            f"price drop {percent}%: "
            f"{current_price} -> "
            f"{new_price}"
        )


    if new_price > upper_limit:

        percent = round(
            (
                new_price / current_price
                - 1
            )
            * 100,
            1
        )

        return (
            False,
            f"price increase {percent}%: "
            f"{current_price} -> "
            f"{new_price}"
        )


    return True, "OK"


# ============================================================
# ОБНОВЛЕНИЕ PROM
# ============================================================

def prom_update(
    external_id,
    price,
    presence,
    quantity_in_stock
):

    body = {
        "id": external_id,

        # Статус наличия.
        "presence": presence,

        # КЛЮЧЕВОЕ ИЗМЕНЕНИЕ.
        #
        # LogicPower inStock -> 1
        # LogicPower не в наличии -> 0
        #
        # Реального количества поставщик
        # нам не сообщает, поэтому ничего
        # выдумывать не будем.
        "quantity_in_stock": quantity_in_stock,
    }


    # Если защита цены её пропустила,
    # отправляем цену.
    #
    # Если цена заблокирована —
    # вообще не передаём поле price.
    if price is not None:
        body["price"] = price


    data = json.dumps(
        body,
        ensure_ascii=False
    ).encode("utf-8")


    last_error = None


    for attempt in range(1, 4):

        headers = prom_headers()

        headers[
            "Content-Type"
        ] = "application/json"


        request = urllib.request.Request(
            PROM_EDIT_URL,
            data=data,
            headers=headers,
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

            found[
                code
            ] = item


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
    "LogicPower tracked "
    "products found: "
    f"{len(found)}/"
    f"{len(TRACKED_CODES)}"
)


if missing:

    print(
        "Missing from LogicPower:",
        ", ".join(missing)
    )


# ============================================================
# СИНХРОНИЗАЦИЯ
# ============================================================

updated = 0

available_count = 0

not_available_count = 0

price_updated_count = 0

price_protected_count = 0

errors = []

price_warnings = []


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


    # ========================================================
    # НАЛИЧИЕ + ОСТАТОК
    # ========================================================

    if item is None:

        lp_status = "missing"

        presence = (
            "not_available"
        )

        quantity_in_stock = 0

        proposed_price = None


    else:

        lp_status = str(
            item.get(
                "status",
                ""
            )
        )


        if lp_status == "inStock":

            presence = (
                "available"
            )

            # Поставщик подтверждает наличие,
            # но не сообщает точный остаток.
            quantity_in_stock = 1

        else:

            presence = (
                "not_available"
            )

            quantity_in_stock = 0


        proposed_price = (
            recommended_retail_minus_one(
                item
            )
        )


    if presence == "available":

        available_count += 1

    else:

        not_available_count += 1


    # ========================================================
    # ПРОВЕРКА ЦЕНЫ
    # ========================================================

    safe_price = None

    current_price = None

    price_status = (
        "not checked"
    )


    if item is not None:

        try:

            prom_product = (
                prom_get_product(
                    external_id
                )
            )


            current_price = (
                extract_prom_price(
                    prom_product
                )
            )


            allowed, reason = (
                check_price(
                    proposed_price,
                    current_price
                )
            )


            if allowed:

                safe_price = (
                    proposed_price
                )

                price_updated_count += 1

                price_status = "OK"


            else:

                price_protected_count += 1

                price_status = (
                    f"BLOCKED: {reason}"
                )


                warning = (
                    f"{external_id}: "
                    f"{reason}"
                )


                price_warnings.append(
                    warning
                )


                print(
                    "::warning title="
                    "PRICE ANOMALY::"
                    + warning
                )


        except Exception as exc:

            # Если проверка цены не удалась,
            # цену не трогаем.
            #
            # Наличие и остаток при этом
            # всё равно обновляем.
            price_protected_count += 1


            price_status = (
                "BLOCKED: "
                f"Prom price check failed: "
                f"{exc}"
            )


            warning = (
                f"{external_id}: "
                f"Prom price check failed: "
                f"{exc}"
            )


            price_warnings.append(
                warning
            )


            print(
                "::warning title="
                "PRICE CHECK FAILED::"
                + warning
            )


    # ========================================================
    # ОТПРАВЛЯЕМ В PROM
    # ========================================================

    try:

        http_status, result = (
            prom_update(
                external_id=external_id,
                price=safe_price,
                presence=presence,
                quantity_in_stock=quantity_in_stock,
            )
        )


        updated += 1


        current_text = (
            "-"
            if current_price is None
            else str(
                round(
                    current_price,
                    2
                )
            )
        )


        proposed_text = (
            "-"
            if proposed_price is None
            else str(
                proposed_price
            )
        )


        sent_text = (
            "UNCHANGED"
            if safe_price is None
            else str(
                safe_price
            )
        )


        print(
            f"[{index:03d}/"
            f"{len(TRACKED_CODES)}] "
            f"{external_id} | "
            f"LogicPower={lp_status} | "
            f"PromOld={current_text} | "
            f"RRP-1={proposed_text} | "
            f"PriceSent={sent_text} | "
            f"StockSent={quantity_in_stock} | "
            f"{price_status} | "
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


    time.sleep(0.15)


# ============================================================
# ИТОГ
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
    f"Prices updated: "
    f"{price_updated_count}"
)


print(
    f"Prices protected: "
    f"{price_protected_count}"
)


print(
    f"Price warnings: "
    f"{len(price_warnings)}"
)


print(
    f"Errors: "
    f"{len(errors)}"
)


print(
    "========================================"
)


if price_warnings:

    print("")

    print(
        "PRICE PROTECTION DETAILS:"
    )

    for warning in price_warnings:

        print(
            warning
        )


if errors:

    print("")

    print(
        "ERROR DETAILS:"
    )

    for external_id, error in errors:

        print(
            f"{external_id}: "
            f"{error}"
        )

    raise SystemExit(1)


print("")

print(
    "SYNC: OK"
)

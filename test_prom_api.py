import os
import json
import urllib.request

token = os.environ.get("PROM_API_TOKEN")

if not token:
    raise SystemExit("PROM_API_TOKEN is not set")

external_id = "LP-40765"

url = f"https://my.prom.ua/api/v1/products/by_external_id/{external_id}"

request = urllib.request.Request(
    url,
    headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    },
    method="GET",
)

with urllib.request.urlopen(request, timeout=30) as response:
    data = json.loads(response.read().decode("utf-8"))

print("PROM PRODUCT LOOKUP: OK")
print("HTTP STATUS: 200")
print(json.dumps(data, ensure_ascii=False, indent=2))

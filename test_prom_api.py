import os
import json
import urllib.request

token = os.environ.get("PROM_API_TOKEN")

if not token:
    raise SystemExit("PROM_API_TOKEN is not set")

url = "https://my.prom.ua/api/v1/products/list?limit=1"

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

print("PROM API CONNECTION: OK")
print("HTTP STATUS: 200")

if isinstance(data, dict):
    print("Response fields:", ", ".join(data.keys()))

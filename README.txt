LogicPower -> DragonElectro SYNC (12 test products)

1. The script fetches LogicPower B2B API.
2. Finds the 12 test product codes.
3. Price = recommendedRetail - 1 UAH.
4. status=inStock -> available=true + in_stock=true.
5. Missing API code remains in feed as available=false.
6. GitHub Actions regenerates the public YML hourly.

SECRET:
Create GitHub Actions secret named LOGICPOWER_API_KEY.
Never put the API key into the Python file.

PROM SETTINGS FOR THIS SYNC LINK:
CHECK: Цена, Наличие
DO NOT CHECK: names, descriptions, keywords, article, photo, quantity, group,
characteristics, discounts, personal notes, GTIN, MPN.
General: "Только обновление" ON.
"Обновить принудительно" OFF for normal operation.
Absent products: "Оставить без изменений".
Automatic link update: "Раз в 4 часа".

Public URL after Pages deployment:
https://YOUR_GITHUB_USERNAME.github.io/YOUR_REPOSITORY/logicpower-sync.yml

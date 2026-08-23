import requests, json

API_KEY = "rnd_wyivsCOxDi2njuzPGBjjA3In7ZeY"
H = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
SVC = "srv-da51frbbc2fs73fhaek0"

env_vars = {
    "BINANCE_API_KEY": "HIWvdNXyUmkDjGIqVujwkGEklkfztETmXLWIiJpOCjV80GjITFo9fvy8MEnFu5vB",
    "BINANCE_SECRET_KEY": "L3BGUtqUUFACQ7R3eFv1e8YO6FmAHBD5makaNt3MUnq1vnvtdQolf7v4YAcyPeFJ",
    "BITGET_API_KEY": "bg_f6e6e91c270bae5dada159f64fc2eb18",
    "BITGET_SECRET_KEY": "95da49454e3beb531955df67477d184d4c8b2f313a54966e9c6ce55ec3bd103a",
    "BITGET_PASSPHRASE": "",
}

for key, value in env_vars.items():
    url = f"https://api.render.com/v1/services/{SVC}/env-vars/{key}"
    r = requests.put(url, headers=H, json={"value": value}, timeout=30)
    status = "OK" if r.status_code in (200, 201) else f"ERRO {r.status_code}"
    print(f"{key}: {status}")

print("\nDONE!")

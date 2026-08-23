import requests, json

API_KEY = "rnd_wyivsCOxDi2njuzPGBjjA3In7ZeY"
H = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

r = requests.get("https://api.render.com/v1/services?limit=5", headers=H, timeout=30)
print(json.dumps(r.json(), indent=2)[:3000])

import re
import urllib.request

url = "https://www.tunismapper.com/itineraire.php?startLat=36.8151533&startLng=10.0568158&endLat=36.8585478&endLng=10.1682756&startName=Tborba&endName=Cite+Ennasr+1"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", errors="replace")

# Search for routeData or itinerary API in script blocks
blocks = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
for b in blocks:
    if "routeData" in b:
        rd_idx = b.find("routeData")
        if rd_idx >= 0:
            print("routeData context:")
            print(b[max(0, rd_idx - 200):rd_idx + 800])
        break

# Search for any PHP endpoint references
php_urls = re.findall(r"[\w/\.]+\.php", html)
for u in set(php_urls):
    print("php:", u)

# Search for itinerary-specific endpoints
for kw in ["itineraire", "calc", "route", "plan", "getItineraire", "routing", "itinerary"]:
    idx = html.lower().find(kw)
    if idx >= 0:
        print(kw, "at", idx, ":", html[max(0, idx - 60):idx + 150])

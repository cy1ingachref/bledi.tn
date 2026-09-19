import re
import urllib.request

url = "https://www.tunismapper.com/itineraire.php"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
html = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", errors="replace")

# Find ALL fetch calls in the entire page
all_fetches = re.findall(r"fetch\s*\(\s*[\"']([^\"']+)[\"']+", html)
for f in all_fetches:
    print(f"fetch: {f}")

# Also look for any URL patterns with 'route' or 'itineraire' or 'calculate'
all_urls = re.findall(r"[\"']([^\"']*(?:route|itineraire|calculate|plan|direction)[^\"']*)[\"']+", html, re.IGNORECASE)
for u in set(all_urls):
    print(f"url: {u}")

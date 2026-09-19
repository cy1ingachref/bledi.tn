import re
import urllib.request

url = "https://www.tunismapper.com/itineraire.php"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
html = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", errors="replace")

# Find all script blocks
script_blocks = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
for i, block in enumerate(script_blocks):
    if any(kw in block.lower() for kw in ["station", "ligne", "bus", "horaire", "schedule", "departure", "lat", "lon"]):
        print(f"--- Script block {i} ({len(block)} chars) ---")
        print(block[:500])
        print()

# Look for JSON objects (not arrays)
json_obj = re.search(r"var\s+\w+\s*=\s*(\{.*?\});", html, re.DOTALL)
if json_obj:
    print(f"Found JSON object: {json_obj.group(1)[:300]}")

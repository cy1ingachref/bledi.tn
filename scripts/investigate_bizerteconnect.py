#!/usr/bin/env python3
"""Investigate BizerteConnect data structure and find all bus lines."""
import urllib.request, re, json, sys

BASE = "https://www.bizerteconnect.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")

def main():
    print("=== BIZERTECONNECT INVESTIGATION ===\n")

    # Fetch homepage
    try:
        html = fetch(BASE)
        print(f"Homepage: {len(html)} bytes")
    except Exception as e:
        print(f"Homepage ERROR: {e}")
        return

    # Look for line/schedule endpoints
    patterns = [
        r'href=["\']([^"\']*(?:horaires|schedules|ligne|bus)[^"\']*)["\']',
        r'action=["\']([^"\']*(?:horaires|schedules|ligne)[^"\']*)["\']',
        r'url\s*[:=]\s*["\']([^"\']*(?:api|json|data)[^"\']*)["\']',
        r'(?:fetch|axios|get)\s*\(\s*["\']([^"\']+)["\']',
    ]

    found_urls = set()
    for pattern in patterns:
        matches = re.findall(pattern, html, re.IGNORECASE)
        found_urls.update(matches)

    print(f"Found {len(found_urls)} URL-like strings:")
    for u in sorted(found_urls):
        if "/" in u and not u.startswith("#"):
            print(f"  {u}")

    # Look for JavaScript that might have all data inline
    script_blocks = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
    print(f"\nJavaScript blocks: {len(script_blocks)}")

    # Search for arrays of lines or JSON-like data
    for i, block in enumerate(script_blocks):
        # Look for bus line data patterns
        if any(kw in block.lower() for kw in ["ligne", "bus", "line", "schedule", "horaires"]):
            print(f"\n--- JS block {i} ({len(block)} chars) has transport keywords ---")
            # Try to find line data
            line_matches = re.findall(r'\{[^{}]*(?:"id"|"name"|"departure"|"arrival")[^{}]*\}', block)
            if line_matches:
                for m in line_matches[:5]:
                    print(f"  {m[:200]}")
            # line number patterns
            nums = re.findall(r'(?:ligne|line)[\s#]?(\d{1,3})', block, re.IGNORECASE)
            if nums:
                print(f"  Line numbers found: {nums[:20]}")

    # Check for embedded JSON data
    json_matches = re.findall(r'\{[^{}]{50,}(?:bus|line|schedule)[^{}]{0,200}\}', html, re.IGNORECASE | re.DOTALL)
    if json_matches:
        print(f"\n=== Embedded JSON-like data ({len(json_matches)} blocks) ===")
        for jm in json_matches[:3]:
            print(f"  {jm[:300]}")

    # Check for page source with line data
    lines = re.findall(r'(?:n°|num|numéro|line|ligne|#)?\s*(\d{1,3})\s*[:\-–]\s*([A-Za-zÀ-ÿ\s\-\(\)]+(?:Tunis|Bizerte|Sousse|Sfax|Gabès|Nabeul|Hammamet|Monastir|Kairouan|Béja|Jendouba|Le Kef|Gafsa|Sidi|Kasserine|Nefta|Tozeur|Douz|Jerba|Djerba|Tabarka|Mateur|Ras|Jbel|Zarzis|Medenine|Gabes))', html, re.IGNORECASE)
    if lines:
        print(f"\n=== Line-Number -> City patterns ===")
        for ln in lines[:30]:
            print(f"  {ln}")

    print("\n=== SAVING homepage HTML for analysis ===")
    with open("scripts/bizerteconnect_home.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("Saved -> scripts/bizerteconnect_home.html")

if __name__ == "__main__":
    main()

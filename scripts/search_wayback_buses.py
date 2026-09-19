#!/usr/bin/env python3
"""Search Wayback Machine CDX API for Tunisia bus operator URLs."""
import urllib.request, json, urllib.parse

def cdx_query(url_pattern, limit=100, collapse="urlkey"):
    params = f"url={urllib.parse.quote(url_pattern)}&output=json&limit={limit}&collapse={collapse}"
    api = "https://web.archive.org/cdx/search/cdx?" + params
    req = urllib.request.Request(api, headers={"User-Agent": "bledi.tn-research/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    return data

print("=== TRANSTU (transtu.com.tn) ===")
try:
    data = cdx_query("transtu.com.tn/*", limit=200)
    if len(data) > 1:
        urls = sorted({row[2] for row in data[1:]})
        print(f"Found {len(urls)} unique archived URLs")
        for u in urls[:40]:
            print(f"  {u}")
    else:
        print("  No snapshots found")
except Exception as e:
    print(f"  ERROR: {e}")

print("\n=== TRANSTU (transtu.tn) ===")
try:
    data = cdx_query("transtu.tn/*", limit=200)
    if len(data) > 1:
        urls = sorted({row[2] for row in data[1:]})
        print(f"Found {len(urls)} unique archived URLs")
        for u in urls[:40]:
            print(f"  {u}")
    else:
        print("  No snapshots found")
except Exception as e:
    print(f"  ERROR: {e}")

# Also check other likely domains
for domain in ["sitrastn.com", "setrag.com", "sntri.com", "ctm.com.tn", "transtu.org", "bus-tunisie.com", "tunisie-transport.com"]:
    print(f"\n=== {domain} ===")
    try:
        data = cdx_query(f"{domain}/*", limit=50)
        if len(data) > 1:
            urls = sorted({row[2] for row in data[1:]})
            print(f"  Found {len(urls)} URLs")
            for u in urls[:10]:
                print(f"    {u}")
        else:
            print("  No snapshots found")
    except Exception as e:
        print(f"  ERROR: {e}")

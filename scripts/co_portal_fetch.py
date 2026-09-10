"""Fetch the co.agentrouter.org portal from a datacenter IP and extract
information about the service: title, signup/console links, pricing hints."""
import re
import urllib.request

r = urllib.request.Request("https://co.agentrouter.org", headers={"User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(r, timeout=60) as resp:
    html = resp.read().decode("utf-8", "replace")

print("length:", len(html))
title = re.search(r"<title[^>]*>(.*?)</title>", html, re.S)
print("title:", title.group(1).strip() if title else "?")

# links
links = sorted(set(re.findall(r'href="([^"]+)"', html)))
print("\nlinks:")
for link in links[:40]:
    print("  ", link)

# visible text (rough)
text = re.sub(r"<script.*?</script>", " ", html, flags=re.S)
text = re.sub(r"<style.*?</style>", " ", text, flags=re.S)
text = re.sub(r"<[^>]+>", " ", text)
text = re.sub(r"\s+", " ", text)
print("\nvisible text (first 1500 chars):")
print(text[:1500])

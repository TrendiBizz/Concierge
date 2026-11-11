#!/usr/bin/env python3
"""Submit the sitemap to IndexNow (Bing, Yandex, Seznam). Also pings ChatGPT's
Bing-backed index. The key file is public and must stay at the site root:
  https://trendibizz.com/<KEY>.txt  (contents: KEY)
"""
import json
import urllib.request
import xml.etree.ElementTree as ET

KEY = "3a226d049abaa3f61aeeb0b3f9a6c6b9"
HOST = "trendibizz.com"
SITEMAP = f"https://{HOST}/sitemap.xml"


def main() -> None:
    root = ET.fromstring(urllib.request.urlopen(SITEMAP, timeout=20).read())
    urls = [node.text.strip() for node in root.iter() if node.tag.endswith("loc") and node.text]
    body = json.dumps({
        "host": HOST,
        "key": KEY,
        "keyLocation": f"https://{HOST}/{KEY}.txt",
        "urlList": urls[:100],
    }).encode()
    request = urllib.request.Request(
        "https://api.indexnow.org/indexnow", data=body,
        headers={"Content-Type": "application/json; charset=utf-8"})
    with urllib.request.urlopen(request, timeout=30) as response:
        print(response.status, len(urls), "urls submitted")


if __name__ == "__main__":
    main()

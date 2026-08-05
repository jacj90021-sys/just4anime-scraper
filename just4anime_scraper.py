#!/usr/bin/env python3
"""
just4anime.scraper  --  resolve playable streams from just4anime.online

HONEST STATUS (verified 2026-08, see notes below):
  kai, zeke  -> resolve from their OWN embed hosts (vivibebe.site / vibevibe.workers.dev).
                 These are real CDN m3u8s, NO Cloudflare proxy, work server-side. RELIABLE.
  jin        -> backed by megaplay; just4anime's proxy is Cloudflare-locked (403 server-side)
                 and megaplay uses its OWN id-space (not anilist) -> wrong-anime if guessed.
                 NOT reliably scrapable from a server.
  sai, mai   -> backed by otakuhg.site, Cloudflare-locked proxy + obfuscated client JS.
                 Browser-only. NOT scrapable.
  ryuk       -> animegg.org direct MP4, but the URL returns 302/Error (dead upstream).
                 NOT available.
  echo       -> just4anime encrypted proxy ("Invalid URL after decoding"). NOT scrapable.

So the scraper ONLY returns kai + zeke (all their sub/dub/hsub variants). The app shows
a clean "not available on this source" for the others instead of a broken/wrong stream.

We learned the hard way: just4anime wraps everything in cors.just4anime.online/proxy/e/<token>
(Cloudflare). That proxy intermittently 403s server-side, so we avoid it entirely and use
the real embed hosts for kai/zeke.

Usage:
  python3 just4anime_scraper.py <anilistId> <episode> [server] [type]
  -> prints JSON list of {server,type,url,referer,format,isM3U8}
"""

import sys
import json
import re
import urllib.request

API = "https://api.just4anime.online/api"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

# Only servers we can reliably resolve without just4anime's CF proxy.
SERVER_TYPES = {
    "kai":  ["sub", "hsub", "dub"],
    "zeke": ["sub", "hsub", "dub"],
}


def _get(url, referer=None, ajax=False):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    if referer:
        req.add_header("Referer", referer)
    if ajax:
        req.add_header("X-Requested-With", "XMLHttpRequest")
        req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "ignore")


def _api_sources(anilist_id, episode, server, typ):
    url = (f"{API}/v1/meta/sources/{anilist_id}?provider={server}"
           f"&num={episode}&type={typ}")
    try:
        d = json.loads(_get(url, ajax=True))
    except Exception:
        return None
    if not d.get("success"):
        return None
    return d["data"]


def _embed_m3u8(iframe_url):
    """Fetch the embed player page and pull the literal m3u8 from its JS.
    Returns (m3u8_url, referer) or (None, None)."""
    try:
        page = _get(iframe_url, referer=iframe_url)
    except Exception:
        return None, None
    m = re.search(r'(https?://[^\s"\']+?\.m3u8[^\s"\']*)', page)
    if not m:
        return None, None
    u = m.group(1)
    try:
        head = _get(u, referer=iframe_url)
    except Exception:
        return None, None
    if head.strip().startswith("#EXTM3U"):
        host = re.search(r"https?://([^/]+)", iframe_url).group(1)
        return u, "https://" + host
    return None, None


def resolve(anilist_id, episode, server=None, typ=None):
    results = []
    servers = [server] if server else list(SERVER_TYPES.keys())
    for srv in servers:
        types = [typ] if typ else SERVER_TYPES.get(srv, [])
        for t in types:
            data = _api_sources(anilist_id, episode, srv, t)
            if not data:
                continue
            iframes = data.get("iframe") or []
            if not iframes:
                continue
            url, referer = _embed_m3u8(iframes[0]["url"])
            if not url:
                continue
            subs = []
            for sub in data.get("subtitles") or []:
                fu = sub.get("url")
                if fu:
                    subs.append({"file": fu, "label": sub.get("lang") or "English"})
            results.append({
                "server": srv,
                "type": t,
                "url": url,
                "referer": referer,
                "format": "hls",
                "isM3U8": True,
                "subtitles": subs,
            })
    return results


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    aid = sys.argv[1]
    ep = sys.argv[2]
    srv = sys.argv[3] if len(sys.argv) > 3 else None
    tp = sys.argv[4] if len(sys.argv) > 4 else None
    print(json.dumps(resolve(aid, ep, srv, tp), indent=2))

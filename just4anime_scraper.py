#!/usr/bin/env python3
"""
just4anime.scraper  --  resolve real m3u8/mp4 streams from just4anime.online

VERIFIED WORKING METHODS (reverse-engineered + tested 2026-08 against
https://just4anime.online/watch/159309 ):

  jin   -> megaplay backend. API: https://api.just4anime.online/api/v1/meta/sources/<anilistId>?provider=jin&num=<ep>&type=<sub|dub>
         Real m3u8 via megaplay getSources: https://megaplay.buzz/stream/getSources?id=<anilistId>&h=0&m=0&type=<sub|dub>
         (sub -> megap.akirax.buzz ; dub -> megap.shiora.top). Referer: https://megaplay.buzz/

  kai   -> vivibebe.site embed. iframe url in API response (data.iframe[0].url) holds the
         player page; the real m3u8 is a literal string in that page's JS:
         https://vivibebe.site/public/stream/<id>/master.m3u8 . Referer: https://vivibebe.site/

  zeke  -> bibiemb.xyz embed (sub/hsub) -> https://<*.vibevibe.workers.dev>/<id>/master.m3u8
         zeke/dub routes to kai's vivibebe stream (same URL as kai). Referer: host of url.

  sai   -> dub routes to kai's vivibebe stream. sai/SUB is otakuhg.site (obfuscated, browser-only -> not scraped).
  mai   -> dub routes to kai's vivibebe stream. mai/SUB is otakuhg.site (obfuscated, browser-only -> not scraped).

  ryuk  -> animegg.org direct MP4. API returns the mp4 url directly in sources[0].url.
         Referer: https://animegg.org/

  echo  -> just4anime encrypted Cloudflare proxy (cors.just4anime.online/proxy/e/...).
           "Invalid URL after decoding" -> client-side only. NOT scraped.

So the SCRAPED servers are: jin (sub+dub), kai (sub+dub+hsub), zeke (sub+dub+hsub),
sai (dub), mai (dub), ryuk (sub+dub+hsub). sai/mai-SUB and echo are intentionally omitted.

Each server's types are taken from the site's own server config:
  jin:["sub","dub"], kai:["sub","h-sub","dub","embed"], zeke:["sub","h-sub","dub","embed"],
  sai:["sub","h-sub","dub","embed"], mai:["sub","h-sub","dub","embed"], ryuk:["h-sub"],
  echo:["h-sub"]  (echo omitted - not scrapable)

Usage:
  python3 just4anime_scraper.py <anilistId> <episode> [server] [type]
  -> prints JSON list of {server,type,url,referer,format,isM3U8}
"""

import sys
import json
import re
import urllib.request
import urllib.error

API = "https://api.just4anime.online/api"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

# Server -> available types (from site config). echo omitted (not scrapable).
SERVER_TYPES = {
    "jin":  ["sub", "dub"],
    "kai":  ["sub", "hsub", "dub"],
    "zeke": ["sub", "hsub", "dub"],
    "sai":  ["dub"],            # sub is otakuhg (browser-only)
    "mai":  ["dub"],            # sub is otakuhg (browser-only)
    "ryuk": ["sub", "dub", "hsub"],
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
    raw = _get(url, ajax=True)
    d = json.loads(raw)
    if not d.get("success"):
        return None
    return d["data"]


def _megaplay_real(anilist_id, typ):
    """jin backend. Returns real m3u8 or None."""
    mt = "hsub" if typ == "hsub" else typ
    url = f"https://megaplay.buzz/stream/getSources?id={anilist_id}&h=0&m=0&type={mt}"
    try:
        d = json.loads(_get(url, referer="https://megaplay.buzz/", ajax=True))
        return d["sources"]["file"]
    except Exception:
        return None


def _embed_m3u8(iframe_url):
    """Fetch the embed player page and pull the literal m3u8 from its JS."""
    try:
        page = _get(iframe_url, referer=iframe_url)
    except Exception:
        return None
    m = re.search(r'(https?://[^\s"\']+?\.m3u8[^\s"\']*)', page)
    if not m:
        return None
    u = m.group(1)
    # confirm it is a playlist, not an HTML page served at that path
    try:
        head = _get(u, referer=iframe_url)
    except Exception:
        return None
    return u if head.strip().startswith("#EXTM3U") else None


def resolve(anilist_id, episode, server=None, typ=None):
    """Return list of stream dicts. If server/type given, only that; else all."""
    results = []
    servers = [server] if server else list(SERVER_TYPES.keys())
    for srv in servers:
        types = [typ] if typ else SERVER_TYPES.get(srv, [])
        for t in types:
            url = referer = None
            fmt = "hls"
            is_m3u8 = True
            try:
                if srv == "jin":
                    url = _megaplay_real(anilist_id, t)
                    referer = "https://megaplay.buzz/"
                elif srv == "ryuk":
                    data = _api_sources(anilist_id, episode, srv, t)
                    if data:
                        url = data["sources"][0]["url"]
                        referer = "https://animegg.org/"
                        fmt = "mp4"
                        is_m3u8 = False
                else:  # kai, zeke, sai, mai
                    data = _api_sources(anilist_id, episode, srv, t)
                    if not data:
                        continue
                    iframes = data.get("iframe") or []
                    if iframes:
                        url = _embed_m3u8(iframes[0]["url"])
                        referer = "https://" + re.search(r"https?://([^/]+)",
                                                          iframes[0]["url"]).group(1)
                    else:
                        # fallback: ryuk-style direct url (shouldn't happen here)
                        url = data["sources"][0]["url"]
                        referer = "https://just4anime.online/"
            except Exception:
                continue
            if not url:
                continue
            results.append({
                "server": srv,
                "type": t,
                "url": url,
                "referer": referer,
                "format": fmt,
                "isM3U8": is_m3u8,
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
    out = resolve(aid, ep, srv, tp)
    print(json.dumps(out, indent=2))

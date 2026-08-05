#!/usr/bin/env python3
"""
just4anime.scraper  --  resolve playable streams from just4anime.online

RELIABLE SERVERS (verified 2026-08):
  kai, zeke  -> resolve from their OWN embed hosts (vivibebe.site / vibevibe.workers.dev).
                Real CDN m3u8s, NO Cloudflare proxy. RELIABLE. All sub/dub/hsub.
  jin        -> just4anime's own cors proxy (megaplay-backed). Returns 200 + valid HLS
                WITH the correct anime/ep (just4anime resolves megaplay's id server-side,
                so we DO NOT re-resolve via megaplay with the anilist id — that produced a
                WRONG-ANIME bug). The only risk is Cloudflare intermittently 403ing the
                proxy from a server; when it 200s it's the exact right stream.
  ryuk       -> just4anime's own animegg URL (302 -> real video/mp4). We follow the
                redirect. Correct ep (just4anime's own resolution). MP4.

NOT AVAILABLE server-side (browser-only / dead):
  sai, mai   -> otakuhg.site, Cloudflare-locked + obfuscated client JS. Browser-only.
  echo       -> just4anime encrypted proxy ("Invalid URL after decoding"). Browser-only.

So we return kai, zeke, jin, ryuk. For kai/zeke we use the real embed m3u8 (no proxy).
For jin/ryuk we return just4anime's own resolved url + the referer it requires.

Usage:
  python3 just4anime_scraper.py <anilistId> <episode> [server] [type]
  -> prints JSON list of {server,type,url,referer,format,isM3U8,subtitles}
"""

import sys
import json
import re
import urllib.request

API = "https://api.just4anime.online/api"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

# Servers we can resolve. kai/zeke from their own embeds; jin from just4anime's
# own resolved proxy url (correct anime/ep, no guessed IDs).
# ryuk DROPPED: just4anime's ryuk->animegg mapping is mislabeled upstream
# (e.g. Black Clover ep1 returns the "Your Name" movie). Plays, but wrong anime.
SERVER_TYPES = {
    "kai":  ["sub", "hsub", "dub"],
    "zeke": ["sub", "hsub", "dub"],
    "jin":  ["sub", "dub"],
}


def _get(url, referer=None, ajax=False, follow=True):
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
    """kai/zeke: pull the literal m3u8 from the embed player page JS."""
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
            # kai/zeke: resolve from their own embed
            if srv in ("kai", "zeke"):
                iframes = data.get("iframe") or []
                if not iframes:
                    continue
                url, referer = _embed_m3u8(iframes[0]["url"])
                if not url:
                    continue
                fmt, is_m = "hls", True
            else:
                # jin/ryuk: use just4anime's OWN resolved url + referer (correct anime/ep)
                srcs = data.get("sources") or []
                if not srcs:
                    continue
                s = srcs[0]
                url = s.get("url")
                if not url:
                    continue
                hdrs = s.get("headers") or {}
                referer = hdrs.get("referer") or hdrs.get("Referer")
                # ryuk's animegg MP4 REQUIRES Referer: https://animegg.org/ or it 500s
                # on the redirect. The API omits headers for ryuk, so hardcode it.
                if srv == "ryuk" and referer is None:
                    referer = "https://animegg.org/"
                is_m = bool(s.get("isM3U8", True)) or url.endswith(".m3u8")
                fmt = "mp4" if not is_m else "hls"
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
                "format": fmt,
                "isM3U8": is_m,
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

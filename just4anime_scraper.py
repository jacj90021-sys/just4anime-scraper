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
  ryuk       -> resolved OURSELVES from animegg.org (just4anime's own animegg mapping
                is mislabeled for some shows). We pick the correct typed mirror (sub/dub).
                MP4, Referer https://animegg.org/.

  sai, mai   -> otakuhg.site obfuscated jwplayer. The iframe runs a packed eval() that
                resolves the real m3u8 (served as master.txt on a random *.site/*.space CDN).
                We extract the packed script and run it via node to recover the URL.
                Referer https://otakuhg.site/. WORKS server-side (needs node).

NOT AVAILABLE server-side (browser-only / dead):
  echo       -> just4anime encrypted proxy ("Invalid URL after decoding"). Browser-only.

So we return kai, zeke, jin, ryuk, sai, mai.
For jin/ryuk we return just4anime's own resolved url + the referer it requires.

Usage:
  python3 just4anime_scraper.py <anilistId> <episode> [server] [type]
  -> prints JSON list of {server,type,url,referer,format,isM3U8,subtitles}
"""

import sys
import json
import re
import os
import subprocess
import urllib.request

API = "https://api.just4anime.online/api"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

# Servers we can resolve. kai/zeke from their own embeds; jin from just4anime's
# own resolved proxy url (correct anime/ep, no guessed IDs).
# ryuk: resolved OURSELVES from animegg.org (just4anime's ryuk mapping is
# mislabeled upstream for some shows -> wrong anime). See _ryuk_real().
# sai/mai: otakuhg.site obfuscated jwplayer -> decoded via node. See _otakuhg_m3u8().
SERVER_TYPES = {
    "kai":  ["sub", "hsub", "dub"],
    "zeke": ["sub", "hsub", "dub"],
    "jin":  ["sub", "dub"],
    "ryuk": ["sub", "dub", "hsub"],
    "sai":  ["sub", "dub"],
    "mai":  ["sub", "dub"],
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


# ---------------------------------------------------------------------------
# sai/mai: otakuhg.site obfuscated jwplayer. The iframe page runs a packed
# eval() that resolves the real m3u8 (served as master.txt on a random
# *.site/*.space CDN). We extract the packed script and run it via node to
# recover the stream URL. Referer must be https://otakuhg.site/.
# ---------------------------------------------------------------------------
import shutil

def _otakuhg_m3u8(iframe_url):
    """Return (m3u8_url, referer) for an otakuhg iframe, or (None, None)."""
    referer = "https://otakuhg.site/"
    try:
        page = _get(iframe_url, referer=referer)
    except Exception:
        return None, None
    i = page.find("eval(function(p,a,c,k,e,d){")
    if i < 0:
        return None, None
    # Extract balanced-paren eval block
    j, depth, instr = i + 4, 0, None
    while j < len(page):
        ch = page[j]
        if instr:
            if ch == "\\":
                j += 2
                continue
            if ch == instr:
                instr = None
            j += 1
            continue
        if ch in ('"', "'"):
            instr = ch
            j += 1
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                block = page[i:j + 1]
                break
        j += 1
    else:
        return None, None
    node = shutil.which("node")
    if not node:
        return None, None
    try:
        tf = "/tmp/otakuhg_%s.js" % abs(hash(iframe_url))
        with open(tf, "w") as f:
            f.write(block)
        r = subprocess.run([node, os.path.join(os.path.dirname(__file__),
                                                "otakuhg_decode.js"), tf],
                           capture_output=True, text=True, timeout=25)
        for line in r.stdout.splitlines():
            if line.startswith("SETUP_FILE:"):
                url = line[len("SETUP_FILE:"):]
                if url and url != "NONE":
                    return url, referer
    except Exception:
        pass
    return None, None


# ---------------------------------------------------------------------------
# ryuk: just4anime's own ryuk->animegg mapping is MISLABELED upstream for some
# shows (e.g. Black Clover ep1 -> "Your Name" movie). So we resolve ryuk OURSELVES
# straight from animegg.org using its correct slug-based episode pages:
#   series slug -> /<slug>-episode-<N> -> /embed/<id> -> /play/<id>/video.mp4
# We prefer just4anime's episode.id slug (it's already animegg's romaji format and
# correct for most shows); if that's corrupt or fails, fall back to the anime title.
# ---------------------------------------------------------------------------
def _animegg_slug_from_title(title):
    """best-effort english-title -> animegg slug (lowercase, hyphenated)."""
    if not title:
        return None
    s = title.lower()
    s = re.sub(r"[^a-z0-9\s\-]", "", s)
    s = re.sub(r"\s+", "-", s.strip())
    return s or None


def _ryuk_real(anilist_id, episode, just4_id_slug, title, typ="sub"):
    """Return (mp4_url, referer) for the CORRECT animegg episode + type, or (None, None).

    animegg episode pages expose separate mirrors per type via tabs:
      data-version="raw"    -> RAW
      data-version="subbed" -> SUB
      data-version="dubbed" -> DUB
    We pick the embed whose data-version matches the requested typ, so ryuk/sub
    and ryuk/dub return the correct mirror (not a random/untyped one).
    """
    referer = "https://animegg.org/"
    want = {"sub": "subbed", "dub": "dubbed", "raw": "raw",
            "hsub": "subbed"}.get(typ, "subbed")
    # Build candidate series slugs (prefer just4anime's slug, then title-based).
    candidates = []
    if just4_id_slug:
        base = re.split(r"(?:-episode-|\$ep-|\\-ep\d|/ep)", just4_id_slug)[0]
        base = base.strip("-$").strip()
        if base and "your-name" not in base and "kimi-no-na-wa" not in base:
            candidates.append(base)
    tslug = _animegg_slug_from_title(title)
    if tslug:
        # Prefer the "-tv" slug FIRST: it carries the typed raw/sub/dub mirror tabs.
        # Base slug often only has a single untyped embed, so try -tv before it.
        candidates += [tslug + "-tv", tslug, tslug + "-dub", re.sub(r"[:.]", "", tslug)]
    seen, ordered = set(), []
    for c in candidates:
        if c and c not in seen:
            seen.add(c)
            ordered.append(c)
    for slug in ordered:
        try:
            page = _get(f"https://www.animegg.org/{slug}-episode-{episode}",
                        referer=referer)
        except Exception:
            continue
        # Collect every mirror tab: data-id + data-version.
        mirrors = re.findall(
            r'data-id=[\'"](\d+)[\'"]\s+data-mirror=[\'"][^\'"]*[\'"]\s+data-version=[\'"]([^\'"]+)[\'"]',
            page)
        if not mirrors:
            m = re.search(r"/embed/(\d+)", page)
            if m:
                mirrors = [(m.group(1), "subbed")]
            else:
                continue
        # Prefer the mirror matching the requested type.
        chosen = next((e for e, v in mirrors if v == want), None)
        if chosen is None:
            # This slug had typed tabs but none matched our type (e.g. no dub) ->
            # keep looking at other slugs rather than returning a wrong-type mirror.
            if len(mirrors) > 1:
                continue
            chosen = mirrors[0][0]
        try:
            emb = _get(f"https://www.animegg.org/embed/{chosen}", referer=referer)
        except Exception:
            continue
        mp = re.search(r"/play/(\d+)/video\.mp4\?for=(\d+)", emb)
        if mp:
            url = f"https://www.animegg.org/play/{mp.group(1)}/video.mp4?for={mp.group(2)}"
            return url, referer
    return None, None


def resolve(anilist_id, episode, server=None, typ=None, title=None):
    results = []
    servers = [server] if server else list(SERVER_TYPES.keys())
    for srv in servers:
        types = [typ] if typ else SERVER_TYPES.get(srv, [])
        for t in types:
            data = _api_sources(anilist_id, episode, srv, t) if srv != "ryuk" else None
            if srv != "ryuk" and not data:
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
            elif srv == "jin":
                # jin: use just4anime's OWN resolved url + referer (correct anime/ep)
                srcs = (data or {}).get("sources") or []
                if not srcs:
                    continue
                s = srcs[0]
                url = s.get("url")
                if not url:
                    continue
                hdrs = s.get("headers") or {}
                referer = hdrs.get("referer") or hdrs.get("Referer")
                is_m = bool(s.get("isM3U8", True)) or url.endswith(".m3u8")
                fmt = "mp4" if not is_m else "hls"
            elif srv in ("sai", "mai"):
                # otakuhg.site obfuscated jwplayer -> decode via node.
                iframes = (data or {}).get("iframe") or []
                if not iframes:
                    continue
                url, referer = _otakuhg_m3u8(iframes[0]["url"])
                if not url:
                    continue
                is_m = url.endswith(".m3u8") or "master" in url or ".txt" in url
                fmt = "hls" if is_m else "mp4"
            else:
                # ryuk: resolve OURSELVES from animegg (just4anime's ryuk is
                # mislabeled/unavailable for many shows). Use just4anime's
                # episode.id slug if present + the anime title as fallback.
                # typ selects the correct mirror (sub/dub/raw).
                j4_slug = (data.get("episode") or {}).get("id") if data else None
                url, referer = _ryuk_real(anilist_id, episode, j4_slug, title, typ)
                if not url:
                    continue
                fmt, is_m = "mp4", False
            subs = []
            for sub in (data.get("subtitles") if data else []) or []:
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

#!/usr/bin/env python3
"""just4anime-scraper - Flask web API around just4anime_scraper.py.

Mirrors the anikage-scraper backend contract so the Android app can call both
the same way:

  GET /api/anime/<anilistId>/servers?ep=<N>
      -> { "servers": [ {"server":..,"name":..,"types":[..]} ], ... }
         (plus embeds if any; just4anime has none, so only "servers")

  GET /api/anime/<anilistId>/stream?ep=<N>&server=<srv>&type=<sub|dub|hsub>
      -> { "server", "type", "url", "referer", "format", "isM3U8",
           "subtitles": [ {"file":..,"label":..} ], "error":.. }

Subtitles: just4anime returns them in the /sources response (data.subtitles).
We forward the .vtt URLs. Several hosts (cdn.anizara.store, 1oe.lostproject.club)
403 direct device fetches, so like anikage we rewrite them through /api/proxy.
"""

from flask import Flask, jsonify, request, Response
import urllib.request
import json as _json

from just4anime_scraper import (
    resolve, SERVER_TYPES, API as J4A_API, UA, _api_sources,
)

app = Flask(__name__)


def _proxy_sub(url):
    if not url:
        return url
    low = url.lower()
    if any(low.endswith(e) for e in (".vtt", ".ass", ".srt", ".ssa", ".ttml")):
        from urllib.parse import urlencode
        return "/api/proxy?" + urlencode({"url": url})
    return url


def _get(url, referer=None, ajax=False):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    if referer:
        req.add_header("Referer", referer)
    if ajax:
        req.add_header("X-Requested-With", "XMLHttpRequest")
        req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "ignore")


@app.get("/api/health")
def health():
    return jsonify({"ok": True})


@app.get("/api/anime/<anilist_id>/servers")
def servers(anilist_id):
    ep = request.args.get("ep", "1")
    out = []
    for srv, types in SERVER_TYPES.items():
        out.append({
            "server": srv,
            "name": srv.capitalize(),
            "types": types,
        })
    return jsonify({"servers": out, "episode": ep})


@app.get("/api/anime/<anilist_id>/stream")
def stream(anilist_id):
    ep = request.args.get("ep", "1")
    server = request.args.get("server")
    typ = request.args.get("type", "sub")
    if not server:
        return jsonify({"error": "missing 'server'"}), 400
    try:
        # Get the stream url via the scraper
        results = resolve(anilist_id, ep, server, typ)
        if not results:
            return jsonify({"error": f"no stream for {server}/{typ} ep{ep}"}), 404
        r = results[0]
        # Attach subtitles from the just4anime /sources response
        subs = []
        try:
            data = _api_sources(anilist_id, ep, server, typ)
            if data:
                for s in data.get("subtitles", []):
                    f = s.get("url")
                    if f:
                        subs.append({
                            "file": _proxy_sub(f),
                            "label": s.get("lang") or s.get("language") or "Unknown",
                        })
        except Exception:
            pass
        return jsonify({
            "server": r["server"],
            "type": r["type"],
            "url": r["url"],
            "referer": r["referer"],
            "format": r["format"],
            "isM3U8": r["isM3U8"],
            "subtitles": subs,
            "episode": ep,
            "anilistId": anilist_id,
        })
    except Exception as ex:
        return jsonify({"error": str(ex)}), 502


@app.get("/api/proxy")
def proxy():
    """Same-origin subtitle proxy (mirrors anikage backend)."""
    target = request.args.get("url")
    if not target or not target.startswith("http"):
        return jsonify({"error": "missing url"}), 400
    try:
        req = urllib.request.Request(
            target,
            headers={
                "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                               "AppleWebKit/537.36 (KHTML, like Gecko) "
                               "Chrome/124.0.0.0 Safari/537.36"),
                "Referer": "https://megaplay.buzz/",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
        return Response(data, mimetype="text/vtt")
    except Exception as ex:
        return jsonify({"error": str(ex)}), 502


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000)

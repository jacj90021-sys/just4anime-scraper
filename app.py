#!/usr/bin/env python3
"""just4anime-scraper - Flask web API.

Contract (mirrors anikage-scraper so the Android client reuses its shape):
  GET /api/anime/<anilistId>/servers?ep=<N>
  GET /api/anime/<anilistId>/stream?ep=<N>&server=<srv>&type=<sub|dub|hsub>
  GET /api/proxy?url=<vtt>   -> same-origin subtitle proxy (text/vtt)

Only kai + zeke are returned (see just4anime_scraper.py for why jin/sai/mai/ryuk/echo
are not reliably scrapable from a server). Their URLs are REAL CDN m3u8s (vivibebe.site,
vibevibe.workers.dev) with a Referer the device must send. The Android app attaches the
referer via PlayerModule.buildAnikageMediaSource (same as anikage).
"""

import os
import urllib.parse
import urllib.request
from flask import Flask, jsonify, request, Response

from just4anime_scraper import resolve, SERVER_TYPES, UA

app = Flask(__name__)


def _get(url, referer=None, as_text=True):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    if referer:
        req.add_header("Referer", referer)
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read()
    return data.decode("utf-8", "ignore") if as_text else data


@app.get("/api/health")
def health():
    return jsonify({"ok": True})


@app.get("/api/anime/<anilist_id>/servers")
def servers(anilist_id):
    ep = request.args.get("ep", "1")
    out = [{"server": s, "name": s.capitalize(), "types": t}
           for s, t in SERVER_TYPES.items()]
    return jsonify({"servers": out, "episode": ep})


@app.get("/api/anime/<anilist_id>/stream")
def stream(anilist_id):
    ep = request.args.get("ep", "1")
    server = request.args.get("server")
    typ = request.args.get("type", "sub")
    if not server:
        return jsonify({"error": "missing 'server'"}), 400
    title = request.args.get("title", "")
    try:
        results = resolve(anilist_id, ep, server, typ, title=title)
        if not results:
            return jsonify({"error": f"no stream for {server}/{typ} ep{ep} "
                                    f"(source not available on just4anime)"}), 404
        r = results[0]
        subs = [{
            "file": "/api/proxy?" + urllib.parse.urlencode({"url": s["file"]}),
            "label": s["label"],
        } for s in r.get("subtitles", [])]
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
    """Same-origin subtitle proxy (vtt/ass/srt)."""
    target = request.args.get("url")
    if not target or not target.startswith("http"):
        return jsonify({"error": "missing url"}), 400
    try:
        req = urllib.request.Request(
            target, headers={"User-Agent": UA, "Referer": "https://just4anime.online/"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
        return Response(data, mimetype="text/vtt")
    except Exception as ex:
        return jsonify({"error": str(ex)}), 502


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "3000"))
    app.run(host="0.0.0.0", port=port)

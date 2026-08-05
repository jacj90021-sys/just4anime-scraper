# just4anime-scraper

Reverse-engineered scraper + Flask API for **just4anime.online** anime streams.
Returns the **real, playable m3u8 / mp4** (not just4anime's locked CORS proxy) plus
the required `Referer` and subtitles — so an Android ExoPlayer app can play them.

## Verified working servers

| Server | Types | Real source | Referer |
|--------|-------|-------------|---------|
| `jin`  | sub, dub | megaplay (`megap.akirax.buzz` / `megap.shiora.top`) | `https://megaplay.buzz/` |
| `kai`  | sub, dub, hsub | vivibebe.site embed | `https://vivibebe.site/` |
| `zeke` | sub, dub, hsub | bibiemb.xyz / vibevibe workers | host of url |
| `sai`  | dub | routes to kai's vivibebe stream | `https://vivibebe.site/` |
| `mai`  | dub | routes to kai's vivibebe stream | `https://vivibebe.site/` |
| `ryuk` | sub, dub, hsub | animegg.org direct MP4 | `https://animegg.org/` |

**Not statically scrapable** (client-side decryption, like anikage's anizone.to player):
`sai`/ `mai` **sub** (otakuhg.site obfuscated) and `echo` (all, just4anime Cloudflare proxy).

## Flask API (mirrors anikage-scraper contract)

```
GET /api/anime/<anilistId>/servers?ep=<N>
   -> { "servers": [ {"server","name","types":[...]} ] }

GET /api/anime/<anilistId>/stream?ep=<N>&server=<srv>&type=<sub|dub|hsub>
   -> { "url","referer","format","isM3U8","subtitles":[{"file","label"}], ... }

GET /api/proxy?url=<vtt>     (same-origin subtitle proxy, text/vtt)
```

## Run

```bash
pip install -r requirements.txt
python3 app.py            # listens on :3000

# CLI
python3 just4anime_scraper.py <anilistId> <ep> [server] [type]
```

## Deploy (Render / similar)

Point a web service at this repo; the app listens on `$PORT` (or 3000). Add the
anime route to your Android app's backend list alongside anikage-scraper.

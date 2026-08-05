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
| `sai`  | sub, dub | otakuhg.site (jwplayer, decoded via node) | `https://otakuhg.site/` |
| `mai`  | sub, dub | otakuhg.site (jwplayer, decoded via node) | `https://otakuhg.site/` |
| `ryuk` | sub, dub, hsub | resolved from animegg.org (correct typed mirror) | `https://animegg.org/` |

`echo` is the only server we cannot resolve (just4anime's encrypted Cloudflare proxy, browser-only).

## How sai/mai work (otakuhg.site)

otakuhg serves an obfuscated, packed jwplayer script. The iframe page
(`otakuhg.site/e/<id>`) contains an `eval(function(p,a,c,k,e,d){...})` packer that
resolves the **real m3u8** (served as `master.txt` on a random `*.site`/`*.space` CDN).
We extract that packed script and run it with **node** (`otakuhg_decode.js`) to recover
the URL. Node must be installed on the host (`shutil.which("node")`).

## Flask API (mirrors anikage-scraper contract)

```
GET /api/anime/<anilistId>/servers?ep=<N>
   -> { "servers": [ {"server","name","types":[...]} ] }

GET /api/anime/<anilistId>/stream?ep=<N>&server=<srv>&type=<sub|dub|hsub>&title=<anime title>
   -> { "url","referer","format","isM3U8","subtitles":[{"file","label"}], ... }

GET /api/proxy?url=<vtt>     (same-origin subtitle proxy, text/vtt)
```

The `title` query param is used by ryuk to build the correct animegg slug.

## Run

```bash
pip install -r requirements.txt
python3 app.py            # listens on $PORT (or 3000)

# CLI
python3 just4anime_scraper.py <anilistId> <ep> [server] [type]
```

Requires `node` on PATH (for sai/mai decoding).

## Deploy (Render / similar)

Point a web service at this repo; the app listens on `$PORT` (or 3000).
Render's Python runtime includes node. Add the anime route to your Android app's
backend list alongside anikage-scraper.

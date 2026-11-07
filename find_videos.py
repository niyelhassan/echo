"""List YouTube search results that have human-made English captions (for scoring accuracy).

Usage: uv run --no-project --with yt-dlp python find_videos.py "query" ...
"""
import sys
from concurrent.futures import ThreadPoolExecutor
import yt_dlp

FLAT = {'quiet': True, 'extract_flat': True, 'no_warnings': True}
FULL = {'quiet': True, 'no_warnings': True, 'skip_download': True, 'remote_components': ['ejs:github']}


def check(item):
    video, query = item
    try:
        with yt_dlp.YoutubeDL(FULL) as y:
            info = y.extract_info(video, download=False)
    except Exception:
        return None
    subs = [k for k in (info.get('subtitles') or {}) if k.startswith('en')]
    if subs and info.get('duration', 0) < 600:
        return f"{video} {info['duration']}s {subs} {info['title'][:80]} | {query}"


with yt_dlp.YoutubeDL(FLAT) as y:
    items = [(e['id'], q) for q in sys.argv[1:] for e in y.extract_info(f'ytsearch5:{q}', download=False)['entries']]
with ThreadPoolExecutor(8) as pool:
    for line in pool.map(check, items):
        if line: print(line, flush=True)

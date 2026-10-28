"""Bot de notificação de vídeos do YouTube para o Discord.

Lê o feed RSS público de cada canal e envia um embed via webhook do Discord
quando aparece um vídeo novo. Não precisa de chave de API do YouTube.
"""
import json
import os
import time
import xml.etree.ElementTree as ET

import requests
from dotenv import load_dotenv

load_dotenv()

WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]
CHANNEL_IDS = [c.strip() for c in os.environ["YT_CHANNEL_IDS"].split(",") if c.strip()]
INTERVAL = int(os.getenv("CHECK_INTERVAL", "300"))  # segundos
MENTION = os.getenv("DISCORD_MENTION", "")  # ex: @everyone ou <@&ID_DO_CARGO>
STATE_FILE = "seen.json"

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
}


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def fetch_videos(channel_id):
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    videos = []
    for entry in root.findall("atom:entry", NS):
        video_id = entry.find("yt:videoId", NS).text
        thumb = entry.find("media:group/media:thumbnail", NS)
        videos.append(
            {
                "id": video_id,
                "title": entry.find("atom:title", NS).text,
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "author": entry.find("atom:author/atom:name", NS).text,
                "published": entry.find("atom:published", NS).text,
                "thumbnail": thumb.get("url") if thumb is not None else None,
            }
        )
    return videos  # o feed vem do mais novo para o mais antigo


def notify(video):
    embed = {
        "title": video["title"],
        "url": video["url"],
        "description": f"**{video['author']}** postou um vídeo novo!",
        "color": 0xFF0000,
        "timestamp": video["published"],
    }
    if video["thumbnail"]:
        embed["image"] = {"url": video["thumbnail"]}
    payload = {
        "content": f"{MENTION} {video['url']}".strip(),
        "embeds": [embed],
    }
    resp = requests.post(WEBHOOK_URL, json=payload, timeout=15)
    resp.raise_for_status()


def check_channel(channel_id, state):
    videos = fetch_videos(channel_id)
    seen = set(state.get(channel_id, []))
    first_run = channel_id not in state

    # Na primeira execução só registra os vídeos atuais, sem spammar o canal.
    if not first_run:
        for video in reversed(videos):  # do mais antigo para o mais novo
            if video["id"] not in seen:
                notify(video)
                print(f"[novo] {video['author']}: {video['title']}")
                time.sleep(1)

    state[channel_id] = [v["id"] for v in videos] + [
        i for i in seen if i not in {v["id"] for v in videos}
    ][:50]


def run_once(state):
    for channel_id in CHANNEL_IDS:
        try:
            check_channel(channel_id, state)
        except Exception as e:
            print(f"[erro] canal {channel_id}: {e}")
    save_state(state)


def main():
    state = load_state()
    # RUN_ONCE=1 faz uma checagem só e encerra (usado no GitHub Actions)
    if os.getenv("RUN_ONCE") == "1":
        run_once(state)
        return
    print(f"Monitorando {len(CHANNEL_IDS)} canal(is), checando a cada {INTERVAL}s")
    while True:
        run_once(state)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()

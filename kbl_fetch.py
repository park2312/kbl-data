import json
import os
import sys
import urllib.request
from datetime import datetime

BASE = "https://api.kbl.or.kr"
HEADERS = {
    "accept": "application/json, text/plain, */*",
    "channel": "WEB",
    "lang": "ko",
    "teamcode": "XX",
    "x-requested-with": "XMLHttpRequest",
    "origin": "https://www.kbl.or.kr",
    "referer": "https://www.kbl.or.kr/",
    "user-agent": "Mozilla/5.0",
}

def get_json(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as res:
        return json.load(res)

def normalize_matches(raw):
    # KBL may return either:
    # 1) a JSON array of game objects, or
    # 2) one object whose fields are arrays.
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]

    if not isinstance(raw, dict):
        raise TypeError(f"Unexpected match-list JSON type: {type(raw).__name__}")

    gmkeys = raw.get("gmkey", [])
    if not isinstance(gmkeys, list):
        gmkeys = [gmkeys]

    games = []
    for i, gmkey in enumerate(gmkeys):
        def at(key, default=""):
            value = raw.get(key, default)
            if isinstance(value, list):
                return value[i] if i < len(value) else default
            return value
        games.append({
            "gmkey": gmkey,
            "tnameH": at("tnameH"),
            "tnameA": at("tnameA"),
            "gameStart": at("gameStart"),
            "gameDate": at("gameDate"),
        })
    return games

def main():
    date = os.environ.get("KBL_DATE") or (sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%Y%m%d"))
    raw = get_json(f"{BASE}/match/list?fromDate={date}&toDate={date}&tcodeList=all")
    games = normalize_matches(raw)

    folder = f"data/{date}"
    os.makedirs(folder, exist_ok=True)

    with open(f"{folder}/match-list.json", "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False, indent=2)

    index = []
    for game in games:
        gmkey = game.get("gmkey")
        if not gmkey:
            continue
        home = game.get("tnameH", "")
        away = game.get("tnameA", "")
        start = game.get("gameStart", "")

        stats = get_json(f"{BASE}/match/{gmkey}/player-stat?")
        out = f"{folder}/{gmkey}_player-stat.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)

        # Collect full play-by-play, quarter by quarter.
        text_cast_all = []
        text_cast_files = {}
        for quarter in ("Q1", "Q2", "Q3", "Q4"):
            text_cast = get_json(f"{BASE}/match/{gmkey}/text-cast?quarterList={quarter}")
            quarter_out = f"{folder}/{gmkey}_text-cast_{quarter}.json"
            with open(quarter_out, "w", encoding="utf-8") as f:
                json.dump(text_cast, f, ensure_ascii=False, indent=2)
            text_cast_files[quarter] = quarter_out
            text_cast_all.extend(text_cast)

        text_cast_out = f"{folder}/{gmkey}_text-cast.json"
        with open(text_cast_out, "w", encoding="utf-8") as f:
            json.dump(text_cast_all, f, ensure_ascii=False, indent=2)

        index.append({
            "gmkey": gmkey,
            "home": home,
            "away": away,
            "start": start,
            "player_stat_file": out,
            "text_cast_file": text_cast_out,
            "text_cast_quarter_files": text_cast_files,
        })
        print(f"{gmkey}: {home} vs {away} {start}")

    with open(f"{folder}/index.json", "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    print(f"Collected {len(index)} game(s) for {date}")

if __name__ == "__main__":
    main()

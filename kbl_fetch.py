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

def scalar_at(v, i):
    return v[i] if isinstance(v, list) else v

def main():
    date = os.environ.get("KBL_DATE") or (sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%Y%m%d"))
    url = f"{BASE}/match/list?fromDate={date}&toDate={date}&tcodeList=all"
    raw = get_json(url)
    gmkeys = raw.get("gmkey", [])
    if not isinstance(gmkeys, list):
        gmkeys = [gmkeys]
    os.makedirs(f"data/{date}", exist_ok=True)
    with open(f"data/{date}/match-list.json", "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False, indent=2)
    index = []
    for i, gmkey in enumerate(gmkeys):
        if not gmkey:
            continue
        home = scalar_at(raw.get("tnameH", ""), i)
        away = scalar_at(raw.get("tnameA", ""), i)
        start = scalar_at(raw.get("gameStart", ""), i)
        stats = get_json(f"{BASE}/match/{gmkey}/player-stat?")
        out = f"data/{date}/{gmkey}_player-stat.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
        index.append({"gmkey": gmkey, "home": home, "away": away, "start": start, "file": out})
        print(f"{gmkey}: {home} vs {away} {start}")
    with open(f"data/{date}/index.json", "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()

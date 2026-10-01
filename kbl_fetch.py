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

EVENT_NAMES = {
    "001": "게임시작",
    "003": "작전시간",
    "009": "게임종료",
    "101": "교체(IN)",
    "102": "교체(OUT)",
    "201": "2점슛성공",
    "202": "2점슛시도",
    "203": "자유투성공",
    "204": "자유투시도",
    "205": "3점슛성공",
    "206": "3점슛시도",
    "207": "덩크슛성공",
    "209": "공격리바운드",
    "210": "수비리바운드",
    "211": "어시스트",
    "212": "스틸",
    "213": "블록",
    "214": "턴오버",
    "215": "파울자유투",
    "216": "파울",
    "217": "UNKNOWN",
    "218": "팀리바운드",
    "221": "굿디펜스",
    "223": "팀턴오버",
    "224": "기타파울",
    "225": "팀파울",
    "226": "스크린 어시스트",
    "227": "디플렉션",
    "228": "UNKNOWN",
    "229": "코치챌린지",
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

        # Match chart includes shot locations (shootLog), leadTrack, scoreChart, bestPlayer, etc.
        match_chart = get_json(f"{BASE}/match/{gmkey}/match-chart?")
        match_chart_out = f"{folder}/{gmkey}_match-chart.json"
        with open(match_chart_out, "w", encoding="utf-8") as f:
            json.dump(match_chart, f, ensure_ascii=False, indent=2)

        # Flatten the official shootLog into one row per field-goal attempt.
        # d is retained raw; observed KBL charts use it to distinguish court/attack direction.
        shot_log = []
        for player in match_chart.get("shootLog", []):
            for shot_no, shot in enumerate(player.get("logs", []), start=1):
                shot_log.append({
                    "pcode": player.get("pcode"),
                    "pname": player.get("pname"),
                    "ename": player.get("ename"),
                    "tcode": player.get("tcode"),
                    "shot_no": shot_no,
                    "q": shot.get("q"),
                    "x": shot.get("x"),
                    "y": shot.get("y"),
                    "result": shot.get("o"),
                    "made": shot.get("o") == "O",
                    "direction": shot.get("d"),
                })

        shot_log_out = f"{folder}/{gmkey}_shot-log.json"
        with open(shot_log_out, "w", encoding="utf-8") as f:
            json.dump(shot_log, f, ensure_ascii=False, indent=2)

        # Collect full play-by-play, quarter by quarter.
        text_cast_all = []
        text_cast_files = {}
        for quarter in ("Q1", "Q2", "Q3", "Q4"):
            text_cast = get_json(f"{BASE}/match/{gmkey}/text-cast?quarterList={quarter}")
            quarter_out = f"{folder}/{gmkey}_text-cast_{quarter}.json"
            with open(quarter_out, "w", encoding="utf-8") as f:
                json.dump(text_cast, f, ensure_ascii=False, indent=2)
            text_cast_files[quarter] = quarter_out
            for event in text_cast:
                code = str(event.get("a", ""))
                event["event"] = EVENT_NAMES.get(code, "UNKNOWN")
            text_cast_all.extend(text_cast)

        # Join field-goal PBP events to shootLog in player/quarter order.
        # KBL shootLog does not include game clock, so the safest deterministic key
        # is player + quarter + chronological attempt order. Validate counts and
        # never silently force a match when the two official feeds disagree.
        fg_codes = {"201", "202", "205", "206", "207"}
        pbp_shots = {}
        for event in text_cast_all:
            code = str(event.get("a", ""))
            if code not in fg_codes:
                continue
            key = (str(event.get("t", "")), event.get("p") or event.get("e") or "", event.get("q"))
            pbp_shots.setdefault(key, []).append(event)

        chart_shots = {}
        for shot in shot_log:
            key = (str(shot.get("tcode", "")), shot.get("pname") or shot.get("ename") or "", shot.get("q"))
            chart_shots.setdefault(key, []).append(shot)

        merged_shots = []
        shot_merge_issues = []
        all_shot_keys = set(pbp_shots) | set(chart_shots)
        for key in sorted(all_shot_keys, key=lambda x: (x[2] or "", x[0], x[1])):
            events = pbp_shots.get(key, [])
            coords = chart_shots.get(key, [])
            if len(events) != len(coords):
                shot_merge_issues.append({
                    "tcode": key[0],
                    "pname": key[1],
                    "q": key[2],
                    "pbp_attempts": len(events),
                    "chart_attempts": len(coords),
                })
                continue

            for event, shot in zip(events, coords):
                code = str(event.get("a", ""))
                merged_shots.append({
                    "n": event.get("n"),
                    "q": event.get("q"),
                    "m": event.get("m"),
                    "s": event.get("s"),
                    "tcode": event.get("t"),
                    "pcode": shot.get("pcode"),
                    "pname": shot.get("pname"),
                    "ename": shot.get("ename"),
                    "event_code": code,
                    "event": EVENT_NAMES.get(code, "UNKNOWN"),
                    "shot_value": 3 if code in {"205", "206"} else 2,
                    "made": code in {"201", "205", "207"},
                    "x": shot.get("x"),
                    "y": shot.get("y"),
                    "direction": shot.get("direction"),
                })

        merged_shots_out = f"{folder}/{gmkey}_shots-merged.json"
        with open(merged_shots_out, "w", encoding="utf-8") as f:
            json.dump(merged_shots, f, ensure_ascii=False, indent=2)

        shot_merge_issues_out = f"{folder}/{gmkey}_shot-merge-issues.json"
        with open(shot_merge_issues_out, "w", encoding="utf-8") as f:
            json.dump(shot_merge_issues, f, ensure_ascii=False, indent=2)

        # Keep a compact report of any event codes we have not decoded yet.
        unknown_events = [event for event in text_cast_all if event.get("event") == "UNKNOWN"]
        unknown_out = f"{folder}/{gmkey}_unknown-events.json"
        with open(unknown_out, "w", encoding="utf-8") as f:
            json.dump(unknown_events, f, ensure_ascii=False, indent=2)

        text_cast_out = f"{folder}/{gmkey}_text-cast.json"
        with open(text_cast_out, "w", encoding="utf-8") as f:
            json.dump(text_cast_all, f, ensure_ascii=False, indent=2)

        index.append({
            "gmkey": gmkey,
            "home": home,
            "away": away,
            "start": start,
            "player_stat_file": out,
            "match_chart_file": match_chart_out,
            "shot_log_file": shot_log_out,
            "shot_attempt_count": len(shot_log),
            "merged_shots_file": merged_shots_out,
            "merged_shot_count": len(merged_shots),
            "shot_merge_issues_file": shot_merge_issues_out,
            "shot_merge_issue_count": len(shot_merge_issues),
            "text_cast_file": text_cast_out,
            "text_cast_quarter_files": text_cast_files,
            "unknown_events_file": unknown_out,
            "unknown_event_count": len(unknown_events),
        })
        print(f"{gmkey}: {home} vs {away} {start}")

    with open(f"{folder}/index.json", "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    print(f"Collected {len(index)} game(s) for {date}")

if __name__ == "__main__":
    main()

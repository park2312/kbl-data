# kbl-data

Official KBL game data collector.

## What it does

Run the **KBL Fetch** GitHub Action with a date in `YYYYMMDD` format.

The workflow:
1. Calls the official KBL match-list endpoint.
2. Finds every game and `gmkey` for that date.
3. Downloads official `player-stat` JSON for each game.
4. Saves the results under `data/YYYYMMDD/`.
5. Commits the collected data back to this repository.

Initial test date: **20260927** (includes KT vs Goyang Sono, `S49G14N9`).

#!/usr/bin/env python3
"""Generate assets/streak.svg from real GitHub contribution data.

No third-party dependencies (stdlib only) so this runs anywhere: locally
with `gh` on PATH, or in Actions with GITHUB_TOKEN. Re-run any time to
refresh the widget with current data - nothing here is hand-typed.
"""
import datetime
import json
import os
import subprocess
import sys
import urllib.request

USER = os.environ.get("STREAK_USER", "Svector-anu")

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        weeks { contributionDays { date contributionCount weekday } }
      }
    }
  }
}
"""


def fetch_days():
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        req = urllib.request.Request(
            "https://api.github.com/graphql",
            data=json.dumps({"query": QUERY, "variables": {"login": USER}}).encode(),
            headers={
                "Authorization": f"bearer {token}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.load(resp)
    else:
        # local fallback: shell out to the already-authenticated gh CLI
        out = subprocess.run(
            ["gh", "api", "graphql", "-f", f"query={QUERY}", "-F", f"login={USER}"],
            capture_output=True, text=True, check=True,
        )
        data = json.loads(out.stdout)

    weeks = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    days = [d for w in weeks for d in w["contributionDays"]]
    days.sort(key=lambda d: d["date"])
    return days


def current_streak(days):
    """Consecutive days with contributions, ending today or yesterday.

    Today counts as still-open (0 so far doesn't break the streak) so a
    streak doesn't visibly die every morning before the operator has had
    a chance to contribute.
    """
    today = datetime.date.today()
    by_date = {datetime.date.fromisoformat(d["date"]): d["contributionCount"] for d in days}
    streak = 0
    cursor = today
    if by_date.get(today, 0) == 0:
        cursor = today - datetime.timedelta(days=1)
    while by_date.get(cursor, 0) > 0:
        streak += 1
        cursor -= datetime.timedelta(days=1)
    return streak


WEEKDAY_LETTER = ["S", "M", "T", "W", "T", "F", "S"]  # GraphQL weekday: 0=Sunday


def heat_color(count, max_count):
    if count == 0:
        return "#2b2118"
    ratio = count / max_count if max_count else 1
    stops = ["#4a2a17", "#7a3b1d", "#c1531f", "#ff6b35", "#ffb454"]
    idx = min(int(ratio * (len(stops) - 1)), len(stops) - 1)
    return stops[idx]


def build_svg(days):
    last7 = days[-7:]
    last14 = days[-14:]
    streak = current_streak(days)
    today = datetime.date.fromisoformat(days[-1]["date"])

    # --- left: flame + streak number ---
    flame = """
    <g transform="translate(20,20)">
      <ellipse cx="24" cy="30" rx="26" ry="26" fill="url(#glow)"/>
      <path d="M24 2c3 9-4 11-4 18 0 5 4 8 8 8 5 0 9-4 9-10 0-5-3-8-3-8s2 4 0 8c-1 2-3 3-5 3-3 0-5-2-5-5 0-4 4-6 4-11 0-6-4-10-4-10s3 4-3 7c-5 3-8 7-8 13 0 8 6 14 14 14s14-6 14-14C41 15 30 8 24 2z"
            fill="url(#flame)"/>
    </g>
    <text x="66" y="44" font-family="-apple-system,Segoe UI,Helvetica,Arial,sans-serif"
          font-size="30" font-weight="700" fill="#ff8c42">{streak}</text>
    <text x="66" y="62" font-family="-apple-system,Segoe UI,Helvetica,Arial,sans-serif"
          font-size="11" fill="#e0a479">days streak</text>
    """.format(streak=streak)

    # --- middle: 7-day row ---
    day_cells = []
    col_w = 24
    start_x = 148
    for i, d in enumerate(last7):
        date = datetime.date.fromisoformat(d["date"])
        letter = WEEKDAY_LETTER[d["weekday"]]
        x = start_x + i * col_w
        done = d["contributionCount"] > 0
        day_cells.append(f'<text x="{x}" y="18" text-anchor="middle" font-family="-apple-system,Segoe UI,Helvetica,Arial,sans-serif" font-size="10" fill="#8b949e">{letter}</text>')
        if done:
            day_cells.append(f'''
            <circle cx="{x}" cy="38" r="11" fill="none" stroke="#ff6b35" stroke-width="2"/>
            <path d="M{x-5} 38l3.5 3.5L{x+5} 34" stroke="#ff6b35" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
            ''')
        else:
            marker = "today" if date == today else "plain"
            color = "#6e7681" if marker == "today" else "#484f58"
            day_cells.append(f'<text x="{x}" y="42" text-anchor="middle" font-family="-apple-system,Segoe UI,Helvetica,Arial,sans-serif" font-size="11" fill="{color}">{date.day}</text>')
    day_row = "\n".join(day_cells)

    # --- right: mini heatmap, 2 rows x 7 cols over the last 14 days ---
    max_count = max((d["contributionCount"] for d in last14), default=1) or 1
    heat_cells = []
    hx0 = 320
    size = 11
    gap = 3
    for i, d in enumerate(last14):
        col = i % 7
        row = i // 7
        x = hx0 + col * (size + gap)
        y = 12 + row * (size + gap)
        color = heat_color(d["contributionCount"], max_count)
        heat_cells.append(f'<rect x="{x}" y="{y}" width="{size}" height="{size}" rx="3" fill="{color}"/>')
    heat_grid = "\n".join(heat_cells)

    width = 448
    height = 96

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <defs>
    <radialGradient id="glow" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#ff6b35" stop-opacity="0.35"/>
      <stop offset="100%" stop-color="#ff6b35" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="flame" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#ffb454"/>
      <stop offset="55%" stop-color="#ff6b35"/>
      <stop offset="100%" stop-color="#c1401a"/>
    </linearGradient>
  </defs>
  <rect x="0.5" y="0.5" width="{width-1}" height="{height-1}" rx="10" fill="#161b22" stroke="#30363d"/>
  {flame}
  {day_row}
  {heat_grid}
</svg>"""
    return svg


def main():
    days = fetch_days()
    svg = build_svg(days)
    out_path = os.path.join(os.path.dirname(__file__), "..", "assets", "streak.svg")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        f.write(svg)
    print(f"wrote {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()

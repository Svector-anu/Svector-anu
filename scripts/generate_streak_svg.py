#!/usr/bin/env python3
"""Generate assets/streak.svg from real GitHub contribution data.

No third-party dependencies (stdlib only) so this runs anywhere: locally
with `gh` on PATH, or in Actions with GITHUB_TOKEN. Re-run any time to
refresh the widget with current data - nothing here is hand-typed.

Layout is three deliberately-separated zones (identity / week / activity),
each with its own breathing room, rather than one dense strip - a dense
strip is what made v1 read as a tiny badge instead of a card.
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


# --- overall canvas -----------------------------------------------------
# widths are derived, not guessed: the day-row needs 7 circles (r=10) at
# col_w=28 starting with a 24px margin inside Z1_END, which needs Z2-Z1
# >= 24*2 + 6*28 + 2*10 = 236px of usable zone before the divider even
# starts to crowd - v1 of this redesign didn't leave that room and the
# 7th (today) circle overflowed past the divider into zone 3.
WIDTH = 529
HEIGHT = 132

Z1_END = 170   # streak identity
Z2_END = 396   # weekly row (226px - fits 7 circles with real margin both sides)
# Z3 = contribution activity, Z2_END..WIDTH (133px - fits the heatmap centered)


def build_flame():
    # a taller, cleaner flame silhouette than v1 - two nested paths (outer
    # body, inner hot-core) read as a flame at this size where a single
    # rough path just read as an orange blob.
    return """
    <g transform="translate(34,20)">
      <ellipse cx="22" cy="34" rx="34" ry="34" fill="url(#glow)"/>
      <path d="M22 0
               C10 14 2 24 2 38
               C2 54 12 66 22 66
               C32 66 42 54 42 38
               C42 30 38 24 34 20
               C34 30 28 34 24 30
               C20 26 22 18 26 12
               C20 10 14 6 22 0 Z"
            fill="url(#flameOuter)"/>
      <path d="M22 20
               C16 28 13 36 13 44
               C13 52 17 58 22 58
               C27 58 31 52 31 45
               C31 40 28 36 25 34
               C25 39 21 41 19 38
               C17 35 18 30 21 26
               C21 24 22 22 22 20 Z"
            fill="url(#flameInner)"/>
    </g>
    """


def build_identity(streak):
    return f"""
    {build_flame()}
    <text x="112" y="62" font-family="-apple-system,Segoe UI,Helvetica,Arial,sans-serif"
          font-size="46" font-weight="800" fill="#ff8c42">{streak}</text>
    <text x="112" y="86" font-family="-apple-system,Segoe UI,Helvetica,Arial,sans-serif"
          font-size="13" letter-spacing="0.3" fill="#e0a479">days streak</text>
    """


def build_week(last7, today):
    cells = []
    col_w = 28
    start_x = Z1_END + 24 + 10  # left margin (24) + circle radius (10)
    circle_r = 10
    letter_y = 34
    circle_cy = 66
    number_y = 71
    for i, d in enumerate(last7):
        date = datetime.date.fromisoformat(d["date"])
        letter = WEEKDAY_LETTER[d["weekday"]]
        x = start_x + i * col_w
        done = d["contributionCount"] > 0
        cells.append(
            f'<text x="{x}" y="{letter_y}" text-anchor="middle" '
            f'font-family="-apple-system,Segoe UI,Helvetica,Arial,sans-serif" '
            f'font-size="12" fill="#8b949e">{letter}</text>'
        )
        if done:
            cells.append(f'''
            <circle cx="{x}" cy="{circle_cy}" r="{circle_r}" fill="none" stroke="#ff6b35" stroke-width="2"/>
            <path d="M{x-4},{circle_cy} L{x-1},{circle_cy+3} L{x+4},{circle_cy-4}"
                  stroke="#ff6b35" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
            ''')
        else:
            color = "#8b949e" if date == today else "#484f58"
            cells.append(
                f'<text x="{x}" y="{number_y}" text-anchor="middle" '
                f'font-family="-apple-system,Segoe UI,Helvetica,Arial,sans-serif" '
                f'font-size="13" fill="{color}">{date.day}</text>'
            )
    return "\n".join(cells)


def build_heatmap(last14):
    max_count = max((d["contributionCount"] for d in last14), default=1) or 1
    cells = []
    size = 13
    gap = 3
    cols = 7
    grid_w = cols * size + (cols - 1) * gap
    hx0 = Z2_END + (WIDTH - Z2_END - grid_w) // 2
    grid_h = 2 * size + gap
    hy0 = (HEIGHT - grid_h) // 2
    for i, d in enumerate(last14):
        col = i % cols
        row = i // cols
        x = hx0 + col * (size + gap)
        y = hy0 + row * (size + gap)
        color = heat_color(d["contributionCount"], max_count)
        cells.append(f'<rect x="{x}" y="{y}" width="{size}" height="{size}" rx="4" fill="{color}"/>')
    return "\n".join(cells)


def build_svg(days):
    last7 = days[-7:]
    last14 = days[-14:]
    streak = current_streak(days)
    today = datetime.date.fromisoformat(days[-1]["date"])

    identity = build_identity(streak)
    week = build_week(last7, today)
    heatmap = build_heatmap(last14)

    divider_y0, divider_y1 = 22, HEIGHT - 22

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">
  <defs>
    <radialGradient id="glow" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#ff6b35" stop-opacity="0.4"/>
      <stop offset="100%" stop-color="#ff6b35" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="flameOuter" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#ffcf8a"/>
      <stop offset="45%" stop-color="#ff8a3d"/>
      <stop offset="100%" stop-color="#c1401a"/>
    </linearGradient>
    <linearGradient id="flameInner" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#fff3d6"/>
      <stop offset="60%" stop-color="#ffb454"/>
      <stop offset="100%" stop-color="#ff6b35"/>
    </linearGradient>
  </defs>
  <rect x="0.5" y="0.5" width="{WIDTH-1}" height="{HEIGHT-1}" rx="14" fill="#161b22" stroke="#30363d"/>
  <line x1="{Z1_END}" y1="{divider_y0}" x2="{Z1_END}" y2="{divider_y1}" stroke="#30363d" stroke-width="1"/>
  <line x1="{Z2_END}" y1="{divider_y0}" x2="{Z2_END}" y2="{divider_y1}" stroke="#30363d" stroke-width="1"/>
  {identity}
  {week}
  {heatmap}
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

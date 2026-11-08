"""Render the profile's activity card from the GitHub API.

Run daily by .github/workflows/activity.yml, which provides GITHUB_TOKEN.
To render from saved data instead: python scripts/activity.py --data data.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import urllib.request
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / "assets"
LOGIN = os.environ.get("GITHUB_LOGIN", "hasyarshad")

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar { weeks { contributionDays { date contributionCount } } }
    }
    repositories(ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC, first: 100) {
      totalCount
      nodes { languages(first: 20) { edges { size node { name } } } }
    }
  }
}
"""

THEMES = {
    "light": {
        "bg": "#f3f1ec",
        "ink": "#1e1c19",
        "soft": "#55514a",
        "faint": "#6f6a61",
        "accent": "#7a2e2e",
        "levels": ["#e5e1d8", "#e2c4bf", "#c48a83", "#9f524b", "#7a2e2e"],
        "langs": ["#7a2e2e", "#a8605a", "#8f877b", "#b3ac9f", "#d2ccc1"],
    },
    "dark": {
        "bg": "#1c1b19",
        "ink": "#f3f1ec",
        "soft": "#c9c4ba",
        "faint": "#a39d92",
        "accent": "#e3a3a3",
        "levels": ["#2c2a27", "#4d302e", "#7b403c", "#b3655f", "#e3a3a3"],
        "langs": ["#e3a3a3", "#b3655f", "#8a8378", "#6b655c", "#4d4943"],
    },
}

MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
SERIF = "Georgia, 'Times New Roman', serif"
WIDTH, HEIGHT = 900, 360
LEFT, CELL, PITCH = 40, 12, 15
GRID_TOP = 172


def fetch() -> dict:
    """Contribution days and language sizes for LOGIN, from the GraphQL API."""
    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": LOGIN}}).encode(),
        headers={"Authorization": f"bearer {os.environ['GITHUB_TOKEN']}"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        user = json.load(response)["data"]["user"]

    weeks = user["contributionsCollection"]["contributionCalendar"]["weeks"]
    days = [
        {"date": d["date"], "count": d["contributionCount"]}
        for week in weeks
        for d in week["contributionDays"]
    ]
    languages: dict[str, int] = {}
    for repo in user["repositories"]["nodes"]:
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            languages[name] = languages.get(name, 0) + edge["size"]
    return {
        "days": days,
        "languages": languages,
        "public_repos": user["repositories"]["totalCount"],
    }


def longest_streak(counts: list[int]) -> int:
    best = run = 0
    for n in counts:
        run = run + 1 if n else 0
        best = max(best, run)
    return best


def level(count: int) -> int:
    """GitHub-style intensity, on fixed thresholds so a quiet year still shows shape."""
    return sum(count >= t for t in (1, 3, 6, 10))


def top_languages(sizes: dict[str, int], keep: int = 4) -> list[tuple[str, float]]:
    total = sum(sizes.values()) or 1
    ranked = sorted(sizes.items(), key=lambda kv: -kv[1])
    shares = [(name, size / total) for name, size in ranked[:keep]]
    rest = sum(size for _, size in ranked[keep:]) / total
    if rest > 0:
        shares.append(("Other", rest))
    return shares


def stat(x: int, figure: str, label: str, colour: str, theme: dict) -> str:
    return (
        f'<text x="{x}" y="104" font-family="{SERIF}" font-size="44" fill="{colour}"'
        f' style="font-variant-numeric: lining-nums">{figure}</text>'
        f'<text x="{x + 2}" y="126" font-family="{MONO}" font-size="11" letter-spacing="1.5"'
        f' fill="{theme["faint"]}">{label}</text>'
    )


def render(data: dict, theme: dict) -> str:
    days = sorted(data["days"], key=lambda d: d["date"])
    counts = [d["count"] for d in days]

    parts = [
        f'<rect width="{WIDTH}" height="{HEIGHT}" rx="14" fill="{theme["bg"]}"/>',
        f'<text x="{LEFT}" y="44" font-family="{MONO}" font-size="12" letter-spacing="2"'
        f' fill="{theme["soft"]}">GITHUB ACTIVITY · LAST 12 MONTHS</text>',
        stat(LEFT, str(sum(counts)), "CONTRIBUTIONS", theme["accent"], theme),
        stat(LEFT + 210, str(sum(1 for n in counts if n)), "ACTIVE DAYS", theme["ink"], theme),
        stat(LEFT + 420, str(longest_streak(counts)), "LONGEST STREAK, DAYS", theme["ink"], theme),
        stat(LEFT + 630, str(data["public_repos"]), "PUBLIC REPOSITORIES", theme["ink"], theme),
    ]

    # Columns are weeks starting on Sunday, as on a GitHub profile.
    first = dt.date.fromisoformat(days[0]["date"])
    offset = (first.weekday() + 1) % 7
    last_month_col = -10
    for i, day in enumerate(days):
        col, row = divmod(i + offset, 7)
        x, y = LEFT + col * PITCH, GRID_TOP + row * PITCH
        fill = theme["levels"][level(day["count"])]
        parts.append(f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="3" fill="{fill}"/>')
        date = dt.date.fromisoformat(day["date"])
        if date.day <= 7 and row == 0 and col - last_month_col >= 3:
            parts.append(
                f'<text x="{x}" y="{GRID_TOP - 8}" font-family="{MONO}" font-size="10"'
                f' letter-spacing="1" fill="{theme["faint"]}">{date.strftime("%b").upper()}</text>'
            )
            last_month_col = col

    legend_x = WIDTH - LEFT - 5 * PITCH
    legend_y = GRID_TOP + 7 * PITCH + 12
    parts.append(
        f'<text x="{legend_x - 8}" y="{legend_y + 10}" text-anchor="end" font-family="{MONO}"'
        f' font-size="10" fill="{theme["faint"]}">LESS</text>'
    )
    for i, fill in enumerate(theme["levels"]):
        parts.append(
            f'<rect x="{legend_x + i * PITCH}" y="{legend_y}" width="{CELL}" height="{CELL}"'
            f' rx="3" fill="{fill}"/>'
        )
    parts.append(
        f'<text x="{legend_x + 5 * PITCH + 2}" y="{legend_y + 10}" font-family="{MONO}"'
        f' font-size="10" fill="{theme["faint"]}">MORE</text>'
    )

    # Languages across public repositories, by bytes of code.
    bar_y, bar_w = HEIGHT - 44, legend_x - LEFT - 110
    x = float(LEFT)
    labels = []
    shares = top_languages(data["languages"])
    for (name, share), colour in zip(shares, theme["langs"], strict=False):
        width = bar_w * share
        parts.append(
            f'<rect x="{x:.1f}" y="{bar_y}" width="{width:.1f}" height="8" fill="{colour}"/>'
        )
        labels.append((name, share, colour))
        x += width
    label_x = LEFT
    for name, share, colour in labels:
        text = f"{name} {share:.0%}"
        parts.append(f'<circle cx="{label_x + 4}" cy="{bar_y + 25}" r="4" fill="{colour}"/>')
        parts.append(
            f'<text x="{label_x + 13}" y="{bar_y + 29}" font-family="{MONO}" font-size="11"'
            f' fill="{theme["soft"]}">{text}</text>'
        )
        label_x += 26 + 7 * len(text)

    body = "\n  ".join(parts)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}"'
        f' viewBox="0 0 {WIDTH} {HEIGHT}" role="img"'
        ' aria-label="GitHub activity over the last 12 months">\n'
        f"  {body}\n</svg>\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, help="render from saved JSON instead of the API")
    args = parser.parse_args()
    data = json.loads(args.data.read_text(encoding="utf-8")) if args.data else fetch()
    for name, theme in THEMES.items():
        (ASSETS / f"activity-{name}.svg").write_text(render(data, theme), encoding="utf-8")


if __name__ == "__main__":
    main()

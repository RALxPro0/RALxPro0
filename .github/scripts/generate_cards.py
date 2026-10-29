#!/usr/bin/env python3
"""Membuat kartu statistik GitHub (stats, bahasa, aktivitas) sebagai file SVG.

Dijalankan oleh GitHub Actions memakai GITHUB_TOKEN bawaan, jadi tidak
bergantung pada layanan pihak ketiga yang sering down.
"""
import html
import json
import os
import sys
import time
import urllib.request
from collections import defaultdict
from datetime import datetime

LOGIN = os.environ.get("GITHUB_REPOSITORY_OWNER") or os.environ.get("LOGIN", "RALxPro0")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
OUT_DIR = os.environ.get("OUT_DIR", "dist")
MOCK = os.environ.get("MOCK_JSON")  # hanya untuk pengujian lokal

BG, BORDER = "#0d1117", "#30363d"
ACCENT, TEXT, MUTED = "#2c9cdb", "#c9d1d9", "#8b949e"
FONT = "'Segoe UI', Ubuntu, 'Helvetica Neue', Arial, sans-serif"

QUERY = """
query($login: String!) {
  user(login: $login) {
    followers { totalCount }
    pullRequests { totalCount }
    issues { totalCount }
    contributionsCollection {
      totalCommitContributions
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false) {
      nodes {
        stargazerCount
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}
"""


def fetch():
    if MOCK:
        with open(MOCK, encoding="utf-8") as f:
            return json.load(f)
    if not TOKEN:
        sys.exit("GITHUB_TOKEN tidak ditemukan.")
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": LOGIN}}).encode(),
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "profile-cards",
        },
    )
    data, last_error = None, None
    for attempt in range(1, 4):  # coba sampai 3 kali bila GitHub sedang sibuk
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.load(resp)
            if data.get("data", {}).get("user"):
                return data
            last_error = data.get("errors")
        except Exception as exc:  # noqa: BLE001
            last_error = exc
        print(f"Percobaan {attempt} gagal: {last_error}", file=sys.stderr)
        time.sleep(attempt * 3)
    sys.exit(f"Gagal mengambil data GitHub: {last_error}")


def esc(text):
    return html.escape(str(text), quote=True)


def card(width, height, title, body):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{esc(title)}">'
        f'<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="10" '
        f'fill="{BG}" stroke="{BORDER}"/>'
        f'<text x="24" y="36" font-family="{FONT}" font-size="18" font-weight="600" '
        f'fill="{ACCENT}">{esc(title)}</text>{body}</svg>'
    )


def stats_card(user):
    stars = sum(r["stargazerCount"] for r in user["repositories"]["nodes"])
    cc = user["contributionsCollection"]
    rows = [
        ("Total Bintang", stars),
        ("Commit (1 tahun terakhir)", cc["totalCommitContributions"]),
        ("Total Pull Request", user["pullRequests"]["totalCount"]),
        ("Total Issue", user["issues"]["totalCount"]),
        ("Total Kontribusi (1 tahun)", cc["contributionCalendar"]["totalContributions"]),
        ("Pengikut", user["followers"]["totalCount"]),
    ]
    body = ""
    for i, (label, value) in enumerate(rows):
        y = 72 + i * 26
        body += (
            f'<text x="24" y="{y}" font-family="{FONT}" font-size="14" fill="{TEXT}">{esc(label)}</text>'
            f'<text x="396" y="{y}" text-anchor="end" font-family="{FONT}" '
            f'font-size="14" font-weight="600" fill="{TEXT}">{value:,}</text>'
        )
    return card(420, 232, f"Statistik GitHub {LOGIN}", body)


def langs_card(user):
    sizes, colors = defaultdict(int), {}
    for repo in user["repositories"]["nodes"]:
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            sizes[name] += edge["size"]
            colors[name] = edge["node"]["color"] or "#8b949e"
    top = sorted(sizes.items(), key=lambda kv: kv[1], reverse=True)[:6]
    total = sum(s for _, s in top) or 1
    bar_w, x = 292, 24.0
    bar = (
        f'<clipPath id="bar"><rect x="24" y="56" width="{bar_w}" height="10" rx="5"/></clipPath>'
        '<g clip-path="url(#bar)">'
    )
    for name, size in top:
        w = size / total * bar_w
        bar += f'<rect x="{x:.2f}" y="56" width="{w:.2f}" height="10" fill="{colors[name]}"/>'
        x += w
    bar += "</g>"
    legend = ""
    for i, (name, size) in enumerate(top):
        col, row = i % 2, i // 2
        lx, ly = 24 + col * 150, 96 + row * 28
        legend += (
            f'<circle cx="{lx + 5}" cy="{ly - 4}" r="5" fill="{colors[name]}"/>'
            f'<text x="{lx + 18}" y="{ly}" font-family="{FONT}" font-size="13" fill="{TEXT}">'
            f'{esc(name)} <tspan fill="{MUTED}">{size / total * 100:.1f}%</tspan></text>'
        )
    if not top:
        legend = f'<text x="24" y="100" font-family="{FONT}" font-size="13" fill="{MUTED}">Belum ada data bahasa</text>'
    return card(340, 232, "Bahasa Terbanyak", bar + legend)


def activity_card(user):
    days = [
        d
        for w in user["contributionsCollection"]["contributionCalendar"]["weeks"]
        for d in w["contributionDays"]
    ][-31:]
    counts = [d["contributionCount"] for d in days]
    width, height = 780, 260
    left, right, top, bottom = 48, 24, 60, 40
    plot_w, plot_h = width - left - right, height - top - bottom
    max_y = max(max(counts, default=0), 4)
    step = max_y / 4

    def px(i):
        return left + (i / max(len(days) - 1, 1)) * plot_w

    def py(v):
        return top + plot_h - (v / max_y) * plot_h

    body = ""
    for g in range(5):
        v = step * g
        y = py(v)
        body += (
            f'<line x1="{left}" y1="{y:.1f}" x2="{width - right}" y2="{y:.1f}" stroke="{BORDER}" stroke-dasharray="3 4"/>'
            f'<text x="{left - 10}" y="{y + 4:.1f}" text-anchor="end" font-family="{FONT}" '
            f'font-size="11" fill="{MUTED}">{v:g}</text>'
        )
    points = [(px(i), py(c)) for i, c in enumerate(counts)]
    if points:
        line = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
        area = f"{left},{top + plot_h} {line} {px(len(points) - 1):.1f},{top + plot_h}"
        body += (
            f'<defs><linearGradient id="fill" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0" stop-color="{ACCENT}" stop-opacity="0.35"/>'
            f'<stop offset="1" stop-color="{ACCENT}" stop-opacity="0"/></linearGradient></defs>'
            f'<polygon points="{area}" fill="url(#fill)"/>'
            f'<polyline points="{line}" fill="none" stroke="{ACCENT}" stroke-width="2.5" '
            f'stroke-linejoin="round" stroke-linecap="round"/>'
        )
        for x, y in points:
            body += f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{BG}" stroke="{ACCENT}" stroke-width="2"/>'
        for i in range(0, len(days), 5):
            label = datetime.strptime(days[i]["date"], "%Y-%m-%d").strftime("%d %b")
            body += (
                f'<text x="{px(i):.1f}" y="{height - 14}" text-anchor="middle" '
                f'font-family="{FONT}" font-size="11" fill="{MUTED}">{label}</text>'
            )
    return card(width, height, f"Aktivitas Kontribusi {LOGIN} (31 hari terakhir)", body)


def main():
    user = fetch()["data"]["user"]
    os.makedirs(OUT_DIR, exist_ok=True)
    for name, svg in (
        ("stats.svg", stats_card(user)),
        ("langs.svg", langs_card(user)),
        ("activity.svg", activity_card(user)),
    ):
        with open(os.path.join(OUT_DIR, name), "w", encoding="utf-8") as f:
            f.write(svg)
        print("dibuat:", name)


if __name__ == "__main__":
    main()

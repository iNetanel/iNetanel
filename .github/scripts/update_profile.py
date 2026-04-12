#!/usr/bin/env python3
"""
update_profile.py
- Fetches latest articles from inetanel.com/articles
- Fetches GitHub stats via GitHub API
- Generates stats SVG cards locally (no external service)
- Rewrites the articles section and updates stats in README.md
"""

import os
import re
import json
import requests
from datetime import datetime
from bs4 import BeautifulSoup

GITHUB_USERNAME = os.environ.get("GITHUB_USERNAME", "inetanel")
GITHUB_TOKEN    = os.environ.get("GITHUB_TOKEN", "")
ARTICLES_URL    = "https://inetanel.com/articles"
README_PATH     = "README.md"

HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
}

# ── BIOS colour palette ───────────────────────────────────────────
BG      = "#0000aa"
BG2     = "#00007a"
CYAN    = "#55ffff"
WHITE   = "#ffffff"
YELLOW  = "#ffff55"
GRAY    = "#aaaaaa"
BORDER  = "#55ffff"


# ═════════════════════════════════════════════════════════════════
# 1. FETCH ARTICLES
# ═════════════════════════════════════════════════════════════════

def fetch_articles():
    try:
        resp = requests.get(ARTICLES_URL, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"[articles] fetch failed: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    articles = []

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        # only article links
        if "/articles/" not in href:
            continue

        # grab heading text
        h = a_tag.find(["h2", "h3"])
        if not h:
            continue
        title = h.get_text(strip=True)

        # date — look for a sibling/nearby element with a date pattern
        date_text = ""
        for el in a_tag.find_all(string=True):
            m = re.search(r"\d{2}/\d{2}/\d{4}", el)
            if m:
                try:
                    dt = datetime.strptime(m.group(), "%d/%m/%Y")
                    date_text = dt.strftime("%Y-%m")
                except:
                    pass
                break

        # source label (Forbes, Silicon Review, etc.)
        source = ""
        label_el = a_tag.find(class_=re.compile(r"label|tag|category|badge", re.I))
        if label_el:
            source = label_el.get_text(strip=True)

        # tags
        tags = []
        for tag_el in a_tag.find_all(class_=re.compile(r"tag|badge|chip", re.I)):
            t = tag_el.get_text(strip=True)
            if t and t not in tags and t != source:
                tags.append(t)

        url = href if href.startswith("http") else "https://inetanel.com" + href

        if title and url not in [x["url"] for x in articles]:
            articles.append({
                "title": title,
                "url": url,
                "date": date_text,
                "source": source,
                "tags": tags[:3],
            })

    # deduplicate and sort newest first
    seen = set()
    unique = []
    for a in articles:
        if a["url"] not in seen:
            seen.add(a["url"])
            unique.append(a)

    unique.sort(key=lambda x: x["date"], reverse=True)
    print(f"[articles] found {len(unique)} articles")
    return unique


def build_articles_block(articles):
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "```",
        f"ARTICLES & PUBLICATIONS — {len(articles)} total  [ auto-updated: {now} ]",
        "─" * 71,
    ]
    for a in articles:
        date   = f"[{a['date']}]" if a['date'] else "        "
        source = f"  [ {a['source']} ]" if a['source'] else ""
        tags   = "  " + "  ".join(f"#{t}" for t in a['tags']) if a['tags'] else ""
        # shorten URL for display
        display_url = a['url'].replace("https://", "").replace("http://", "")
        if len(display_url) > 68:
            display_url = display_url[:65] + "..."

        lines.append(f"{date}  {a['title']}{source}")
        if tags:
            lines.append(f"         {tags}")
        lines.append(f"         → {display_url}")
        lines.append("")

    lines.append("─" * 71)
    lines.append("```")
    return "\n".join(lines)


# ═════════════════════════════════════════════════════════════════
# 2. FETCH GITHUB STATS via API
# ═════════════════════════════════════════════════════════════════

def fetch_github_stats():
    stats = {
        "stars": 0, "commits": 0, "prs": 0,
        "issues": 0, "followers": 0, "repos": 0,
        "langs": {},
    }
    try:
        # user info
        u = requests.get(
            f"https://api.github.com/users/{GITHUB_USERNAME}",
            headers=HEADERS, timeout=10
        ).json()
        stats["followers"] = u.get("followers", 0)
        stats["repos"]     = u.get("public_repos", 0)

        # repos for stars + languages
        page = 1
        while True:
            r = requests.get(
                f"https://api.github.com/users/{GITHUB_USERNAME}/repos",
                headers=HEADERS,
                params={"per_page": 100, "page": page},
                timeout=10,
            ).json()
            if not r or not isinstance(r, list):
                break
            for repo in r:
                stats["stars"] += repo.get("stargazers_count", 0)
                lang = repo.get("language")
                if lang:
                    stats["langs"][lang] = stats["langs"].get(lang, 0) + 1
            if len(r) < 100:
                break
            page += 1

        # commits this year (search API)
        year = datetime.utcnow().year
        cr = requests.get(
            "https://api.github.com/search/commits",
            headers={**HEADERS, "Accept": "application/vnd.github.cloak-preview+json"},
            params={"q": f"author:{GITHUB_USERNAME} committer-date:>{year}-01-01", "per_page": 1},
            timeout=10,
        ).json()
        stats["commits"] = cr.get("total_count", 0)

        # PRs
        pr = requests.get(
            "https://api.github.com/search/issues",
            headers=HEADERS,
            params={"q": f"author:{GITHUB_USERNAME} type:pr", "per_page": 1},
            timeout=10,
        ).json()
        stats["prs"] = pr.get("total_count", 0)

    except Exception as e:
        print(f"[stats] API error: {e}")

    print(f"[stats] {stats}")
    return stats


# ═════════════════════════════════════════════════════════════════
# 3. GENERATE STATS SVG  (replaces github-readme-stats widget)
# ═════════════════════════════════════════════════════════════════

def generate_stats_svg(stats):
    items = [
        ("Total Stars",  str(stats["stars"]),     YELLOW),
        ("Commits (yr)", str(stats["commits"]),   WHITE),
        ("Pull Requests",str(stats["prs"]),        WHITE),
        ("Followers",    str(stats["followers"]),  CYAN),
        ("Public Repos", str(stats["repos"]),      CYAN),
    ]
    row_h = 36
    pad   = 16
    w     = 420
    h     = pad + len(items) * row_h + pad

    rows = ""
    for i, (label, value, color) in enumerate(items):
        y = pad + i * row_h + row_h // 2
        rows += f"""
  <text x="20" y="{y+5}" font-size="13" fill="{CYAN}" font-family="'Courier New',monospace">{label}</text>
  <text x="{w-20}" y="{y+5}" font-size="13" fill="{color}" font-family="'Courier New',monospace" text-anchor="end" font-weight="bold">{value}</text>
  <line x1="16" y1="{y+14}" x2="{w-16}" y2="{y+14}" stroke="{BORDER}" stroke-width="0.4" opacity="0.4"/>"""

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
  <rect width="{w}" height="{h}" fill="{BG}" rx="0"/>
  <rect width="{w}" height="{h}" fill="none" stroke="{BORDER}" stroke-width="1" rx="0"/>
  <rect width="{w}" height="24" fill="{GRAY}"/>
  <text x="10" y="16" font-size="11" fill="{BG}" font-family="'Courier New',monospace" font-weight="bold" letter-spacing="1">■  GITHUB STATS — {GITHUB_USERNAME}</text>
  {rows}
</svg>"""
    return svg


def generate_langs_svg(stats):
    langs = sorted(stats["langs"].items(), key=lambda x: x[1], reverse=True)[:6]
    if not langs:
        return None

    total = sum(v for _, v in langs)
    colors = [CYAN, YELLOW, "#55ff55", "#ff55ff", "#ff5555", "#55aaff"]

    w   = 420
    bh  = 14   # bar height
    pad = 16
    row = 32
    h   = 24 + pad + len(langs) * row + pad

    bars = ""
    bar_y = 24 + pad
    for i, (lang, count) in enumerate(langs):
        pct   = count / total
        bw    = int((w - 40) * pct)
        color = colors[i % len(colors)]
        y     = bar_y + i * row
        bars += f"""
  <text x="20" y="{y+11}" font-size="12" fill="{color}" font-family="'Courier New',monospace">{lang}</text>
  <rect x="20" y="{y+16}" width="{bw}" height="{bh}" fill="{color}" opacity="0.85"/>
  <text x="{w-20}" y="{y+27}" font-size="10" fill="{GRAY}" font-family="'Courier New',monospace" text-anchor="end">{pct*100:.1f}%</text>"""

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
  <rect width="{w}" height="{h}" fill="{BG}" rx="0"/>
  <rect width="{w}" height="{h}" fill="none" stroke="{BORDER}" stroke-width="1" rx="0"/>
  <rect width="{w}" height="24" fill="{GRAY}"/>
  <text x="10" y="16" font-size="11" fill="{BG}" font-family="'Courier New',monospace" font-weight="bold" letter-spacing="1">■  TOP LANGUAGES</text>
  {bars}
</svg>"""
    return svg


# ═════════════════════════════════════════════════════════════════
# 4. REWRITE README SECTIONS
# ═════════════════════════════════════════════════════════════════

def rewrite_readme(articles, stats):
    with open(README_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    # ── Articles section ─────────────────────────────────────────
    articles_block = build_articles_block(articles)
    content = re.sub(
        r"(<!-- ARTICLES:START -->).*?(<!-- ARTICLES:END -->)",
        f"<!-- ARTICLES:START -->\n\n{articles_block}\n\n<!-- ARTICLES:END -->",
        content,
        flags=re.DOTALL,
    )

    # ── Stats section ────────────────────────────────────────────
    stars_line = f"![Stars](https://img.shields.io/badge/Stars-{stats['stars']}-ffff55?style=flat-square&labelColor=0000aa&color=0000aa)"
    commits_line = f"![Commits](https://img.shields.io/badge/Commits_{datetime.utcnow().year}-{stats['commits']}-55ffff?style=flat-square&labelColor=0000aa&color=0000aa)"
    followers_line = f"![Followers](https://img.shields.io/badge/Followers-{stats['followers']}-55ffff?style=flat-square&labelColor=0000aa&color=0000aa)"
    repos_line = f"![Repos](https://img.shields.io/badge/Repos-{stats['repos']}-55ffff?style=flat-square&labelColor=0000aa&color=0000aa)"

    stats_badges = f"{stars_line}\n{commits_line}\n{followers_line}\n{repos_line}"

    content = re.sub(
        r"(<!-- STATS-BADGES:START -->).*?(<!-- STATS-BADGES:END -->)",
        f"<!-- STATS-BADGES:START -->\n\n{stats_badges}\n\n<!-- STATS-BADGES:END -->",
        content,
        flags=re.DOTALL,
    )

    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(content)

    print("[readme] updated successfully")


# ═════════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("── Fetching articles ──")
    articles = fetch_articles()

    print("── Fetching GitHub stats ──")
    stats = fetch_github_stats()

    print("── Generating stats SVG ──")
    stats_svg = generate_stats_svg(stats)
    with open("generated-stats.svg", "w") as f:
        f.write(stats_svg)

    langs_svg = generate_langs_svg(stats)
    if langs_svg:
        with open("generated-langs.svg", "w") as f:
            f.write(langs_svg)

    print("── Rewriting README ──")
    rewrite_readme(articles, stats)

    print("── Done ──")

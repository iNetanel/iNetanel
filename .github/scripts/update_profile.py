#!/usr/bin/env python3
"""
update_profile.py
- Fetches articles from inetanel.com/articles
- Fetches GitHub stats + language data + contribution calendar via API
- Generates beautiful BIOS-styled SVGs:
    generated-langs.svg    — spider/radar chart, top languages
    generated-activity.svg — contribution heatmap (52x7 grid)
- Rewrites README.md sections between markers
"""

import os, re, math, requests
from datetime import datetime
from bs4 import BeautifulSoup

USERNAME     = os.environ.get("GITHUB_USERNAME", "inetanel")
TOKEN        = os.environ.get("GITHUB_TOKEN", "")
ARTICLES_URL = "https://inetanel.com/articles"
README_PATH  = "README.md"

GH = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json"}

BG      = "#0000aa"
BG2     = "#00007a"
CYAN    = "#55ffff"
YELLOW  = "#ffff55"
WHITE   = "#ffffff"
GRAY    = "#aaaaaa"
DOT     = ["#00007a","#003055","#005a99","#0088cc","#55ffff"]
LANG_COLORS = [CYAN, YELLOW, "#55ff55", "#ff55ff", "#ff9955", "#aaaaff", "#ff5555"]


# ═════════════════════════════════════════════════════════════════
# GITHUB DATA
# ═════════════════════════════════════════════════════════════════

def gh_get(url, params=None, extra_headers=None):
    h = {**GH, **(extra_headers or {})}
    r = requests.get(url, headers=h, params=params, timeout=15)
    r.raise_for_status()
    return r.json()

def fetch_langs():
    langs = {}
    page = 1
    while True:
        repos = gh_get(f"https://api.github.com/users/{USERNAME}/repos",
                       {"per_page": 100, "page": page})
        if not repos or not isinstance(repos, list): break
        for repo in repos:
            if repo.get("fork"): continue
            try:
                rl = gh_get(repo["languages_url"])
                for lang, bytes_ in rl.items():
                    langs[lang] = langs.get(lang, 0) + bytes_
            except: pass
        if len(repos) < 100: break
        page += 1
    return langs

def fetch_contributions():
    query = """
    query($login: String!) {
      user(login: $login) {
        contributionsCollection {
          contributionCalendar {
            weeks {
              contributionDays { contributionCount date }
            }
          }
        }
      }
    }"""
    try:
        r = requests.post(
            "https://api.github.com/graphql",
            headers={**GH, "Content-Type": "application/json"},
            json={"query": query, "variables": {"login": USERNAME}},
            timeout=15
        )
        weeks = (r.json()["data"]["user"]["contributionsCollection"]
                         ["contributionCalendar"]["weeks"])
        days = []
        for w in weeks:
            for d in w["contributionDays"]:
                days.append(d["contributionCount"])
        return days
    except Exception as e:
        print(f"[contrib] {e}")
        return []

def fetch_stats():
    stats = {"stars": 0, "commits": 0, "prs": 0, "followers": 0, "repos": 0}
    try:
        u = gh_get(f"https://api.github.com/users/{USERNAME}")
        stats["followers"] = u.get("followers", 0)
        stats["repos"]     = u.get("public_repos", 0)
        page = 1
        while True:
            repos = gh_get(f"https://api.github.com/users/{USERNAME}/repos",
                           {"per_page": 100, "page": page})
            if not repos or not isinstance(repos, list): break
            for repo in repos:
                stats["stars"] += repo.get("stargazers_count", 0)
            if len(repos) < 100: break
            page += 1
        year = datetime.utcnow().year
        cr = gh_get("https://api.github.com/search/commits",
                    {"q": f"author:{USERNAME} committer-date:>{year}-01-01", "per_page": 1},
                    {"Accept": "application/vnd.github.cloak-preview+json"})
        stats["commits"] = cr.get("total_count", 0)
        pr = gh_get("https://api.github.com/search/issues",
                    {"q": f"author:{USERNAME} type:pr", "per_page": 1})
        stats["prs"] = pr.get("total_count", 0)
    except Exception as e:
        print(f"[stats] {e}")
    return stats


# ═════════════════════════════════════════════════════════════════
# SVG: SPIDER / RADAR CHART
# ═════════════════════════════════════════════════════════════════

def generate_langs_svg(langs_raw):
    if not langs_raw:
        return None

    total = sum(langs_raw.values())
    top   = sorted(langs_raw.items(), key=lambda x: x[1], reverse=True)[:7]
    top_total = sum(v for _, v in top)

    W, H   = 860, 460
    cx, cy = W // 2, H // 2 + 20
    R      = 130   # max radius — slightly smaller to give labels more room
    N      = len(top)
    rings  = 5
    HDR    = 24
    PI     = math.pi

    def angle(i):
        return (i / N) * 2 * PI - PI / 2

    def pt(i, r):
        a = angle(i)
        return cx + r * math.cos(a), cy + r * math.sin(a)

    # scale: map top language (100%) to full radius
    # other langs scaled relative to top
    max_pct = top[0][1] / top_total

    def scaled_r(pct):
        return R * (pct / max_pct) * 0.95

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
  <rect width="{W}" height="{H}" fill="{BG}"/>
  <rect width="{W}" height="{HDR}" fill="{GRAY}"/>
  <text x="10" y="{HDR-8}" font-size="11" fill="{BG}" font-family="'Courier New',monospace" font-weight="bold" letter-spacing="2">&#9632;  LANGUAGE RADAR &#8212; {USERNAME}</text>
"""

    # grid rings
    for ring in range(1, rings + 1):
        r      = R * ring / rings
        points = " ".join(f"{pt(i,r)[0]:.1f},{pt(i,r)[1]:.1f}" for i in range(N))
        opacity = "0.5" if ring == rings else "0.2"
        width   = "1" if ring == rings else "0.5"
        svg += f'  <polygon points="{points}" fill="none" stroke="{CYAN}" stroke-width="{width}" opacity="{opacity}"/>\n'

        # ring % label — right of centre, readable
        label_pct = round(ring / rings * 100)
        svg += f'  <text x="{cx+5:.0f}" y="{cy - r + 5:.0f}" font-size="11" fill="{CYAN}" opacity="0.55" font-family="\'Courier New\',monospace">{label_pct}%</text>\n'

    # spokes
    for i in range(N):
        x, y = pt(i, R)
        svg += f'  <line x1="{cx}" y1="{cy}" x2="{x:.1f}" y2="{y:.1f}" stroke="{CYAN}" stroke-width="0.5" opacity="0.2"/>\n'

    # filled polygon
    poly_pts = []
    for i, (lang, count) in enumerate(top):
        pct = count / top_total
        r   = scaled_r(pct)
        x, y = pt(i, r)
        poly_pts.append(f"{x:.1f},{y:.1f}")
    poly_str = " ".join(poly_pts)
    svg += f'  <polygon points="{poly_str}" fill="{CYAN}" fill-opacity="0.1" stroke="{CYAN}" stroke-width="1.5" stroke-linejoin="round"/>\n'

    # dots + labels — pushed far out with background boxes
    LABEL_R  = R + 72   # much further out for breathing room
    BOX_H    = 46
    BOX_PAD  = 12

    for i, (lang, count) in enumerate(top):
        pct   = count / top_total
        r     = scaled_r(pct)
        color = LANG_COLORS[i % len(LANG_COLORS)]
        x, y  = pt(i, r)

        # glow circle
        svg += f'  <circle cx="{x:.1f}" cy="{y:.1f}" r="12" fill="{color}" opacity="0.15"/>\n'
        # dot
        svg += f'  <circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{color}" stroke="{BG}" stroke-width="2"/>\n'

        # label position — pushed outside
        lx, ly = pt(i, LABEL_R)
        pct_disp = f"{pct*100:.1f}%"

        # estimate box width based on longer of name/pct (~9px per char at 15px font)
        chars    = max(len(lang), len(pct_disp))
        box_w    = chars * 10 + BOX_PAD * 2
        box_x    = lx - box_w / 2
        box_y    = ly - BOX_H / 2

        # dark background box with colored border — makes text pop on any bg
        svg += f'  <rect x="{box_x:.1f}" y="{box_y:.1f}" width="{box_w:.0f}" height="{BOX_H}" fill="#000066" rx="3" opacity="0.85"/>\n'
        svg += f'  <rect x="{box_x:.1f}" y="{box_y:.1f}" width="{box_w:.0f}" height="{BOX_H}" fill="none" stroke="{color}" stroke-width="1" rx="3" opacity="0.6"/>\n'

        # language name — 15px bold colored
        svg += f'  <text x="{lx:.1f}" y="{ly - 7:.1f}" font-size="15" fill="{color}" font-family="\'Courier New\',monospace" text-anchor="middle" font-weight="bold">{lang}</text>\n'
        # percentage — 16px bold white, clearly readable
        svg += f'  <text x="{lx:.1f}" y="{ly + 14:.1f}" font-size="16" fill="{WHITE}" font-family="\'Courier New\',monospace" text-anchor="middle" font-weight="bold">{pct_disp}</text>\n'

    # centre dot
    svg += f'  <circle cx="{cx}" cy="{cy}" r="3" fill="{CYAN}"/>\n'

    svg += "</svg>"
    return svg


# ═════════════════════════════════════════════════════════════════
# SVG: CONTRIBUTION HEATMAP
# ═════════════════════════════════════════════════════════════════

def generate_activity_svg(days):
    W      = 860
    HDR    = 24
    PAD_X  = 20
    PAD_Y  = 16
    CELL   = 13
    GAP    = 2
    COLS   = 52
    ROWS_G = 7

    grid_w   = COLS * (CELL + GAP) - GAP
    grid_h   = ROWS_G * (CELL + GAP) - GAP
    offset_x = (W - grid_w) // 2
    H        = HDR + PAD_Y + grid_h + PAD_Y + 18

    if not days:
        days = [0] * (COLS * ROWS_G)

    max_count = max(days) if days else 1
    if max_count == 0: max_count = 1

    def level(count):
        if count == 0: return 0
        f = count / max_count
        if f < 0.2: return 1
        if f < 0.4: return 2
        if f < 0.7: return 3
        return 4

    while len(days) < COLS * ROWS_G:
        days = [0] + days
    days = days[-(COLS * ROWS_G):]

    cells = ""
    for col in range(COLS):
        for row in range(ROWS_G):
            idx   = col * ROWS_G + row
            cnt   = days[idx] if idx < len(days) else 0
            lvl   = level(cnt)
            color = DOT[lvl]
            x     = offset_x + col * (CELL + GAP)
            y     = HDR + PAD_Y + row * (CELL + GAP)
            extra = f' filter="url(#glow)"' if lvl == 4 else ""
            cells += f'\n  <rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" fill="{color}" rx="2"{extra}/>'

    # legend
    leg_x = offset_x
    leg_y = HDR + PAD_Y + grid_h + PAD_Y + 2
    legend = f'<text x="{leg_x}" y="{leg_y+10}" font-size="10" fill="{GRAY}" font-family="\'Courier New\',monospace">Less</text>'
    for i, c in enumerate(DOT):
        lx = leg_x + 36 + i * 17
        legend += f'<rect x="{lx}" y="{leg_y}" width="{CELL}" height="{CELL}" fill="{c}" rx="2"/>'
    end_x = leg_x + 36 + len(DOT) * 17 + 4
    legend += f'<text x="{end_x}" y="{leg_y+10}" font-size="10" fill="{GRAY}" font-family="\'Courier New\',monospace">More</text>'

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
  <defs>
    <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
      <feGaussianBlur stdDeviation="1.5" result="blur"/>
      <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
  </defs>
  <rect width="{W}" height="{H}" fill="{BG}"/>
  <rect width="{W}" height="{HDR}" fill="{GRAY}"/>
  <text x="10" y="{HDR-8}" font-size="11" fill="{BG}" font-family="'Courier New',monospace" font-weight="bold" letter-spacing="2">&#9632;  CONTRIBUTION ACTIVITY &#8212; last 12 months</text>
  {cells}
  {legend}
</svg>"""


# ═════════════════════════════════════════════════════════════════
# ARTICLES
# ═════════════════════════════════════════════════════════════════

def fetch_articles():
    try:
        resp = requests.get(ARTICLES_URL, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        print(f"[articles] {e}"); return []

    articles, seen = [], set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/articles/" not in href: continue
        h = a.find(["h2", "h3"])
        if not h: continue
        title = h.get_text(strip=True)
        date  = ""
        for el in a.find_all(string=True):
            m = re.search(r"\d{2}/\d{2}/\d{4}", el)
            if m:
                try: date = datetime.strptime(m.group(), "%d/%m/%Y").strftime("%Y-%m")
                except: pass
                break
        url  = href if href.startswith("http") else "https://inetanel.com" + href
        tags = [t.get_text(strip=True)
                for t in a.find_all(class_=re.compile(r"tag|badge|chip", re.I))][:3]
        if url not in seen:
            seen.add(url)
            articles.append({"title": title, "url": url, "date": date, "tags": tags})

    articles.sort(key=lambda x: x["date"], reverse=True)
    print(f"[articles] {len(articles)} found")
    return articles

def build_articles_block(articles):
    now   = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    lines = ["```",
             f"ARTICLES & PUBLICATIONS — {len(articles)} total  [ auto-updated: {now} ]",
             "─" * 71]
    for a in articles:
        date = f"[{a['date']}]" if a["date"] else "        "
        tags = "  " + "  ".join(f"#{t}" for t in a["tags"]) if a["tags"] else ""
        url  = a["url"].replace("https://", "").replace("http://", "")
        if len(url) > 68: url = url[:65] + "..."
        lines.append(f"{date}  {a['title']}")
        if tags: lines.append(f"         {tags}")
        lines.append(f"         → {url}")
        lines.append("")
    lines += ["─" * 71, "```"]
    return "\n".join(lines)


# ═════════════════════════════════════════════════════════════════
# README REWRITE
# ═════════════════════════════════════════════════════════════════

def rewrite_readme(articles, stats):
    with open(README_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    block = build_articles_block(articles)
    content = re.sub(
        r"(<!-- ARTICLES:START -->).*?(<!-- ARTICLES:END -->)",
        f"<!-- ARTICLES:START -->\n\n{block}\n\n<!-- ARTICLES:END -->",
        content, flags=re.DOTALL)

    year   = datetime.utcnow().year
    badges = "\n".join([
        f"![Stars](https://img.shields.io/badge/Stars-{stats['stars']}-ffff55?style=flat-square&labelColor=0000aa&color=0000aa)",
        f"![Commits](https://img.shields.io/badge/Commits_{year}-{stats['commits']}-55ffff?style=flat-square&labelColor=0000aa&color=0000aa)",
        f"![PRs](https://img.shields.io/badge/Pull_Requests-{stats['prs']}-55ffff?style=flat-square&labelColor=0000aa&color=0000aa)",
        f"![Followers](https://img.shields.io/badge/Followers-{stats['followers']}-55ffff?style=flat-square&labelColor=0000aa&color=0000aa)",
        f"![Repos](https://img.shields.io/badge/Repos-{stats['repos']}-55ffff?style=flat-square&labelColor=0000aa&color=0000aa)",
    ])
    content = re.sub(
        r"(<!-- STATS-BADGES:START -->).*?(<!-- STATS-BADGES:END -->)",
        f"<!-- STATS-BADGES:START -->\n\n{badges}\n\n<!-- STATS-BADGES:END -->",
        content, flags=re.DOTALL)

    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(content)
    print("[readme] updated")


# ═════════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("── Languages ──")
    langs_raw = fetch_langs()

    print("── Contributions ──")
    days = fetch_contributions()

    print("── Stats ──")
    stats = fetch_stats()

    print("── Generating language radar chart ──")
    svg = generate_langs_svg(langs_raw)
    if svg:
        with open("generated-langs.svg", "w") as f: f.write(svg)
        print("  saved generated-langs.svg")

    print("── Generating activity heatmap ──")
    svg2 = generate_activity_svg(days)
    with open("generated-activity.svg", "w") as f: f.write(svg2)
    print("  saved generated-activity.svg")

    print("── Articles ──")
    articles = fetch_articles()

    print("── Rewriting README ──")
    rewrite_readme(articles, stats)

    print("── Done ──")

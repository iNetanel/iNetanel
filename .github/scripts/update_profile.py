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
# SVG: TROPHIES
# ═════════════════════════════════════════════════════════════════

def generate_trophies_svg(stats, days):
    """Clean professional stat grid — no ranks, just real numbers."""
    BG    = "#0000aa"
    BG2   = "#00007a"
    GRAY  = "#aaaaaa"
    CYAN  = "#55ffff"
    YELLOW= "#ffff55"
    WHITE = "#ffffff"
    W     = 860
    MONO  = "'Courier New',monospace"
    HDR   = 28

    total_commits   = stats.get("commits", 0)
    total_stars     = stats.get("stars", 0)
    total_prs       = stats.get("prs", 0)
    total_repos     = stats.get("repos", 0)
    total_followers = stats.get("followers", 0)
    total_contribs  = sum(days) if days else 0

    metrics = [
        ("Stars",          f"{total_stars:,}",     YELLOW),
        ("Commits",        f"{total_commits:,}",   CYAN),
        ("Pull Requests",  f"{total_prs:,}",       CYAN),
        ("Repositories",   f"{total_repos:,}",     CYAN),
        ("Followers",      f"{total_followers:,}", CYAN),
        ("Contributions",  f"{total_contribs:,}",  CYAN),
    ]

    COLS   = 3
    ROWS   = 2
    PAD    = 16
    CELL_W = (W - PAD * 2) // COLS
    CELL_H = 72
    BODY_H = PAD + ROWS * CELL_H + PAD
    H      = HDR + BODY_H

    svg  = f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">\n'
    svg += f'  <rect width="{W}" height="{H}" fill="{BG}"/>\n'
    svg += f'  <rect width="{W}" height="{HDR}" fill="{GRAY}"/>\n'
    svg += f'  <rect x="0" y="0" width="4" height="{HDR}" fill="{BG}"/>\n'
    svg += f'  <text x="14" y="19" font-size="13" fill="{BG}" font-family="{MONO}" font-weight="bold" letter-spacing="2">&#9632;  GITHUB STATS {datetime.utcnow().year} &#8212; {USERNAME}</text>\n'
    svg += f'  <text x="760" y="19" font-size="11" fill="{BG}" font-family="{MONO}">[ F9 ]</text>\n'

    for i, (label, value, color) in enumerate(metrics):
        col = i % COLS
        row = i // COLS
        x   = PAD + col * CELL_W
        y   = HDR + PAD + row * CELL_H

        # cell background
        svg += f'  <rect x="{x+4}" y="{y+4}" width="{CELL_W-8}" height="{CELL_H-8}" fill="{BG2}" rx="4" opacity="0.6"/>\n'
        # colored left accent bar
        svg += f'  <rect x="{x+4}" y="{y+4}" width="3" height="{CELL_H-8}" fill="{color}" rx="1"/>\n'
        # big number
        svg += f'  <text x="{x + CELL_W//2}" y="{y + CELL_H//2 - 4}" font-size="26" fill="{color}" font-family="{MONO}" text-anchor="middle" font-weight="bold">{value}</text>\n'
        # label below
        svg += f'  <text x="{x + CELL_W//2}" y="{y + CELL_H//2 + 20}" font-size="11" fill="{GRAY}" font-family="{MONO}" text-anchor="middle">{label}</text>\n'

    svg += '</svg>'
    return svg



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
        repos = gh_get("https://api.github.com/user/repos",
                       {"per_page": 100, "page": page,
                        "affiliation": "owner,organization_member",
                        "visibility": "all"})
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
    print(f"[langs] {len(langs)} languages found")
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
        # Use authenticated endpoint to count ALL repos including private
        page = 1
        while True:
            repos = gh_get("https://api.github.com/user/repos",
                           {"per_page": 100, "page": page,
                            "affiliation": "owner,organization_member",
                            "visibility": "all"})
            if not repos or not isinstance(repos, list): break
            for repo in repos:
                stats["stars"] += repo.get("stargazers_count", 0)
                stats["repos"] += 1
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

    # Take top 8 languages
    top = sorted(langs_raw.items(), key=lambda x: x[1], reverse=True)[:8]
    top_total = sum(v for _, v in top)
    N = len(top)

    W, H   = 860, 500
    HDR    = 24
    cx     = W // 2
    cy     = HDR + (H - HDR) // 2 + 10
    R      = 148
    rings  = 5
    PI     = math.pi

    colors = [CYAN, YELLOW, "#55ff55", "#ff55ff", "#ff9955", "#aaaaff", "#ff5555", "#55ffaa"]

    def angle(i):
        return (i / N) * 2 * PI - PI / 2

    def pt(i, r):
        a = angle(i)
        return cx + r * math.cos(a), cy + r * math.sin(a)

    max_val = top[0][1]

    def data_r(val):
        return max(10, R * val / max_val)

    parts = []
    parts.append(f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
  <rect width="{W}" height="{H}" fill="{BG}"/>
  <rect width="{W}" height="{HDR}" fill="{GRAY}"/>
  <text x="10" y="{HDR-8}" font-size="11" fill="{BG}" font-family="'Courier New',monospace" font-weight="bold" letter-spacing="2">&#9632;  LANGUAGE RADAR &#8212; {USERNAME} ({N} languages)</text>''')

    # Grid rings
    for ring in range(1, rings + 1):
        r   = R * ring / rings
        pts = " ".join(f"{pt(i,r)[0]:.1f},{pt(i,r)[1]:.1f}" for i in range(N))
        sw  = "1.5" if ring == rings else "0.8"
        op  = "0.85" if ring == rings else "0.45"
        parts.append(f'  <polygon points="{pts}" fill="none" stroke="{CYAN}" stroke-width="{sw}" opacity="{op}"/>')
        # ring label at top
        lbl = round(ring / rings * 100)
        parts.append(f'  <text x="{cx+5:.0f}" y="{cy - r + 5:.0f}" font-size="10" fill="{CYAN}" opacity="0.7" font-family="\'Courier New\',monospace">{lbl}%</text>')

    # Spokes
    for i in range(N):
        x, y = pt(i, R)
        parts.append(f'  <line x1="{cx:.1f}" y1="{cy:.1f}" x2="{x:.1f}" y2="{y:.1f}" stroke="{CYAN}" stroke-width="1" opacity="0.45"/>')

    # Filled data polygon
    poly = " ".join(f"{pt(i, data_r(v))[0]:.1f},{pt(i, data_r(v))[1]:.1f}" for i, (_, v) in enumerate(top))
    parts.append(f'  <polygon points="{poly}" fill="{CYAN}" fill-opacity="0.2" stroke="{CYAN}" stroke-width="2.5" stroke-linejoin="round"/>')

    # Dots + clamped label boxes
    LABEL_R = R + 70
    MARGIN  = 8

    for i, (lang, val) in enumerate(top):
        color    = colors[i % len(colors)]
        dr       = data_r(val)
        dx, dy   = pt(i, dr)
        lx, ly   = pt(i, LABEL_R)
        pct_val  = val / top_total * 100
        pct_disp = f"{pct_val:.1f}%"
        chars    = max(len(lang), len(pct_disp))
        BOX_W    = chars * 9 + 24
        BOX_H    = 44
        # clamp box inside canvas
        bx = max(MARGIN, min(W - BOX_W - MARGIN, lx - BOX_W / 2))
        by = max(HDR + MARGIN, min(H - BOX_H - MARGIN, ly - BOX_H / 2))
        tx = bx + BOX_W / 2
        ty = by + BOX_H / 2

        # glow
        parts.append(f'  <circle cx="{dx:.1f}" cy="{dy:.1f}" r="13" fill="{color}" opacity="0.12"/>')
        # dot
        parts.append(f'  <circle cx="{dx:.1f}" cy="{dy:.1f}" r="5" fill="{color}" stroke="{BG}" stroke-width="2"/>')
        # dashed leader
        parts.append(f'  <line x1="{dx:.1f}" y1="{dy:.1f}" x2="{tx:.1f}" y2="{ty:.1f}" stroke="{color}" stroke-width="0.5" opacity="0.3" stroke-dasharray="3 3"/>')
        # box fill + border
        parts.append(f'  <rect x="{bx:.1f}" y="{by:.1f}" width="{BOX_W:.0f}" height="{BOX_H}" fill="{BG2}" rx="3"/>')
        parts.append(f'  <rect x="{bx:.1f}" y="{by:.1f}" width="{BOX_W:.0f}" height="{BOX_H}" fill="none" stroke="{color}" stroke-width="1" rx="3" opacity="0.7"/>')
        # name
        parts.append(f'  <text x="{tx:.1f}" y="{by+16:.1f}" font-size="13" fill="{color}" font-family="\'Courier New\',monospace" text-anchor="middle" font-weight="bold">{lang}</text>')
        # pct — white, larger
        parts.append(f'  <text x="{tx:.1f}" y="{by+34:.1f}" font-size="15" fill="{WHITE}" font-family="\'Courier New\',monospace" text-anchor="middle" font-weight="bold">{pct_disp}</text>')

    # centre dot
    parts.append(f'  <circle cx="{cx:.1f}" cy="{cy:.1f}" r="3" fill="{CYAN}"/>')
    parts.append("</svg>")
    return "\n".join(parts)


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
    MONTH_H  = 16
    H        = HDR + PAD_Y + MONTH_H + grid_h + PAD_Y + 18

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

    # Month labels — figure out which column each month starts at
    from datetime import date, timedelta
    today      = date.today()
    start_date = today - timedelta(weeks=52)
    month_cols = {}
    for col in range(COLS):
        d = start_date + timedelta(weeks=col)
        key = (d.year, d.month)
        if key not in month_cols:
            month_cols[key] = col
    MONTH_NAMES = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

    # Month labels sit above the grid — add extra space
    MONTH_H = 16
    cells = ""
    for col in range(COLS):
        for row in range(ROWS_G):
            idx   = col * ROWS_G + row
            cnt   = days[idx] if idx < len(days) else 0
            lvl   = level(cnt)
            color = DOT[lvl]
            x     = offset_x + col * (CELL + GAP)
            y     = HDR + PAD_Y + MONTH_H + row * (CELL + GAP)
            extra = f' filter="url(#glow)"' if lvl == 4 else ""
            cells += f'\n  <rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" fill="{color}" rx="2"{extra}/>'

    # Draw month labels
    month_labels = ""
    for (yr, mo), col in month_cols.items():
        if col > 0:  # skip first partial month
            mx = offset_x + col * (CELL + GAP)
            my = HDR + PAD_Y + MONTH_H - 4
            month_labels += f'\n  <text x="{mx}" y="{my}" font-size="10" fill="{GRAY}" font-family="\'Courier New\',monospace">{MONTH_NAMES[mo-1]}</text>'

    # legend
    leg_x = offset_x
    leg_y = HDR + PAD_Y + MONTH_H + grid_h + PAD_Y + 2
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
  {month_labels}
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

# ─────────────────────────────────────────────────────────────────
# SVG SECTION BUILDER — used by all dynamic sections
# ─────────────────────────────────────────────────────────────────

def make_section_svg(filename, title, fkey, rows):
    """Generate a complete section SVG: gray bar + blue body with content rows."""
    BG="#0000aa"; BG2="#00007a"; GRAY="#aaaaaa"; W=860; MONO="'Courier New',monospace"
    HDR=28; PAD=14; LH=20
    body_h = PAD + len(rows)*LH + PAD
    H = HDR + body_h
    def esc(s): return s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
    out  = f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">\n'
    out += f'  <rect width="{W}" height="{H}" fill="{BG}"/>\n'
    out += f'  <rect width="{W}" height="{HDR}" fill="{GRAY}"/>\n'
    out += f'  <rect x="0" y="0" width="4" height="{HDR}" fill="{BG}"/>\n'
    out += f'  <text x="14" y="19" font-size="13" fill="{BG}" font-family="{MONO}" font-weight="bold" letter-spacing="2">&#9632;  {esc(title)}</text>\n'
    if fkey:
        out += f'  <text x="760" y="19" font-size="11" fill="{BG}" font-family="{MONO}">{fkey}</text>\n'
    out += f'  <rect x="12" y="{HDR+6}" width="{W-24}" height="{body_h-12}" fill="{BG2}" rx="2" opacity="0.35"/>\n'
    for i,(txt,col,fs,bold) in enumerate(rows):
        y  = HDR + PAD + i*LH + LH - 5
        fw = "bold" if bold else "normal"
        out += f'  <text x="20" y="{y}" font-size="{fs}" fill="{col}" font-family="{MONO}" font-weight="{fw}">{esc(txt)}</text>\n'
    out += '</svg>'
    with open(filename, "w") as f: f.write(out)
    return filename


# ─────────────────────────────────────────────────────────────────
# ARTICLES — generates section-articles.svg (complete, with bar)
# ─────────────────────────────────────────────────────────────────

def build_articles_block(articles):
    now  = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    CYAN="#55ffff"; YELLOW="#ffff55"; WHITE="#ffffff"; GRAY="#aaaaaa"

    rows = []
    rows.append((f"Updated: {now}  ·  {len(articles)} articles", GRAY, 10, False))
    rows.append(("─"*74, CYAN, 10, False))
    for a in articles:
        date  = f"[{a['date']}]" if a["date"] else "        "
        title = a["title"] if len(a["title"]) <= 72 else a["title"][:69]+"..."
        url   = a["url"].replace("https://","").replace("http://","")
        if len(url) > 65: url = url[:62]+"..."
        tags  = "  ".join(f"#{t}" for t in a["tags"]) if a["tags"] else ""
        rows.append((f"{date}  {title}", WHITE, 12, False))
        if tags: rows.append((f"            {tags}", YELLOW, 11, False))
        rows.append((f"            → {url}", CYAN, 11, False))
        rows.append(("", GRAY, 10, False))
    rows.append(("─"*74, CYAN, 10, False))

    make_section_svg("section-articles.svg", "ARTICLES & PUBLICATIONS", "[ F3 ]", rows)
    return '<div align="center"><img src="section-articles.svg" width="100%" alt="Articles"/></div>'


# ─────────────────────────────────────────────────────────────────
# PROJECTS — generates section-projects.svg (complete, with bar)
# ─────────────────────────────────────────────────────────────────

def fetch_projects():
    try:
        resp = requests.get("https://inetanel.com/projects", timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        projects = []
        for h2 in soup.find_all("h2"):
            name = h2.get_text(strip=True)
            if not name or name in ["Projects","Main Menu"]: continue
            stage=""; status=""; desc_parts=[]; first_url=""
            node = h2.find_next_sibling()
            p_count = 0
            while node and node.name not in ["h2","h1"]:
                if node.name == "p":
                    txt = node.get_text(strip=True)
                    if p_count == 0: stage = txt
                    elif p_count == 1: status = txt
                    p_count += 1
                    a_tag = node.find("a")
                    if a_tag and not first_url:
                        href = a_tag.get("href","")
                        if href.startswith("http"): first_url = href
                elif node.name == "ul":
                    for li in node.find_all("li"):
                        desc_parts.append(li.get_text(strip=True))
                node = node.find_next_sibling()
            desc = " ".join(desc_parts[:2])
            if len(desc) > 200: desc = desc[:197]+"..."
            projects.append({"name":name,"stage":stage,"status":status,"desc":desc,"url":first_url})
        print(f"[projects] {len(projects)} found")
        return projects
    except Exception as e:
        print(f"[projects] {e}"); return []


def build_projects_block(projects):
    now  = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    CYAN="#55ffff"; YELLOW="#ffff55"; WHITE="#ffffff"; GRAY="#aaaaaa"

    def wrap(text, maxlen=78):
        words=text.split(); lines=[]; cur=""
        for w in words:
            if len(cur)+len(w)+1>maxlen: lines.append(cur.strip()); cur=w+" "
            else: cur+=w+" "
        if cur: lines.append(cur.strip())
        return lines

    rows = []
    rows.append((f"Updated: {now}  ·  {len(projects)} projects", GRAY, 10, False))
    rows.append(("─"*74, CYAN, 10, False))
    for p in projects:
        rows.append((p["name"], YELLOW, 14, True))
        meta = []
        if p.get("stage"): meta.append(p["stage"])
        if p.get("status"): meta.append(p["status"])
        if meta: rows.append(("  " + "  ·  ".join(meta), CYAN, 11, False))
        for dl in wrap(p.get("desc",""), 80)[:3]:
            rows.append(("  " + dl, WHITE, 12, False))
        if p.get("url"):
            disp = p["url"].replace("https://","").replace("http://","")
            rows.append(("  → " + disp, CYAN, 11, False))
        rows.append(("─"*74, CYAN, 10, False))

    make_section_svg("section-projects.svg", "PROJECTS", "[ F6 ]", rows)
    return '<div align="center"><img src="section-projects.svg" width="100%" alt="Projects"/></div>'


# ─────────────────────────────────────────────────────────────────
# CONTACT — generates section-contact.svg (complete, with bar)
# ─────────────────────────────────────────────────────────────────

def fetch_contact():
    try:
        resp = requests.get("https://inetanel.com/contact", timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        info = {}
        for a in soup.find_all("a", href=True):
            href = a["href"]; text = a.get_text(strip=True)
            # email skipped — Cloudflare obfuscates it, hardcoded in build_contact_block
            if "tel:" in href:
                info["phone"] = text
            elif "linkedin.com/in/" in href:
                info["linkedin"] = href.replace("https://www.","").replace("https://","")
            elif "medium.com/@" in href:
                info["medium"] = href.replace("https://","")
            elif "crunchbase.com/person/" in href:
                info["crunchbase"] = href.replace("https://www.","").replace("https://","")
            elif "f6s.com/" in href and "f6s.com/netanel" in href:
                info["f6s"] = href.replace("https://www.","").replace("https://","")
        for p in soup.find_all(["p","li","div"]):
            t = p.get_text(strip=True)
            if "London" in t or "United Kingdom" in t: info["location"] = "London, United Kingdom"; break
        avail = []
        for li in soup.find_all("li"):
            t = li.get_text(strip=True)
            if any(w in t.lower() for w in ["advisory","mentor","due diligence","keynote","architecture","panel","social good"]):
                avail.append(t[:70])
        info["availability"] = avail[:5]
        print(f"[contact] fetched: {list(info.keys())}")
        return info
    except Exception as e:
        print(f"[contact] {e}"); return {}


def build_contact_block(contact=None):
    CYAN="#55ffff"; YELLOW="#ffff55"; WHITE="#ffffff"; GRAY="#aaaaaa"
    c = contact or {}
    email    = "inetanel@me.com"  # hardcoded — Cloudflare blocks scraping
    phone    = c.get("phone","+44 (7570) 397-338")
    linkedin = c.get("linkedin","linkedin.com/in/inetanel")
    medium   = c.get("medium","medium.com/@inetanel")
    cbase    = c.get("crunchbase","crunchbase.com/person/netanel-eliav")
    f6s      = c.get("f6s","f6s.com/netanel")
    location = c.get("location","London, United Kingdom")
    avail    = c.get("availability",[])

    rows = [
        (f"Email      :  {email}", WHITE, 12, False),
        (f"Phone      :  {phone}", WHITE, 12, False),
        (f"LinkedIn   :  {linkedin}", WHITE, 12, False),
        (f"Medium     :  {medium}", WHITE, 12, False),
        (f"Crunchbase :  {cbase}", WHITE, 12, False),
        (f"F6S        :  {f6s}", WHITE, 12, False),
        ("─"*74, CYAN, 10, False),
        (f"Location   :  {location}", GRAY, 12, False),
        ("Open to    :", GRAY, 12, False),
    ]
    if avail:
        for a in avail[:5]:
            rows.append((f"  ·  {a[:65]}", GRAY, 11, False))
    else:
        rows.append(("  ·  Advisory · Due Diligence · Architecture Reviews", GRAY, 11, False))
        rows.append(("  ·  Keynotes · Mentorship · AI for Good", GRAY, 11, False))
    rows.append(("─"*74, CYAN, 10, False))

    make_section_svg("section-contact.svg", "CONTACT", "[ F8 ]", rows)
    return '<a href="https://inetanel.com/contact"><img src="section-contact.svg" width="100%" alt="Contact"/></a>'




# ═════════════════════════════════════════════════════════════════
# README REWRITE
# ═════════════════════════════════════════════════════════════════

def rewrite_readme(articles, stats, projects, contact):
    with open(README_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    # Articles — regenerates section-articles.svg directly (no marker swap needed)
    build_articles_block(articles)

    # Projects — regenerates section-projects.svg directly
    build_projects_block(projects)

    # Contact — regenerates section-contact.svg directly
    build_contact_block(contact)

    # Stats — regenerate section-stats.svg with live numbers
    year = datetime.utcnow().year
    now  = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    rows = [
        (f"Stars      :  {stats['stars']:,}  ·  Followers  :  {stats['followers']:,}  ·  Repos  :  {stats['repos']:,}", "#ffff55", 12, False),
        (f"Commits {year}:  {stats['commits']:,}  ·  Pull Requests  :  {stats['prs']:,}  ·  Updated: {now}", "#55ffff", 11, False),
        ("─"*74, "#55ffff", 10, False),
    ]
    make_section_svg("section-stats.svg", "GITHUB STATS", "[ F9 ]", rows)

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

    print("── Generating trophies ──")
    svg3 = generate_trophies_svg(stats, days)
    with open("generated-trophies.svg", "w") as f: f.write(svg3)
    print("  saved generated-trophies.svg")

    print("── Articles ──")
    articles = fetch_articles()

    print("── Projects ──")
    projects = fetch_projects()

    print("── Contact ──")
    contact = fetch_contact()

    print("── Rewriting README ──")
    rewrite_readme(articles, stats, projects, contact)

    print("── Done ──")

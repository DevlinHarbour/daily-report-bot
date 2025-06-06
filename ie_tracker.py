import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from modules.load_config import load_config

TOTAL_CACHE = {}

# === Toggle for test mode ===
USE_FAKE_DATE = False
FAKE_TODAY = datetime(2024, 10, 9, 23, 59, 59)

def parse_date_safe(raw_date):
    if " - " in raw_date:
        raw_date = raw_date.split(" - ")[0].strip()
    try:
        return datetime.strptime(raw_date, "%m/%d/%Y")
    except:
        return None

def get_ie_alert_window(today):
    """Returns the start of the window to catch filings from yesterday + today."""
    window_start = (today - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return window_start, today

def parse_ie_table(url):
    response = requests.get(url)
    if response.status_code != 200:
        print(f"⚠️ Failed to fetch IE page for {url}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        print("⚠️ No tables found on the IE page")
        return []

    table = tables[-1]
    rows = table.find_all("tr")[1:]
    filings = []

    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 5:
            continue
        date = cols[0].text.strip()
        committee = cols[1].text.strip()
        position = cols[2].text.strip().upper()
        amount = cols[3].text.strip().replace("$", "").replace(",", "")
        desc = cols[4].text.strip()
        try:
            amount_num = float(amount)
        except:
            continue
        links = row.find_all("a")
        filing_link = links[-1] if links else None
        link = "https://cal-access.sos.ca.gov" + filing_link["href"] if filing_link else ""

        filings.append({
            "date": date,
            "committee": committee,
            "position": position,
            "amount": amount_num,
            "desc": desc,
            "url": link
        })

    return filings

def compute_totals(candidate_side, candidate_filings, opponent_filings):
    team_us = 0
    team_them = 0

    for f in candidate_filings:
        if f["position"] == "SUPPORT" and candidate_side == "us":
            team_us += f["amount"]
        elif f["position"] == "OPPOSE" and candidate_side == "us":
            team_them += f["amount"]
        elif f["position"] == "SUPPORT" and candidate_side == "them":
            team_them += f["amount"]
        elif f["position"] == "OPPOSE" and candidate_side == "them":
            team_us += f["amount"]

    for f in opponent_filings:
        if f["position"] == "OPPOSE" and candidate_side == "us":
            team_us += f["amount"]
        elif f["position"] == "SUPPORT" and candidate_side == "us":
            team_them += f["amount"]
        elif f["position"] == "OPPOSE" and candidate_side == "them":
            team_them += f["amount"]
        elif f["position"] == "SUPPORT" and candidate_side == "them":
            team_us += f["amount"]

    return int(team_us), int(team_them)

def track_ie_filings(candidate_config):
    candidate_name = candidate_config["name"]
    district = candidate_config["district"]
    side = candidate_config.get("side", "them")
    ie_url = candidate_config["ie_tracking"]["ie_url"]
    start_date = candidate_config["ie_tracking"]["start_date"]
    opponents = candidate_config.get("opponents", [])

    today = FAKE_TODAY if USE_FAKE_DATE else datetime.now()
    window_start, window_end = get_ie_alert_window(today)
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")

    config = load_config()

    # Always fetch fresh candidate filings for this candidate
    candidate_raw = parse_ie_table(ie_url)
    candidate_filings = [f for f in candidate_raw if parse_date_safe(f["date"]) and start_dt <= parse_date_safe(f["date"]) <= window_end]

    # Always fetch opponent filings
    opponent_raw = []
    for opponent_name in opponents:
        opponent = next((c for c in config["trackers"] if c["name"] == opponent_name), None)
        if opponent and opponent.get("ie_tracking", {}).get("enabled"):
            opponent_url = opponent["ie_tracking"]["ie_url"]
            opponent_raw += parse_ie_table(opponent_url)
    opponent_filings = [f for f in opponent_raw if parse_date_safe(f["date"]) and start_dt <= parse_date_safe(f["date"]) <= window_end]

    # Compute and cache totals (once per district)
    if district not in TOTAL_CACHE:
        team_us_total, team_them_total = compute_totals(side, candidate_filings, opponent_filings)
        TOTAL_CACHE[district] = {
            "totals": (team_us_total, team_them_total)
        }
    else:
        team_us_total, team_them_total = TOTAL_CACHE[district]["totals"]

    # Generate alerts from filings in the alert window (on this candidate's page only)
    alert_lines = []
    for f in candidate_filings:
        f_date = parse_date_safe(f["date"])
        if not f_date or not (window_start <= f_date <= window_end):
            continue

        is_us = (
            (f["position"] == "SUPPORT" and side == "us") or
            (f["position"] == "OPPOSE" and side == "them")
        )
        color = "🟩" if is_us else "🟥"

        amount_str = f"${int(f['amount']):,}"
        filing_line = f"{color} {district} | {f['position']} {candidate_name} → [{amount_str}]({f['url']})"
        totals_line = f"→ Totals: Team Us ${team_us_total:,} | Team Them ${team_them_total:,}"
        alert_lines.append(filing_line + "\n" + totals_line)

    return "\n".join(alert_lines) if alert_lines else None

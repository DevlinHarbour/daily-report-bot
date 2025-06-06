import json
import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

def load_config():
    with open("config.json", "r", encoding="utf-8") as f:
        return json.load(f)["trackers"]

def load_existing_data(candidate_name):
    path = f"./data/{candidate_name.replace(' ', '_')}.json"
    if not os.path.exists(path):
        return {
            "name": candidate_name,
            "district": "",
            "side": "",
            "type": "candidate",
            "fppc_filings": [],
            "press_clips": []
        }

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_candidate_data(candidate_name, data):
    path = f"./data/{candidate_name.replace(' ', '_')}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def scrape_fppc_filings(fppc_url):
    response = requests.get(fppc_url)
    if response.status_code != 200:
        return []

    soup = BeautifulSoup(response.content, 'html.parser')
    tables = soup.find_all('table', {'border': '3'})
    filings = []
    now = datetime.now()
    window = now - timedelta(hours=24)

    for table in tables:
        rows = table.find_all('tr')
        if len(rows) < 3:
            continue

        try:
            # Example: rows[2] holds form type and amount
            form_type = rows[2].find_all('td')[0].get_text(strip=True)  # e.g., "ORIGINAL FILING"
            amount = rows[2].find_all('td')[1].get_text(strip=True)
        except IndexError:
            form_type = "Unknown Filing"
            amount = "Amount Not Available"

        try:
            filed_on_raw = rows[1].find_all('td')[1].get_text(strip=True).replace("FILED ON:", "").strip()
            filed_on_date = datetime.strptime(filed_on_raw, "%m/%d/%Y %I:%M:%S %p")
        except (IndexError, ValueError):
            continue

        if filed_on_date >= window:
            try:
                filing_link = table.find('a', {'class': 'sublink5'})['href']
            except (AttributeError, TypeError):
                filing_link = ""

            filings.append({
                "date": filed_on_date.strftime("%Y-%m-%d"),
                "form": form_type,
                "amount": amount,
                "url": f"https://cal-access.sos.ca.gov{filing_link}"
            })

    return filings

def update_fppc_all():
    candidates = load_config()
    for cand in candidates:
        existing_data = load_existing_data(cand["name"])
        fppc_url = cand.get("fppc_url")
        if not fppc_url:
            continue

        # Scrape new filings
        new_filings = scrape_fppc_filings(fppc_url)

        # Always overwrite the FPPC filings with the fresh scraped data
        existing_data["fppc_filings"] = new_filings

        if new_filings:
            print(f"↪️ Updated FPPC filings for {cand['name']}: {len(new_filings)}")
        else:
            print(f"✔️ No FPPC filings in the last 24 hours for {cand['name']}")

        # Maintain core metadata (no changes here)
        existing_data["name"] = cand["name"]
        existing_data["district"] = cand["district"]
        existing_data["side"] = cand["side"]
        existing_data["type"] = "candidate"

        # Save the updated data to the JSON file
        save_candidate_data(cand["name"], existing_data)


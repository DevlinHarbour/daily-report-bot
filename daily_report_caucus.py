from modules.formatter_caucus import generate_caucus_digest
from modules.fppc_updater import update_fppc_all
from modules.press_scraper import fetch_press_clips
import markdown
import yagmail
from datetime import datetime

# === CONFIG ===
GMAIL_USER = ""
GMAIL_APP_PASSWORD = ""
RECIPIENT_EMAIL = [
    "",
    "",
    ""
]  
SEND_EMAIL = True

def build_daily_report():
    from modules.load_config import load_config
    trackers = load_config()["trackers"]
    press_clips = fetch_press_clips(trackers, hours_ago=24)
    return generate_caucus_digest(press_clips=press_clips)

def send_email_report():
    date = datetime.now().strftime("%B %d, %Y")
    subject = f"CA Assembly Target Digest Report – {date}"
    raw_body = build_daily_report()

    with open("output_caucus_report.txt", "w", encoding="utf-8") as f:
        f.write(raw_body)
    print("✅ Saved to output_caucus_report.txt")

    if not SEND_EMAIL:
        print("🚫 SEND_EMAIL is False — skipping email send.")
        return

    html_body = markdown.markdown(raw_body)

    yag = yagmail.SMTP(GMAIL_USER, GMAIL_APP_PASSWORD)
    yag.send(to=RECIPIENT_EMAIL, subject=subject, contents=html_body)
    print("✅ Email sent!")

if __name__ == "__main__":
    print("Updating FPPC filings...")
    update_fppc_all()

    print("📬 Sending caucus report...")
    send_email_report()

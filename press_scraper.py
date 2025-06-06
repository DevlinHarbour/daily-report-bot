import feedparser
import time
import json
import os
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from openai import OpenAI
from newspaper import Article
import trafilatura

# === CONFIGURATION ===
PAYWALL_USERNAME = "your_username_here"
PAYWALL_PASSWORD = "your_password_here"

PAYWALLED_DOMAINS = [
    "sacbee.com",
    "latimes.com",
    "fresnobee.com",
    "modbee.com",
    "sandiegouniontribune.com",
    "nytimes.com",
    "wsj.com",
    "washingtonpost.com"
]

CHROMEDRIVER_PATH = r"PUT PATH HERE"
CACHE_FILE = "resolved_url_cache.json"

# Load cached URLs
if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, "r") as f:
        url_cache = json.load(f)
else:
    url_cache = {}

def save_cache():
    with open(CACHE_FILE, "w") as f:
        json.dump(url_cache, f)

def init_openai_client(api_key="OPEN AI KEY"):
    return OpenAI(api_key=api_key)

def login_to_paywalled_site(driver, domain):
    try:
        login_url = f"https://www.{domain}/login"
        driver.get(login_url)
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.NAME, "username")))

        driver.find_element(By.NAME, "username").send_keys(PAYWALL_USERNAME)
        driver.find_element(By.NAME, "password").send_keys(PAYWALL_PASSWORD)
        driver.find_element(By.XPATH, "//button[@type='submit']").click()

        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        print(f"🔐 Logged into paywalled site: {domain}")
    except Exception as e:
        print(f"⚠️ Paywall login failed for {domain}: {e}")

def get_selenium_driver():
    options = webdriver.ChromeOptions()
    options.add_argument('--log-level=3')
    options.add_experimental_option('excludeSwitches', ['enable-logging'])
    service = Service(CHROMEDRIVER_PATH)
    return webdriver.Chrome(service=service, options=options)

def resolve_final_url(url):
    if url in url_cache:
        print(f"🔗 URL resolved from cache: {url_cache[url]}")
        return url_cache[url]

    driver = get_selenium_driver()
    try:
        driver.get(url)
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(3)

        try:
            canonical = driver.find_element(By.XPATH, "//link[@rel='canonical']").get_attribute("href")
            final_url = canonical if canonical else driver.current_url
        except:
            final_url = driver.current_url

        url_cache[url] = final_url
        save_cache()
        print(f"🔗 URL resolved and cached: {final_url}")
        return final_url

    except Exception as e:
        print(f"⚠️ Error resolving URL: {e}")
        return url
    finally:
        driver.quit()

def extract_article_text(url):
    try:
        article = Article(url)
        article.download()
        article.parse()
        if len(article.text.split()) > 50:
            return article.text, "newspaper3k"
    except:
        pass

    try:
        downloaded = trafilatura.fetch_url(url)
        result = trafilatura.extract(downloaded)
        if result and len(result.split()) > 50:
            return result, "trafilatura"
    except:
        pass

    driver = get_selenium_driver()
    try:
        for domain in PAYWALLED_DOMAINS:
            if domain in url:
                login_to_paywalled_site(driver, domain)
                break

        driver.get(url)
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(3)
        body_text = driver.find_element(By.TAG_NAME, "article").text
        if len(body_text.split()) > 50:
            return body_text, "selenium"
    except:
        pass
    finally:
        driver.quit()

    return None, "none"

def get_summary_from_openai(client, url, candidate_name):
    article_text, extractor_used = extract_article_text(url)
    if not article_text:
        return "Summary unavailable."

    prompt = f"Summarize this news article about {candidate_name} in 1–2 sentences:\n\n{article_text}"
    response = client.chat.completions.create(model="gpt-4", messages=[{"role": "user", "content": prompt}], max_tokens=100, temperature=0.5)
    return response.choices[0].message.content.strip()

def fetch_press_clips(trackers, hours_ago=72, openai_client=None):
    clips = []
    now = datetime.now()
    threshold = timedelta(hours=hours_ago)
    client = openai_client or init_openai_client()

    SKIP_KEYWORDS = ["obituary", "funeral", "passed away", "death notice"]

    for tracker in trackers:
        for term in tracker.get("search_terms", []):
            rss_url = f"https://news.google.com/rss/search?q={term.replace(' ', '+')}&hl=en-US&gl=US&ceid=US:en"
            feed = feedparser.parse(rss_url)

            for entry in feed.entries:
                if any(word in entry.title.lower() for word in SKIP_KEYWORDS):
                    continue

                published = datetime(*entry.published_parsed[:6])
                if now - published > threshold:
                    continue

                url = resolve_final_url(entry.link)
                summary = get_summary_from_openai(client, url, tracker["name"])

                clips.append({
                    "candidate": tracker["name"],
                    "title": entry.title,
                    "url": url,
                    "snippet": summary,
                    "date": published.strftime("%Y-%m-%d")
                })

                time.sleep(3)

    return clips

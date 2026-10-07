print("1. File started")
from rag_pipeline import ingest_document
print("2. Imported rag_pipeline")
import time
import schedule
import hashlib
import os
from url_scraper import scrape_website
print("3. Imported url_scraper")


URL = "https://books.toscrape.com/"   # Replace with your actual website

HASH_FILE = "website_hash.txt"

def get_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def job():
    print("Running scheduled scraping...")

    text = scrape_website(URL)

    if text == "Could not fetch website.":
        print("Website could not be reached. Skipping update.")
        return

    new_hash = get_hash(text)

    old_hash = None
    if os.path.exists(HASH_FILE):
        with open(HASH_FILE, "r") as f:
            old_hash = f.read().strip()

    if new_hash == old_hash:
        print("No website changes detected.")
        return

    print("Website changed. Updating files...")

    with open("website_content.txt", "w", encoding="utf-8") as f:
        f.write(text)

    with open(HASH_FILE, "w") as f:
        f.write(new_hash)
    
    print("Rebuilding Chroma database...")
    ingest_document("website_content.txt")
    print("Chroma database updated.")

    print("Website content updated.")

schedule.every().day.at("02:00").do(job)

print("4. About to call job()")
job()
print("5. Finished")
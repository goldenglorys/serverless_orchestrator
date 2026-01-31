import logging
import csv
import io
import re
from datetime import datetime
import httpx
from bs4 import BeautifulSoup

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def fetch_all_rsrch_data():
    """
    Fetches ALL links from rsrch.space using the specific HTML structure
    to extract the original date and title.
    """
    url = "https://rsrch.space/"
    logger.info(f"Connecting to {url}...")

    try:
        # 1. Fetch the raw HTML
        # We use a large timeout because loading a large page might take time
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        response = httpx.get(url, timeout=60.0, follow_redirects=True, headers=headers)
        response.raise_for_status()

        logger.info("Page downloaded. Parsing HTML...")
        soup = BeautifulSoup(response.text, 'html.parser')

        links_data = []

        # 2. Target the specific Row Container
        # Based on your previous code/HTML, rows look like:
        # <div class="flex items-start justify-between py-1 gap-4">
        rows = soup.find_all('div', class_=lambda x: x and 'flex' in x and 'justify-between' in x and 'gap-4' in x)

        logger.info(f"Found {len(rows)} potential entry rows. Processing...")

        for row in rows:
            try:
                # A. Extract Title and URL (from the <a> tag)
                a_tag = row.find('a', href=True)
                if not a_tag:
                    continue

                href = a_tag.get('href', '')
                title = a_tag.get_text(strip=True)

                # Filters
                if not href or href.startswith('#'): continue
                if 'favicon' in href or 'ishanshah.me' in href: continue

                # B. Extract Original Date
                # We look for the <p> tag with class 'font-berkeley' inside this specific row
                original_date = "Unknown"
                date_tag = row.find('p', class_=lambda x: x and 'font-berkeley' in x)
                
                if date_tag:
                    original_date = date_tag.get_text(strip=True)
                
                # C. Extract Domain (cleanup)
                domain = ""
                domain_match = re.search(r'https?://([^/]+)', href)
                if domain_match:
                    domain = domain_match.group(1).replace('www.', '')

                # D. Append Data
                links_data.append({
                    'title': title,
                    'url': href,
                    'domain': domain,
                    'original_date': original_date,       # The date from the website (2026-01-22)
                    'created_at': datetime.now().isoformat() # When we scraped it
                })

            except Exception as row_err:
                logger.warning(f"Skipping a row due to error: {row_err}")
                continue

        logger.info(f"Successfully extracted {len(links_data)} items.")
        return links_data

    except Exception as e:
        logger.error(f"Critical error fetching data: {e}")
        return []

if __name__ == "__main__":
    # 1. Run the scraper
    data = fetch_all_rsrch_data()

    if data:
        # 2. Save to CSV
        filename = "rsrch_full_dump.csv"
        
        # CSV Headers
        fieldnames = ['title', 'url', 'domain', 'original_date', 'created_at']

        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)
        
        print("\n" + "="*50)
        print(f"✅ DONE! Saved {len(data)} rows to '{filename}'")
        print("="*50 + "\n")
    else:
        print("❌ No data found.")
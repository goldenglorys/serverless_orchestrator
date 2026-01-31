import csv
import re
import sys
from urllib.parse import urlparse
from datetime import datetime

# --- CONFIGURATION ---
SCRAPED_FILE = 'rsrch_full_dump.csv'  # New dump
LINKS_FILE = 'links_rows.csv'              # Old links
PAPERS_FILE = 'papers_rows.csv'            # Old papers
OUTPUT_FILE = 'missing_content_final.csv'

def normalize_url(url):
    """Cleans URL for matching (ignore http/s, www, trailing slash)."""
    if not url: return ""
    url = url.lower().strip()
    url = re.sub(r'^https?://', '', url)
    url = re.sub(r'^www\.', '', url)
    return url.rstrip('/')

def normalize_title(title):
    """Cleans title for matching (ignore special chars, case)."""
    if not title: return ""
    title = title.lower()
    title = re.sub(r'[^a-z0-9\s]', '', title)
    return re.sub(r'\s+', ' ', title).strip()

def get_clean_domain(url):
    """Extracts domain from URL (e.g., 'sub.example.com' -> 'example.com')."""
    if not url: return ""
    try:
        # Add http if missing for urlparse to work
        if not url.startswith(('http://', 'https://')):
            url = 'http://' + url
        parsed = urlparse(url)
        domain = parsed.netloc.replace('www.', '')
        return domain
    except:
        return ""

def format_date(iso_string):
    """Converts ISO timestamp (2023-10-24T10:00:00...) to YYYY-MM-DD."""
    if not iso_string:
        return ""
    try:
        # Split by T usually works for Supabase/Notion timestamps
        return iso_string.split('T')[0]
    except:
        return iso_string

def load_reference_set(filename):
    """Loads the new full dump to know what we already have."""
    urls = set()
    titles = set()
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('url'):
                    urls.add(normalize_url(row['url']))
                if row.get('title'):
                    titles.add(normalize_title(row['title']))
    except FileNotFoundError:
        print(f"❌ Error: Could not find {filename}")
        sys.exit(1)
    return urls, titles

def process_old_file(filename, file_type, existing_urls, existing_titles):
    missing_items = []
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                
                # 1. Normalization for Check
                u_norm = normalize_url(row.get('url', ''))
                t_norm = normalize_title(row.get('title', ''))

                # 2. Check if exists in new dump
                if u_norm in existing_urls or t_norm in existing_titles:
                    continue # It's already in the new system, skip it

                # 3. Extract Data for Result
                raw_url = row.get('url', '')
                
                # MAP: notion_timestamp -> original_date
                notion_ts = row.get('notion_timestamp', '')
                # Fallback to created_at if notion is missing
                if not notion_ts:
                    notion_ts = row.get('created_at', '')
                
                final_date = format_date(notion_ts)

                # MAP: authors (Only exists in papers, empty in links)
                authors = row.get('authors', '')
                if file_type == 'links':
                    authors = "" # Links don't have authors
                
                # 4. Create Entry
                entry = {
                    'title': row.get('title', '').strip(),
                    'url': raw_url,
                    'domain': get_clean_domain(raw_url),
                    'original_date': final_date,
                    'authors': authors
                }
                
                # Basic validation
                if entry['url']:
                    missing_items.append(entry)

    except FileNotFoundError:
        print(f"⚠️ Warning: Could not find {filename}")

    return missing_items

def main():
    print("--- Extracting Missing Content ---")
    
    # 1. Load the new dump (The Reference)
    ex_urls, ex_titles = load_reference_set(SCRAPED_FILE)
    print(f"Loaded reference dump: {len(ex_urls)} items.")

    # 2. Process Papers (Has authors)
    print("Processing papers.csv...")
    missing_papers = process_old_file(PAPERS_FILE, 'papers', ex_urls, ex_titles)

    # 3. Process Links (No authors)
    print("Processing links.csv...")
    missing_links = process_old_file(LINKS_FILE, 'links', ex_urls, ex_titles)

    # 4. Combine
    all_missing = missing_papers + missing_links

    # 5. Write Result
    headers = ['title', 'url', 'domain', 'original_date', 'authors']
    
    with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(all_missing)

    print("\n" + "="*40)
    print(f"✅ DONE. Found {len(all_missing)} items that were missing.")
    print(f"📄 Saved to: {OUTPUT_FILE}")
    print("="*40 + "\n")

if __name__ == "__main__":
    main()
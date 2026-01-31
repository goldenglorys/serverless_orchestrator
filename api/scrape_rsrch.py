import logging
import json
from http.server import BaseHTTPRequestHandler
from typing import List, Dict, Any, Set
from dotenv import load_dotenv
from datetime import datetime
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()


def fetch_rsrch_links(limit: int = 1000) -> List[Dict[str, Any]]:
    """
    Fetches top links from rsrch.space and extracts structured data.
    Limited to prevent timeouts.
    """
    import httpx
    from bs4 import BeautifulSoup

    logger.info(f"Fetching top {limit} links from rsrch.space...")

    try:
        response = httpx.get("https://rsrch.space/", timeout=30.0, follow_redirects=True)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        # Find all link elements
        links = []
        link_elements = soup.find_all('a', href=True)

        # Get current date in YYYY-MM-DD format
        current_date = datetime.now().strftime('%Y-%m-%d')

        # Process only up to the limit
        for a_tag in link_elements[:limit]:
            href = a_tag.get('href', '')

            # Skip internal navigation links and empty hrefs
            if not href or href.startswith('#') or href.startswith('/'):
                continue

            # Skip the favicon URLs
            if 'favicon' in href.lower() or 'icon' in href.lower():
                continue

            # Filter out ishanshah.me
            if 'ishanshah.me' in href:
                continue

            # Extract title (text content of the link)
            title = a_tag.get_text(strip=True)

            # Skip if no title
            if not title:
                continue

            # Extract domain
            domain_match = re.search(r'https?://([^/]+)', href)
            domain = domain_match.group(1) if domain_match else ''

            links.append({
                'url': href,
                'title': title,
                'date': current_date,  # Use current date
                'domain': domain
            })

        logger.info(f"Extracted {len(links)} links from rsrch.space")
        return links

    except Exception as e:
        logger.error(f"Error fetching rsrch.space: {e}")
        return []


def get_existing_urls_from_supabase() -> Set[str]:
    """
    Fetches all existing URLs from Supabase 'papers' and 'links' tables.
    """
    from utils.notion_supabase_sync import supabase_client

    existing_urls = set()

    try:
        # Fetch from papers table
        logger.info("Fetching existing URLs from 'papers' table...")
        papers_response = supabase_client.table("papers").select("url").execute()
        for item in papers_response.data:
            if item.get('url'):
                existing_urls.add(item['url'])

        # Fetch from links table
        logger.info("Fetching existing URLs from 'links' table...")
        links_response = supabase_client.table("links").select("url").execute()
        for item in links_response.data:
            if item.get('url'):
                existing_urls.add(item['url'])

        logger.info(f"Found {len(existing_urls)} existing URLs in Supabase")
        return existing_urls

    except Exception as e:
        logger.error(f"Error fetching existing URLs from Supabase: {e}")
        return set()


def categorize_and_sync_links(unique_links: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Categorizes links (arxiv → papers, others → links) and syncs to Supabase.
    Checks database for existing URLs before inserting to avoid duplicates.
    Returns statistics about the sync.
    """
    from utils.notion_supabase_sync import supabase_client

    papers_to_insert = []
    links_to_insert = []
    seen_urls = set()  # Track URLs within this batch to avoid duplicates

    # Categorize links and deduplicate within the batch
    for link in unique_links:
        url = link.get('url')

        # Skip if we've already seen this URL in the current batch
        if url in seen_urls:
            logger.warning(f"Skipping duplicate URL in batch: {url}")
            continue

        seen_urls.add(url)
        domain = link.get('domain', '').lower()

        # Check if it's from arxiv
        if 'arxiv.org' in domain:
            # Prepare for papers table
            paper_data = {
                'title': link.get('title'),
                'url': url,
                'date': link.get('date'),
                'authors': '',  # Leave blank for now
                'notion_timestamp': datetime.now().isoformat()
            }
            papers_to_insert.append(paper_data)
        else:
            # Prepare for links table
            link_data = {
                'title': link.get('title'),
                'url': url,
                'notion_timestamp': datetime.now().isoformat()
            }
            links_to_insert.append(link_data)

    stats = {
        'papers_synced': 0,
        'links_synced': 0,
        'papers_failed': 0,
        'links_failed': 0,
        'papers_skipped': 0,
        'links_skipped': 0
    }

    # Insert papers - check each URL individually to avoid duplicates
    if papers_to_insert:
        logger.info(f"Checking {len(papers_to_insert)} papers against database...")

        actually_inserted = 0
        for paper in papers_to_insert:
            url = paper['url']

            # Check if URL already exists in papers table
            try:
                existing = supabase_client.table("papers").select("url").eq("url", url).execute()

                if existing.data and len(existing.data) > 0:
                    # logger.info(f"⏭️  Skipping duplicate paper: {paper['title'][:50]}...")
                    stats['papers_skipped'] += 1
                else:
                    # URL doesn't exist, safe to insert
                    try:
                        supabase_client.table("papers").insert(paper).execute()
                        actually_inserted += 1
                        # logger.info(f"✅ Inserted paper: {paper['title'][:50]}...")
                    except Exception as e:
                        logger.error(f"❌ Failed to insert paper: {e}")
                        stats['papers_failed'] += 1

            except Exception as e:
                logger.error(f"Error checking paper URL {url}: {e}")
                stats['papers_failed'] += 1

        stats['papers_synced'] = actually_inserted
        logger.info(f"✅ Papers sync complete: {actually_inserted} inserted, {stats['papers_skipped']} skipped")

    # Insert links - check each URL individually to avoid duplicates
    if links_to_insert:
        logger.info(f"Checking {len(links_to_insert)} links against database...")

        actually_inserted = 0
        for link in links_to_insert:
            url = link['url']

            # Check if URL already exists in links table
            try:
                existing = supabase_client.table("links").select("url").eq("url", url).execute()

                if existing.data and len(existing.data) > 0:
                    # logger.info(f"⏭️  Skipping duplicate link: {link['title'][:50]}...")
                    stats['links_skipped'] += 1
                else:
                    # URL doesn't exist, safe to insert
                    try:
                        supabase_client.table("links").insert(link).execute()
                        actually_inserted += 1
                        # logger.info(f"✅ Inserted link: {link['title'][:50]}...")
                    except Exception as e:
                        logger.error(f"❌ Failed to insert link: {e}")
                        stats['links_failed'] += 1

            except Exception as e:
                logger.error(f"Error checking link URL {url}: {e}")
                stats['links_failed'] += 1

        stats['links_synced'] = actually_inserted
        logger.info(f"✅ Links sync complete: {actually_inserted} inserted, {stats['links_skipped']} skipped")

    return stats


def send_sync_notification(stats: Dict[str, Any], total_scraped: int, total_duplicates: int):
    """
    Sends a Telegram notification with sync statistics.
    """
    from utils.notify import send_telegram_message

    total_synced = stats['papers_synced'] + stats['links_synced']
    total_skipped = stats['papers_skipped'] + stats['links_skipped']
    total_failed = stats['papers_failed'] + stats['links_failed']

    message = f"""🔄 rsrch.space Sync Completed

📊 Scraping Stats:
  • Total scraped: {total_scraped}
  • Pre-filtered duplicates: {total_duplicates}

📚 Papers (arxiv.org):
  • Inserted: {stats['papers_synced']}
  • Skipped (already exist): {stats['papers_skipped']}
  • Failed: {stats['papers_failed']}

🔗 Links (other sources):
  • Inserted: {stats['links_synced']}
  • Skipped (already exist): {stats['links_skipped']}
  • Failed: {stats['links_failed']}

✅ Total inserted: {total_synced}
⏭️  Total skipped: {total_skipped}
"""

    try:
        send_telegram_message(message)
        logger.info("Telegram notification sent successfully")
    except Exception as e:
        logger.error(f"Error sending Telegram notification: {e}")


class handler(BaseHTTPRequestHandler):
    """Handler for scraping rsrch.space and syncing to Supabase."""

    def do_GET(self) -> None:
        """Handle GET requests."""

        try:
            logger.info("Starting rsrch.space scraping and sync process...")

            # Step 1: Fetch ALL links from rsrch.space
            scraped_links = fetch_rsrch_links()

            # Step 2: Get existing URLs from Supabase
            existing_urls = get_existing_urls_from_supabase()

            # Step 3: Filter duplicates
            unique_links = []
            duplicate_count = 0
            for link in scraped_links:
                url = link.get('url')
                if url and url not in existing_urls:
                    unique_links.append(link)
                else:
                    duplicate_count += 1

            logger.info(f"Found {len(unique_links)} unique links, {duplicate_count} duplicates")

            # Step 4: Categorize and sync to Supabase
            sync_stats = categorize_and_sync_links(unique_links)

            # Step 5: Send Telegram notification
            send_sync_notification(sync_stats, len(scraped_links), duplicate_count)

            # Prepare response
            response_data = {
                "status": "success",
                "total_scraped": len(scraped_links),
                "total_existing_in_db": len(existing_urls),
                "total_duplicates": duplicate_count,
                "total_unique": len(unique_links),
                "categorization": {
                    "papers": sync_stats['papers_synced'] + sync_stats['papers_failed'],
                    "links": sync_stats['links_synced'] + sync_stats['links_failed']
                },
                "sync_stats": sync_stats
            }

            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response_data, indent=2).encode())

        except Exception as e:
            logger.error(f"Error in scrape_rsrch handler: {e}")

            error_response = {
                "status": "error",
                "error": str(e)
            }

            self.send_response(500)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(error_response).encode())

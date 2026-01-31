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


def fetch_rsrch_links(limit: int = None) -> List[Dict[str, Any]]:
    """
    Fetches links from rsrch.space and extracts structured data.
    Set limit=None to fetch ALL links, or specify a number to limit.
    Default is None (no limit).
    """
    import httpx
    from bs4 import BeautifulSoup

    if limit is None:
        logger.info(f"Fetching ALL links from rsrch.space...")
    else:
        logger.info(f"Fetching top {limit} links from rsrch.space...")

    try:
        response = httpx.get(
            "https://rsrch.space/", timeout=30.0, follow_redirects=True
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # Find all link elements
        links = []
        link_elements = soup.find_all("a", href=True)

        # Get current date in YYYY-MM-DD format
        current_date = datetime.now().strftime("%Y-%m-%d")

        # Process with or without limit
        elements_to_process = link_elements if limit is None else link_elements[:limit]

        for a_tag in elements_to_process:
            href = a_tag.get("href", "")

            # Skip internal navigation links and empty hrefs
            if not href or href.startswith("#") or href.startswith("/"):
                continue

            # Skip the favicon URLs
            if "favicon" in href.lower() or "icon" in href.lower():
                continue

            # Filter out ishanshah.me
            if "ishanshah.me" in href:
                continue

            # Extract title (text content of the link)
            title = a_tag.get_text(strip=True)

            # Skip if no title
            if not title:
                continue

            # Extract domain
            domain_match = re.search(r"https?://([^/]+)", href)
            domain = domain_match.group(1) if domain_match else ""

            links.append(
                {
                    "url": href,
                    "title": title,
                    "date": current_date,  # Use current date
                    "domain": domain,
                }
            )

        logger.info(f"Extracted {len(links)} links from rsrch.space")
        return links

    except Exception as e:
        logger.error(f"Error fetching rsrch.space: {e}")
        return []


def get_existing_urls_from_supabase() -> Set[str]:
    """
    Fetches all existing URLs from Supabase 'scrape' table.
    """
    from utils.notion_supabase_sync import supabase_client

    existing_urls = set()
    try:
        logger.info("Fetching existing URLs from 'scrape' table...")
        response = supabase_client.table("scrape").select("url").execute()
        for item in response.data:
            if item.get("url"):
                existing_urls.add(item["url"])
        logger.info(f"Found {len(existing_urls)} existing URLs in Supabase")
        return existing_urls
    except Exception as e:
        logger.error(f"Error fetching existing URLs from Supabase: {e}")
        return set()


def categorize_and_sync_links(unique_links: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Prepares and syncs new links to the 'scrape' table in Supabase.
    """
    from utils.notion_supabase_sync import supabase_client

    items_to_insert = []
    for link in unique_links:
        item_data = {
            "title": link.get("title"),
            "url": link.get("url"),
            "domain": link.get("domain"),
            "original_date": link.get(
                "date"
            ),  # This is already the current date from the fetch function
            "authors": None,  # No authors from rsrch.space
        }
        items_to_insert.append(item_data)

    stats = {"items_synced": 0, "items_failed": 0}
    if not items_to_insert:
        return stats

    try:
        logger.info(
            f"Inserting {len(items_to_insert)} new items into 'scrape' table..."
        )
        # This performs an "INSERT...ON CONFLICT DO NOTHING"
        supabase_client.table("scrape").upsert(
            items_to_insert, on_conflict="url"
        ).execute()

        stats["items_synced"] = len(items_to_insert)
        logger.info(f"✅ Sync complete: {stats['items_synced']} items inserted.")
    except Exception as e:
        logger.error(f"❌ Failed to insert items: {e}")
        stats["items_failed"] = len(items_to_insert)

    return stats

def send_sync_notification(
    stats: Dict[str, Any], total_scraped: int, total_duplicates: int
):
    """
    Sends a Telegram notification with sync statistics.
    """
    from utils.notify import send_telegram_message

    message = f"""🔄 rsrch.space Sync Completed

📊 Scraping Stats:
  • Links Scraped: {total_scraped}
  • Duplicates Found: {total_duplicates}

✅ New Items Inserted: {stats.get('items_synced', 0)}
❌ Failed Inserts: {stats.get('items_failed', 0)}
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
            # Parse query parameters for limit
            from urllib.parse import urlparse, parse_qs

            parsed_url = urlparse(self.path)
            query_params = parse_qs(parsed_url.query)

            # Get limit from query params (default: None = no limit)
            # Use limit=1000 for cron job to prevent timeouts
            limit_param = query_params.get("limit", [None])[0]
            limit = int(limit_param) if limit_param else 1000

            logger.info("Starting rsrch.space scraping and sync process...")

            # Step 1: Fetch links from rsrch.space (with or without limit)
            scraped_links = fetch_rsrch_links(limit=limit)

            # Step 2: Get existing URLs from Supabase
            existing_urls = get_existing_urls_from_supabase()

            # Step 3: Filter duplicates
            unique_links = []
            duplicate_count = 0
            for link in scraped_links:
                url = link.get("url")
                if url and url not in existing_urls:
                    unique_links.append(link)
                else:
                    duplicate_count += 1

            logger.info(
                f"Found {len(unique_links)} unique links, {duplicate_count} duplicates"
            )

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
                "sync_stats": sync_stats,
            }

            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response_data, indent=2).encode())

        except Exception as e:
            logger.error(f"Error in scrape_rsrch handler: {e}")

            error_response = {"status": "error", "error": str(e)}

            self.send_response(500)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(error_response).encode())

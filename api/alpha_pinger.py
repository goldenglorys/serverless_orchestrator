import requests
import logging
import json
from http.server import BaseHTTPRequestHandler
from typing import Optional
from utils.notion_supabase_sync import main as sync_data, ping_supabase
from utils.notify import send_telegram_message
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)

# Load environment variables
load_dotenv()


class AlphaPinger:
    """Class to ping a website and check its status."""

    def __init__(self, url: str) -> None:
        """Initialize the WebsitePinger with the website URL."""
        self.url = url

    def get_website_status(self) -> Optional[int]:
        """Ping the website and return its status code."""
        try:
            response = requests.get(self.url)
            response.raise_for_status()
            return response.status_code
        except requests.exceptions.RequestException as e:
            logging.error(f"Error pinging website {self.url}: {e}")
            return None


class handler(BaseHTTPRequestHandler):
    """Handler for incoming HTTP requests."""

    def do_GET(self) -> None:
        """Handle GET requests."""

        # Ping Supabase tables
        try:
            papers_ping = ping_supabase("papers")
            papers_status = "success"
            papers_fetched = len(papers_ping)
        except Exception as e:
            logging.error(f"Error pinging Supabase papers table: {e}")
            papers_status = "error"
            papers_fetched = None

        try:
            links_ping = ping_supabase("links")
            links_status = "success"
            links_fetched = len(links_ping)
        except Exception as e:
            logging.error(f"Error pinging Supabase links table: {e}")
            links_status = "error"
            links_fetched = None

        # Run Notion to Supabase sync
        try:
            sync_data()
            sync_status = "success"
            send_telegram_message(
                "The Notion to Supabase sync job completed successfully."
            )
        except Exception as e:
            logging.error(f"Error syncing data: {e}")
            sync_status = "error"
            send_telegram_message(
                "There was an error in the Notion to Supabase sync job."
            )

        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.end_headers()

        response_data = {
            "supabase_ping": {
                "papers_table": {
                    "status": papers_status,
                    "records_fetched": papers_fetched,
                },
                "links_table": {
                    "status": links_status,
                    "records_fetched": links_fetched,
                },
            },
            "notion_supabase_sync": {"status": sync_status},
        }

        self.wfile.write(json.dumps(response_data).encode())

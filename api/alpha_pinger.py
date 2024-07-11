import requests
import logging
import json
from http.server import BaseHTTPRequestHandler
from typing import Optional
from utils.notion_supabase_sync import main as sync_data
import os
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)

# Load environment variables
load_dotenv()
ALPHA_URL = os.getenv("ALPHA_URL")

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
        website_pinger = AlphaPinger(ALPHA_URL)
        website_status = website_pinger.get_website_status()

        # Run Notion to Supabase sync
        try:
            sync_data()
            sync_status = "success"
        except Exception as e:
            logging.error(f"Error syncing data: {e}")
            sync_status = "error"

        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.end_headers()

        response_data = {
            "website_ping": {
                "status": "success" if website_status else "error",
                "code": website_status if website_status else None,
            },
            "notion_supabase_sync": {"status": sync_status},
        }

        self.wfile.write(json.dumps(response_data).encode())

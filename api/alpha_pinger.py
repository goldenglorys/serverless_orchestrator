import requests
import logging
import json
from http.server import BaseHTTPRequestHandler
from typing import Optional

logging.basicConfig(level=logging.INFO)


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
        website_pinger = AlphaPinger("https://alpha.gloryolusola.com")
        website_status = website_pinger.get_website_status()

        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.end_headers()

        if website_status:
            response_data = {"status": "success", "code": website_status}
        else:
            response_data = {"status": "error", "message": "Failed to ping website"}

        self.wfile.write(json.dumps(response_data).encode())

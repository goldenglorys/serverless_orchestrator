"""
TEMPORARY — delete this file after the initial seed is confirmed.

One-shot endpoint: fetches catalog.md and inserts all current entries into
Supabase, deduplicating by (company_lab, technique_research).
Safe to call multiple times — already-present rows are skipped.

Hit: GET /api/seed_chinese_frontier
"""

import json
import logging
import sys
import os
from http.server import BaseHTTPRequestHandler

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            from scrape_chinese_frontier import run_scrape_and_sync
            result = run_scrape_and_sync()
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(result, indent=2).encode())
        except Exception as e:
            logger.error(f"Seed handler error: {e}")
            self.send_response(500)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "error", "error": str(e)}).encode())

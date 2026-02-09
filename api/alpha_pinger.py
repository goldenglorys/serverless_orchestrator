import logging
import json
from http.server import BaseHTTPRequestHandler
from typing import Dict, Any

from utils.notion_supabase_sync import (
    main as sync_data,
    ping_supabase_table,
    supabase_client,
)
from utils.notify import send_telegram_message
from dotenv import load_dotenv

# Import the scraping function from scrape_rsrch
import sys
import os

# Add the api directory to path to allow importing scrape_rsrch
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scrape_rsrch import run_scrape_and_sync

logging.basicConfig(level=logging.INFO)

# Load environment variables
load_dotenv()


def _ping_and_get_status(
    client: Any, table_name: str, account_name: str
) -> Dict[str, Any]:
    """Helper function to ping a Supabase table and return its status."""
    try:
        ping_result = ping_supabase_table(client, table_name)
        if ping_result is None:
            raise ConnectionError(
                f"Failed to connect to {account_name} table {table_name}"
            )

        return {
            "status": "success",
            "records_fetched": len(ping_result),
        }
    except Exception as e:
        logging.error(f"Error pinging {account_name} table '{table_name}': {e}")
        return {
            "status": "error",
            "records_fetched": None,
        }


class handler(BaseHTTPRequestHandler):
    """Handler for incoming HTTP requests."""

    def do_GET(self) -> None:
        """Handle GET requests."""
        sync_status = "success"

        # Ping Supabase tables first
        # papers_status = _ping_and_get_status(supabase_client, "papers", "account_1")
        # links_status = _ping_and_get_status(supabase_client, "links", "account_1")
        scrape_status = _ping_and_get_status(supabase_client, "scrape", "account_1")

        # Run Notion to Supabase sync. If it fails, stop and report.
        sync_stats = {"papers_synced": 0, "links_synced": 0}
        try:
            sync_stats = sync_data()
            total_synced = sync_stats["papers_synced"] + sync_stats["links_synced"]

            message = f"""✅ Notion to Supabase Sync Completed

📊 Sync Statistics:
  • Papers synced: {sync_stats["papers_synced"]}
  • Links synced: {sync_stats["links_synced"]}
  • Total synced: {total_synced}
"""
            send_telegram_message(message)
        except Exception as e:
            logging.error(f"Critical error during data sync: {e}")
            sync_status = "error"
            send_telegram_message(
                f"❌ CRITICAL: The Notion to Supabase sync job failed. Error: {e}"
            )
            # Do not proceed further if sync fails.

        # Run rsrch.space scraping and syncing
        scrape_rsrch_stats = {"status": "not_run"}
        try:
            logging.info("Starting rsrch.space scraping process...")
            scrape_rsrch_stats = run_scrape_and_sync(limit=1000)
            logging.info(f"rsrch.space scraping completed: {scrape_rsrch_stats.get('status')}")
        except Exception as e:
            logging.error(f"Error during rsrch.space scraping: {e}")
            scrape_rsrch_stats = {"status": "error", "error": str(e)}
            send_telegram_message(
                f"⚠️ rsrch.space scraping failed. Error: {e}"
            )

        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.end_headers()

        response_data = {
            "supabase_ping": {
                "scrape_table": scrape_status,
                # "account_1": {
                #     "papers_table": papers_status,
                #     "links_table": links_status,
                # },
            },
            "notion_supabase_sync": {"status": sync_status, "stats": sync_stats},
            "rsrch_space_scraping": scrape_rsrch_stats,
        }

        self.wfile.write(json.dumps(response_data).encode())

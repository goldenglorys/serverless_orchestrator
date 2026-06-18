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

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scrape_rsrch import run_scrape_and_sync
from scrape_chinese_frontier import run_scrape_and_sync as sync_chinese_frontier

logging.basicConfig(level=logging.INFO)
load_dotenv()


def _ping_and_get_status(client: Any, table_name: str, account_name: str) -> Dict[str, Any]:
    try:
        ping_result = ping_supabase_table(client, table_name)
        if ping_result is None:
            raise ConnectionError(f"Failed to connect to {account_name} table {table_name}")
        return {"status": "success", "records_fetched": len(ping_result)}
    except Exception as e:
        logging.error(f"Error pinging {account_name} table '{table_name}': {e}")
        return {"status": "error", "records_fetched": None}


class handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        sync_status = "success"

        scrape_status = _ping_and_get_status(supabase_client, "scrape", "account_1")

        # 1. Notion → Supabase sync
        sync_stats = {"papers_synced": 0, "links_synced": 0}
        try:
            sync_stats = sync_data()
            total_synced = sync_stats["papers_synced"] + sync_stats["links_synced"]
            send_telegram_message(
                f"✅ Notion to Supabase Sync Completed\n\n"
                f"📊 Sync Statistics:\n"
                f"  • Papers synced: {sync_stats['papers_synced']}\n"
                f"  • Links synced: {sync_stats['links_synced']}\n"
                f"  • Total synced: {total_synced}"
            )
        except Exception as e:
            logging.error(f"Critical error during data sync: {e}")
            sync_status = "error"
            send_telegram_message(f"❌ CRITICAL: Notion to Supabase sync failed. Error: {e}")

        # 2. rsrch.space scrape
        scrape_rsrch_stats = {"status": "not_run"}
        try:
            logging.info("Starting rsrch.space scraping process...")
            scrape_rsrch_stats = run_scrape_and_sync(limit=1000)
            logging.info(f"rsrch.space scraping completed: {scrape_rsrch_stats.get('status')}")
        except Exception as e:
            logging.error(f"Error during rsrch.space scraping: {e}")
            scrape_rsrch_stats = {"status": "error", "error": str(e)}

        # 3. Chinese Frontier scrape
        chinese_frontier_stats = {"status": "not_run"}
        try:
            logging.info("Starting Chinese Frontier scraping process...")
            chinese_frontier_stats = sync_chinese_frontier()
            logging.info(f"Chinese Frontier scraping completed: {chinese_frontier_stats.get('status')}")
        except Exception as e:
            logging.error(f"Error during Chinese Frontier scraping: {e}")
            chinese_frontier_stats = {"status": "error", "error": str(e)}

        # 4. Combined summary message
        rs = scrape_rsrch_stats
        cf = chinese_frontier_stats
        summary = (
            f"📋 Scrape Pipeline Summary\n\n"
            f"🔗 rsrch space\n"
            f"  • Scraped: {rs.get('total_scraped', '—')}\n"
            f"  • New inserted: {rs.get('sync_stats', {}).get('items_synced', '—')}\n\n"
            f"🐉 Chinese Frontier\n"
            f"  • Scraped: {cf.get('scraped', '—')}\n"
            f"  • New inserted: {cf.get('inserted', '—')}\n"
            f"  • Duplicates skipped: {cf.get('duplicates', '—')}"
        )
        if rs.get("status") == "error":
            summary += f"\n\n⚠️ rsrch.space error: {rs.get('error')}"
        if cf.get("status") == "error":
            summary += f"\n\n⚠️ Chinese Frontier error: {cf.get('error')}"
        send_telegram_message(summary)

        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.end_headers()

        self.wfile.write(json.dumps({
            "supabase_ping": {"scrape_table": scrape_status},
            "notion_supabase_sync": {"status": sync_status, "stats": sync_stats},
            "rsrch_space_scraping": scrape_rsrch_stats,
            "chinese_frontier_scraping": chinese_frontier_stats,
        }).encode())

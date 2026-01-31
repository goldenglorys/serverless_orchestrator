import logging
import json
from http.server import BaseHTTPRequestHandler
from typing import Dict, Any

from utils.notion_supabase_sync import (
    main as sync_data,
    ping_supabase_table,
    supabase_client,
    # second_supabase_client,
)
from utils.notify import send_telegram_message
from dotenv import load_dotenv

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
        papers_status = _ping_and_get_status(supabase_client, "papers", "account_1")
        links_status = _ping_and_get_status(supabase_client, "links", "account_1")
        # second_supabase_status = _ping_and_get_status(
        #     second_supabase_client, "users", "account_2"
        # )

        # Run Notion to Supabase sync. If it fails, stop and report.
        try:
            sync_data()
            send_telegram_message(
                "✅ The Notion to Supabase sync job completed successfully."
            )
        except Exception as e:
            logging.error(f"Critical error during data sync: {e}")
            sync_status = "error"
            send_telegram_message(
                f"❌ CRITICAL: The Notion to Supabase sync job failed. Error: {e}"
            )
            # Do not proceed further if sync fails.

        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.end_headers()

        response_data = {
            "supabase_ping": {
                "account_1": {
                    "papers_table": papers_status,
                    "links_table": links_status,
                },
                # "account_2": {
                #     "users_table": second_supabase_status,
                # },
            },
            "notion_supabase_sync": {"status": sync_status},
        }

        self.wfile.write(json.dumps(response_data).encode())

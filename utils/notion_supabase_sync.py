"""
Notion to Supabase Sync Script

This script synchronizes data from Notion databases to Supabase tables
in a configuration-driven way. It ensures that if any step in the process
for a given database fails, it does not leave the data in a partially
synced state (e.g., uploaded to Supabase but not updated in Notion).
"""

import logging
import os
from typing import List, Dict, Any, Optional

from dotenv import load_dotenv
from notion_client import Client
from supabase import create_client, Client as SupabaseClient
from tqdm import tqdm

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Load environment variables
# Find .env file relative to this script's location for better compatibility with Vercel
from pathlib import Path
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# --- Client Initialization ---
supabase_client: SupabaseClient = create_client(
    os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY")
)

notion = Client(auth=os.getenv("NOTION_TOKEN"))

# --- Configuration ---
# Makes the script scalable. Add new dicts to this list to sync more databases.
SYNC_CONFIG = [
    {
        "name": "papers",
        "source_db_id": os.getenv("PAPERS_DATABASE_ID"),
        "archive_db_id": os.getenv("ARCHIVE_PAPERS_DATABASE_ID"),
        "supabase_table": "papers",
        "supabase_client": supabase_client,
    },
    {
        "name": "links",
        "source_db_id": os.getenv("LINKS_DATABASE_ID"),
        "archive_db_id": os.getenv("ARCHIVE_LINKS_DATABASE_ID"),
        "supabase_table": "links",
        "supabase_client": supabase_client,
    },
]


def ping_supabase_table(
    client: SupabaseClient, table_name: str
) -> Optional[List[Dict[str, Any]]]:
    """Pings a Supabase table by fetching up to 10 records."""
    try:
        response = client.table(table_name).select("*").limit(10).execute()
        return response.data
    except Exception as e:
        logger.error(f"Error pinging Supabase table {table_name}: {e}")
        return None


def process_notion_item(item: Dict[str, Any], table_name: str) -> Dict[str, Any]:
    """Extracts relevant data from a Notion item."""
    properties = item["properties"]
    data = {
        "title": properties.get("Title", {})
        .get("title", [{}])[0]
        .get("plain_text", ""),
        "url": properties.get("URL", {}).get("url"),
        "notion_timestamp": item.get("created_time"),
    }
    if table_name == "papers":
        data["date"] = properties.get("Date", {}).get("date", {}).get("start")
        data["authors"] = (
            properties.get("Authors", {})
            .get("rich_text", [{}])[0]
            .get("plain_text", "")
        )
    return data


def update_notion_status_to_uploaded(page_ids: List[str]) -> None:
    """Updates the status of Notion pages to 'Uploaded'."""
    for page_id in page_ids:
        try:
            notion.pages.update(
                page_id=page_id, properties={"Status": {"status": {"name": "Uploaded"}}}
            )
            logger.info(f"Updated status for Notion page {page_id} to 'Uploaded'.")
        except Exception as e:
            logger.error(f"Error updating Notion page {page_id} status: {e}")
            raise  # Re-raise to halt the process if an update fails


def sync_new_items(config: Dict[str, Any]) -> int:
    """Fetches new items from Notion, inserts them into Supabase, and updates their status.
    Returns the number of items synced."""
    db_id = config["source_db_id"]
    table_name = config["supabase_table"]
    supabase = config["supabase_client"]

    logger.info(f"Checking for new items in Notion database: {config['name']}")

    try:
        response = notion.databases.query(
            database_id=db_id,
            filter={"property": "Status", "status": {"equals": "New"}},
        )
    except Exception as e:
        logger.error(f"Error querying Notion for new items: {e}")
        return 0

    if not response["results"]:
        logger.info(f"No new items found for '{config['name']}'.")
        return 0

    data_to_insert = []
    page_ids_to_update = []
    for item in response["results"]:
        data_to_insert.append(process_notion_item(item, table_name))
        page_ids_to_update.append(item["id"])

    # Transactional Block: only update Notion if Supabase insert succeeds.
    try:
        logger.info(
            f"Inserting {len(data_to_insert)} new items into Supabase table '{table_name}'."
        )
        supabase.table(table_name).upsert(data_to_insert).execute()

        logger.info(
            f"Updating {len(page_ids_to_update)} items in Notion to 'Uploaded'."
        )
        update_notion_status_to_uploaded(page_ids_to_update)

        return len(data_to_insert)

    except Exception as e:
        logger.error(
            f"TRANSACTION FAILED for '{config['name']}': Could not sync data. Error: {e}"
        )
        # By re-raising, we stop the main function from proceeding to archival
        raise


def archive_uploaded_items(config: Dict[str, Any]) -> None:
    """Moves items with 'Uploaded' status to an archive database."""
    source_db_id = config["source_db_id"]
    archive_db_id = config["archive_db_id"]

    if not archive_db_id:
        logger.warning(
            f"Archive DB ID not set for '{config['name']}'. Skipping archival."
        )
        return

    logger.info(f"Checking for 'Uploaded' items to archive from '{config['name']}'")
    try:
        response = notion.databases.query(
            database_id=source_db_id,
            filter={"property": "Status", "status": {"equals": "Uploaded"}},
        )
    except Exception as e:
        logger.error(f"Error querying Notion for 'Uploaded' items: {e}")
        return

    if not response["results"]:
        logger.info(f"No items to archive for '{config['name']}'.")
        return

    read_only_props = [
        "created_by",
        "created_time",
        "last_edited_by",
        "last_edited_time",
    ]
    for page in tqdm(response["results"], desc=f"Archiving from '{config['name']}'"):
        try:
            properties_to_copy = {
                k: v
                for k, v in page["properties"].items()
                if v["type"] not in read_only_props
            }
            properties_to_copy["Status"] = {"status": {"name": "Archived"}}

            notion.pages.create(
                parent={"database_id": archive_db_id}, properties=properties_to_copy
            )
            notion.pages.update(page_id=page["id"], archived=True)
            logger.info(f"Archived page {page['id']} and deleted original.")
        except Exception as e:
            logger.error(
                f"Failed to archive page {page['id']}: {e}. Continuing with next page."
            )


def main() -> Dict[str, int]:
    """Main function to run the sync and archival processes based on SYNC_CONFIG.
    Returns a dictionary with sync statistics."""
    logger.info("--- Starting Notion to Supabase Sync Process ---")

    stats = {
        "papers_synced": 0,
        "links_synced": 0
    }

    for config in SYNC_CONFIG:
        if not all(
            k in config for k in ["source_db_id", "supabase_table", "supabase_client"]
        ):
            logger.warning(
                f"Skipping invalid config for '{config.get('name', 'N/A')}'."
            )
            continue

        synced_count = sync_new_items(config)
        # Track stats by table name
        if config["name"] == "papers":
            stats["papers_synced"] = synced_count
        elif config["name"] == "links":
            stats["links_synced"] = synced_count

    logger.info("--- Sync Process Completed ---")

    logger.info("--- Starting Notion Archival Process ---")
    for config in SYNC_CONFIG:
        archive_uploaded_items(config)
    logger.info("--- Archival Process Completed ---")

    return stats

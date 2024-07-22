"""
Notion to Supabase Sync Script

This script synchronizes data from Notion databases to Supabase tables.
It retrieves items with a "New" status from Notion, inserts them into Supabase,
and then updates their status to "Uploaded" in Notion.

Environment Variables:
    SUPABASE_URL: URL of your Supabase project
    SUPABASE_KEY: API key for your Supabase project
    NOTION_TOKEN: Integration token for Notion API
    PAPERS_DATABASE_ID: ID of the Notion database for papers
    LINKS_DATABASE_ID: ID of the Notion database for links

Usage:
    python notion_to_supabase_sync.py
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
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
PAPERS_DATABASE_ID = os.getenv("PAPERS_DATABASE_ID")
LINKS_DATABASE_ID = os.getenv("LINKS_DATABASE_ID")

# Initialize clients
supabase: SupabaseClient = create_client(SUPABASE_URL, SUPABASE_KEY)
notion = Client(auth=NOTION_TOKEN)


def ping_supabase(table_name: str) -> Optional[List[Dict[str, Any]]]:
    """
    Ping the Supabase instance by fetching 10 records from the specified table.

    Args:
        table_name (str): The name of the Supabase table to fetch data from.

    Returns:
        Optional[List[Dict[str, Any]]]: A list of up to 10 records from the specified table, or None if an error occurs.
    """
    try:
        response = supabase.table(table_name).select("*").limit(10).execute()
        return response.data
    except Exception as e:
        logger.error(f"Error pinging Supabase table {table_name}: {e}")
        return None


def insert_data(
    database_id: str, table_name: str, notion: Client, supabase: SupabaseClient
) -> None:
    """
    Retrieve data from Notion and insert it into Supabase.

    Args:
        database_id (str): The ID of the Notion database to query.
        table_name (str): The name of the Supabase table to insert data into.
        notion (Client): The Notion client instance.
        supabase (SupabaseClient): The Supabase client instance.
    """
    start_cursor = None
    total_processed = 0

    while True:
        try:
            response = notion.databases.query(
                database_id=database_id,
                filter={"property": "Status", "status": {"equals": "New"}},
                start_cursor=start_cursor,
            )
        except Exception as e:
            logger.error(f"Error querying Notion database: {e}")
            break

        if not response["results"]:
            logger.info(f"No new items found in the {table_name} database.")
            break

        data_batch = []
        updated_pages = []

        for item in tqdm(response["results"], desc=f"Processing {table_name}"):
            data = process_notion_item(item, table_name)
            data_batch.append(data)
            updated_pages.append(item["id"])

        try:
            supabase.table(table_name).upsert(data_batch).execute()
            logger.info(
                f"Inserted {len(data_batch)} items into Supabase {table_name} table."
            )
        except Exception as e:
            logger.error(f"Error inserting data into Supabase: {e}")
            continue

        update_notion_status(notion, updated_pages)
        total_processed += len(updated_pages)

        if response["has_more"]:
            start_cursor = response["next_cursor"]
        else:
            break

    logger.info(f"Total items processed for {table_name}: {total_processed}")


def process_notion_item(item: Dict[str, Any], table_name: str) -> Dict[str, Any]:
    """
    Process a single Notion item and extract relevant data.

    Args:
        item (Dict[str, Any]): The Notion item to process.
        table_name (str): The name of the table (used to determine which fields to extract).

    Returns:
        Dict[str, Any]: The processed data ready for insertion into Supabase.
    """
    data = {
        "title": item["properties"]["Title"]["title"][0]["plain_text"],
        "url": item["properties"]["URL"]["url"],
        "notion_timestamp": item["created_time"],
    }

    if table_name == "papers":
        data["date"] = item["properties"]["Date"]["date"]["start"]
        data["authors"] = item["properties"]["Authors"]["rich_text"][0]["plain_text"]

    return data


def update_notion_status(notion: Client, page_ids: List[str]) -> None:
    """
    Update the status of Notion pages to "Uploaded".

    Args:
        notion (Client): The Notion client instance.
        page_ids (List[str]): List of page IDs to update.
    """
    for page_id in page_ids:
        try:
            notion.pages.update(
                page_id=page_id, properties={"Status": {"status": {"name": "Uploaded"}}}
            )
        except Exception as e:
            logger.error(f"Error updating Notion page {page_id}: {e}")


def main() -> None:
    """Main function to run the sync process."""
    logger.info("Starting Notion to Supabase sync process")

    logger.info("Syncing papers database")
    insert_data(PAPERS_DATABASE_ID, "papers", notion, supabase)

    logger.info("Syncing links database")
    insert_data(LINKS_DATABASE_ID, "links", notion, supabase)

    logger.info("Sync process completed")

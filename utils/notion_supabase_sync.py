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
ARCHIVE_PAPERS_DATABASE_ID = os.getenv("ARCHIVE_PAPERS_DATABASE_ID")
ARCHIVE_LINKS_DATABASE_ID = os.getenv("ARCHIVE_LINKS_DATABASE_ID")

SECOND_SUPABASE_URL = os.getenv("SECOND_SUPABASE_URL")
SECOND_SUPABASE_KEY = os.getenv("SECOND_SUPABASE_KEY")

# Initialize clients
supabase: SupabaseClient = create_client(SUPABASE_URL, SUPABASE_KEY)
notion = Client(auth=NOTION_TOKEN)

second_supabase: SupabaseClient = create_client(SECOND_SUPABASE_URL, SECOND_SUPABASE_KEY)


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

def ping_second_supabase(table_name: str) -> Optional[List[Dict[str, Any]]]:
    try:
        response = second_supabase.table(table_name).select("*").limit(10).execute()
        return response.data
    except Exception as e:
        logger.error(f"Error pinging second Supabase table {table_name}: {e}")
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
            logger.error(f"Error querying Notion database for new items: {e}")
            break

        if not response["results"]:
            logger.info(f"No new items found in the {table_name} database.")
            break

        data_batch = []
        page_ids_to_update = []

        for item in tqdm(response["results"], desc=f"Processing new {table_name}"):
            data = process_notion_item(item, table_name)
            data_batch.append(data)
            page_ids_to_update.append(item["id"])

        try:
            supabase.table(table_name).upsert(data_batch).execute()
            logger.info(f"Inserted {len(data_batch)} items into Supabase {table_name} table.")
            update_notion_status_to_uploaded(notion, page_ids_to_update)
            total_processed += len(page_ids_to_update)
        except Exception as e:
            logger.error(f"Error inserting data into Supabase or updating Notion: {e}")
            continue

        if response.get("has_more"):
            start_cursor = response.get("next_cursor")
        else:
            break

    logger.info(f"Total new items processed for {table_name}: {total_processed}")

def process_notion_item(item: Dict[str, Any], table_name: str) -> Dict[str, Any]:
    """
    Process a single Notion item and extract relevant data.

    Args:
        item (Dict[str, Any]): The Notion item to process.
        table_name (str): The name of the table (used to determine which fields to extract).

    Returns:
        Dict[str, Any]: The processed data ready for insertion into Supabase.
    """
    properties = item["properties"]
    
    data = {
        "title": properties.get("Title", {}).get("title", [{}])[0].get("plain_text", ""),
        "url": properties.get("URL", {}).get("url"),
        "notion_timestamp": item.get("created_time"),
    }
    
    if table_name == "papers":
        data["date"] = properties.get("Date", {}).get("date", {}).get("start")
        data["authors"] = properties.get("Authors", {}).get("rich_text", [{}])[0].get("plain_text", "")
        
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
            logger.info(f"Updated status for Notion page {page_id} to 'Uploaded'.")
        except Exception as e:
            logger.error(f"Error updating Notion page {page_id} status: {e}")
            

def archive_uploaded_items(source_db_id: str, archive_db_id: str) -> None:
    if not archive_db_id:
        logger.warning(f"Archive database ID not set for source {source_db_id}. Skipping archival.")
        return

    logger.info(f"Checking for 'Uploaded' items to archive from {source_db_id}")
    start_cursor = None
    read_only_property_types = [
        "created_by", "created_time", "last_edited_by", "last_edited_time", "formula", "rollup"
    ]

    while True:
        try:
            response = notion.databases.query(
                database_id=source_db_id,
                filter={"property": "Status", "status": {"equals": "Uploaded"}},
                start_cursor=start_cursor
            )
        except Exception as e:
            logger.error(f"Error querying Notion for 'Uploaded' items: {e}")
            break

        if not response["results"]:
            logger.info(f"No 'Uploaded' items to archive in {source_db_id}.")
            break

        for page in tqdm(response["results"], desc=f"Archiving items from {source_db_id}"):
            try:
                properties_to_copy = {
                    prop_name: prop_value
                    for prop_name, prop_value in page["properties"].items()
                    if prop_value["type"] not in read_only_property_types
                }
                properties_to_copy["Status"] = {"status": {"name": "Archived"}}

                notion.pages.create(
                    parent={"database_id": archive_db_id},
                    properties=properties_to_copy,
                )
                notion.pages.update(page_id=page["id"], archived=True)
                logger.info(f"Archived and deleted original page {page['id']}.")
            except Exception as e:
                logger.error(f"Failed to archive page {page['id']}: {e}")
                continue

        if response.get("has_more"):
            start_cursor = response.get("next_cursor")
        else:
            break            

def main() -> None:
    """Main function to run the sync process."""
    logger.info("Starting Notion to Supabase sync process")
    insert_data(PAPERS_DATABASE_ID, "papers", notion, supabase)
    insert_data(LINKS_DATABASE_ID, "links", notion, supabase)
    logger.info("Sync process completed")

    logger.info("Starting Notion archival process")
    archive_uploaded_items(PAPERS_DATABASE_ID, ARCHIVE_PAPERS_DATABASE_ID)
    archive_uploaded_items(LINKS_DATABASE_ID, ARCHIVE_LINKS_DATABASE_ID)
    logger.info("Archival process completed")

"""
Duplicate Detection and Removal Script for Supabase Tables

This script finds and removes duplicate entries based on URL.
Supports dry-run mode to preview what would be deleted.
"""

import os
import sys
from typing import List, Dict, Any, Set
from collections import defaultdict
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.notion_supabase_sync import supabase_client

load_dotenv()


def find_duplicates_by_url(table_name: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    Finds duplicate entries in a table based on URL.
    Returns a dict where keys are URLs and values are lists of duplicate records.
    """
    print(f"\n{'='*60}")
    print(f"🔍 Analyzing '{table_name}' table for URL duplicates...")
    print(f"{'='*60}")

    try:
        # Fetch all records from the table - do pagination to handle large tables
        all_records = []
        offset = 0
        batch_size = 1000

        while True:
            print(f"   Fetching records {offset} to {offset + batch_size}...")
            response = supabase_client.table(table_name).select("*").range(offset, offset + batch_size - 1).execute()

            if not response.data:
                break

            all_records.extend(response.data)

            if len(response.data) < batch_size:
                break

            offset += batch_size

        print(f"📊 Total records in table: {len(all_records)}")

        # Group records by URL
        url_groups = defaultdict(list)
        records_without_url = 0

        for record in all_records:
            url = record.get('url')
            if url:
                url_groups[url].append(record)
            else:
                records_without_url += 1

        if records_without_url > 0:
            print(f"⚠️  Found {records_without_url} records without URLs")

        # Filter to only keep URLs with duplicates
        duplicates = {url: records for url, records in url_groups.items() if len(records) > 1}

        if duplicates:
            print(f"\n🔍 Found {len(duplicates)} URLs with duplicates:")
            total_duplicate_records = sum(len(records) - 1 for records in duplicates.values())
            print(f"   📝 Total duplicate records to remove: {total_duplicate_records}")
            print(f"   ✅ Will keep: {len(duplicates)} records (oldest)")

            # Show sample duplicates
            print(f"\n📋 Sample duplicates (first 10):")
            for i, (url, records) in enumerate(list(duplicates.items())[:10], 1):
                print(f"\n   {i}. URL: {url[:80]}...")
                print(f"      Count: {len(records)} instances")
                print(f"      IDs: {[rec.get('id') for rec in records]}")
                titles = [rec.get('title', 'N/A')[:40] for rec in records[:3]]
                print(f"      Titles: {titles}")

        else:
            print(f"\n✅ No URL duplicates found in '{table_name}' table!")

        return duplicates

    except Exception as e:
        print(f"❌ Error analyzing table '{table_name}': {e}")
        import traceback
        traceback.print_exc()
        return {}


def remove_duplicates(table_name: str, duplicates: Dict[str, List[Dict[str, Any]]], dry_run: bool = True):
    """
    Removes duplicate records, keeping only the oldest entry (by id).
    """
    if not duplicates:
        print(f"\n✅ No duplicates to remove from '{table_name}' table")
        return

    print(f"\n{'='*60}")
    if dry_run:
        print(f"🔍 DRY RUN: Simulating removal from '{table_name}' table")
    else:
        print(f"🗑️  REMOVING duplicates from '{table_name}' table")
    print(f"{'='*60}")

    total_to_remove = 0
    ids_to_delete = []
    urls_to_keep = []

    for url, records in duplicates.items():
        # Sort by id (assuming lower id = older record) to keep the first one
        records_sorted = sorted(records, key=lambda x: x.get('id', 0))

        # Keep the first (oldest) record, delete the rest
        to_keep = records_sorted[0]
        to_delete = records_sorted[1:]

        urls_to_keep.append(url)

        for record in to_delete:
            ids_to_delete.append(record['id'])
            total_to_remove += 1

    print(f"\n📊 Statistics:")
    print(f"   Total URLs with duplicates: {len(duplicates)}")
    print(f"   Records to keep (oldest): {len(urls_to_keep)}")
    print(f"   Records to delete (duplicates): {total_to_remove}")

    if dry_run:
        print(f"\n⚠️  DRY RUN MODE - No actual deletion performed")
        print(f"\n   Sample IDs to delete (first 20):")
        for i, record_id in enumerate(ids_to_delete[:20], 1):
            print(f"      {i}. ID: {record_id}")

        if len(ids_to_delete) > 20:
            print(f"      ... and {len(ids_to_delete) - 20} more")

    else:
        print(f"\n🗑️  Deleting {total_to_remove} duplicate records...")
        print(f"   This may take a while...")

        deleted_count = 0
        failed_count = 0

        # Delete one by one to ensure accuracy
        for i, record_id in enumerate(ids_to_delete, 1):
            try:
                supabase_client.table(table_name).delete().eq('id', record_id).execute()
                deleted_count += 1

                # Show progress every 50 deletions
                if deleted_count % 50 == 0:
                    print(f"   Progress: {deleted_count}/{total_to_remove} deleted...")

            except Exception as e:
                print(f"   ❌ Error deleting ID {record_id}: {e}")
                failed_count += 1

        print(f"\n✅ Deletion complete!")
        print(f"   Successfully deleted: {deleted_count}")
        if failed_count > 0:
            print(f"   Failed to delete: {failed_count}")


def main():
    """Main function to run duplicate detection and removal."""
    print("\n" + "="*60)
    print("🧹 SUPABASE DUPLICATE DETECTION & REMOVAL TOOL")
    print("="*60)

    # Parse command line arguments
    dry_run = True
    if len(sys.argv) > 1 and sys.argv[1] == "--remove":
        dry_run = False
        print("\n⚠️  WARNING: Running in REMOVE mode - duplicates will be deleted!")
        print("   This will keep the OLDEST record (lowest ID) for each duplicate URL")
        response = input("\n   Are you sure you want to continue? (yes/no): ")
        if response.lower() != "yes":
            print("\n❌ Aborted.")
            return
    else:
        print("\n🔍 Running in DRY RUN mode (no changes will be made)")
        print("   Use '--remove' flag to actually delete duplicates")

    # Tables to check
    tables = ["papers", "links"]

    summary = {
        "total_duplicates": 0,
        "total_to_delete": 0
    }

    for table in tables:
        print(f"\n{'#'*60}")
        print(f"# Processing table: {table}")
        print(f"{'#'*60}")

        # Find URL duplicates
        url_duplicates = find_duplicates_by_url(table)

        if url_duplicates:
            duplicate_count = sum(len(records) - 1 for records in url_duplicates.values())
            summary["total_duplicates"] += len(url_duplicates)
            summary["total_to_delete"] += duplicate_count

            remove_duplicates(table, url_duplicates, dry_run)

    # Summary
    print("\n" + "="*60)
    print("📊 FINAL SUMMARY")
    print("="*60)
    print(f"Total unique URLs with duplicates: {summary['total_duplicates']}")
    print(f"Total duplicate records found: {summary['total_to_delete']}")

    if dry_run:
        print(f"\n💡 To actually remove duplicates, run:")
        print(f"   python remove_duplicates.py --remove")
    else:
        print(f"\n✅ Duplicate removal completed!")
        print(f"\n🎉 Your database is now clean!")


if __name__ == "__main__":
    main()

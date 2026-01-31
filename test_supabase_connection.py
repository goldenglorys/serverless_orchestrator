"""
Test script to verify Supabase API key validity
"""
import os
from dotenv import load_dotenv
from supabase import create_client

# Load environment variables
load_dotenv()

print("=" * 60)
print("TESTING SUPABASE API KEYS")
print("=" * 60)

# Test first Supabase account
print("\n[1] Testing FIRST Supabase Account")
print(f"URL: {os.getenv('SUPABASE_URL')}")
print(f"Key starts with: {os.getenv('SUPABASE_KEY')[:30]}...")
print(f"Key format: {'JWT (old format)' if os.getenv('SUPABASE_KEY').startswith('eyJ') else 'New format (sb_)'}")

try:
    client1 = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
    response = client1.table("papers").select("*").limit(1).execute()
    print(f"✅ SUCCESS: Connected to first Supabase account")
    print(f"   Response: {len(response.data)} records fetched")
except Exception as e:
    print(f"❌ FAILED: {str(e)}")

# Test second Supabase account
print("\n[2] Testing SECOND Supabase Account")
print(f"URL: {os.getenv('SECOND_SUPABASE_URL')}")
print(f"Key starts with: {os.getenv('SECOND_SUPABASE_KEY')[:30]}...")
print(f"Key format: {'JWT (old format)' if os.getenv('SECOND_SUPABASE_KEY').startswith('eyJ') else 'New format (sb_)'}")

try:
    client2 = create_client(os.getenv("SECOND_SUPABASE_URL"), os.getenv("SECOND_SUPABASE_KEY"))
    response = client2.table("users").select("*").limit(1).execute()
    print(f"✅ SUCCESS: Connected to second Supabase account")
    print(f"   Response: {len(response.data)} records fetched")
except Exception as e:
    print(f"❌ FAILED: {str(e)}")

print("\n" + "=" * 60)
print("DIAGNOSIS:")
print("=" * 60)
print("If the first account failed with 'Invalid API key', you need to:")
print("1. Go to https://supabase.com/dashboard")
print("2. Select your project: sacumoyabskwgnlsewei")
print("3. Go to Settings > API Keys")
print("4. Look for 'Publishable key' (sb_publishable_...) or 'Secret key' (sb_secret_...)")
print("5. Copy the new secret key (sb_secret_...) for server-side use")
print("6. Update your .env file with the new key")
print("=" * 60)

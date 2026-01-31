import os
from supabase import create_client, Client

SUPABASE_URL="https://sacumoyabskwgnlsewei.supabase.co"
SUPABASE_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InNhY3Vtb3lhYnNrd2dubHNld2VpIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTcxMDA4NTg5OSwiZXhwIjoyMDI1NjYxODk5fQ.ioTqiZgWXr0P8iZzxm32T7Mm05DdSNSH1xiE5I8jDNA"

# # ---- PASTE YOUR CREDENTIALS DIRECTLY HERE FOR THIS TEST ----
# SUPABASE_URL = "https://sacumoyabskwgnlsewei.supabase.co"
# # IMPORTANT: Use the SECRET service_role key, not the anon key.
# SUPABASE_KEY = "YOUR_ACTUAL_SERVICE_ROLE_KEY_HERE"
# -------------------------------------------------------------

try:
    print("Attempting to connect to Supabase...")
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("Client initialized. Fetching data from 'papers' table...")

    response = supabase.table("papers").select("*").limit(1).execute()

    print("\n--- SUCCESS ---")
    print("API Response:", response.data)

except Exception as e:
    print("\n--- FAILED ---")
    print("An error occurred:", e)
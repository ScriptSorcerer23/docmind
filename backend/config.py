"""
Configuration — loads env vars and initializes shared clients.
"""

import os
from dotenv import load_dotenv
from supabase import create_client, Client
from langchain_google_genai import GoogleGenerativeAIEmbeddings

load_dotenv()

# ── Environment Variables ──────────────────────────────────────────
SUPABASE_URL: str = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY: str = os.environ["SUPABASE_SERVICE_KEY"]
SUPABASE_ANON_KEY: str = os.getenv("SUPABASE_ANON_KEY", "")
GOOGLE_API_KEY: str = os.environ["GOOGLE_API_KEY"]
GROQ_API_KEY: str = os.environ["GROQ_API_KEY"]

# CrewAI uses LiteLLM under the hood; LiteLLM reads GEMINI_API_KEY
os.environ["GEMINI_API_KEY"] = GOOGLE_API_KEY

# ── Shared Clients ─────────────────────────────────────────────────
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

embedder = GoogleGenerativeAIEmbeddings(
    model="models/gemini-embedding-001",
    google_api_key=GOOGLE_API_KEY
)

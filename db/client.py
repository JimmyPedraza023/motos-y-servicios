import os

from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

_client: Client | None = None


def get_client() -> Client:
    global _client

    if _client is None:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

        if not url:
            raise ValueError("SUPABASE_URL no está configurada")

        if not key:
            raise ValueError("SUPABASE_SERVICE_ROLE_KEY no está configurada")

        _client = create_client(url, key)

    return _client
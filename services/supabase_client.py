"""Supabase client factory."""

from functools import lru_cache

from supabase import Client, create_client

from config import get_settings


@lru_cache
def get_supabase_client() -> Client:
    """Return cached Supabase client."""

    settings = get_settings()
    
    # Create client with proper headers for PostgREST
    options = {
        "headers": {
            "accept-profile": "public",
            "content-profile": "public",
        }
    }
    
    return create_client(
        settings.supabase_url, 
        settings.supabase_service_role_key,
        options=options
    )

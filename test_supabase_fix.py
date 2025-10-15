#!/usr/bin/env python3
"""Quick test to verify Supabase client fix."""

import asyncio
from services.customer_service import resolve_customer_from_phone


async def test_customer_lookup():
    """Test customer lookup with the fixed Supabase client."""
    
    print("Testing Supabase customer lookup...")
    
    try:
        # Try to find/create customer
        result = await resolve_customer_from_phone(
            phone_number="+256782240146",
            display_name="Test User"
        )
        
        print("✅ Success!")
        print(f"Customer ID: {result['customer_id']}")
        print(f"Phone: {result['phone_number']}")
        print(f"Display Name: {result['display_name']}")
        print(f"Is New: {result['is_new_customer']}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_customer_lookup())

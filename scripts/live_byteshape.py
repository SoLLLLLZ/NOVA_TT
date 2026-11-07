"""Standalone ByteShape baseline followed by the OpenRouter/Astra production test."""
import asyncio
from check_live_models import main

if __name__ == "__main__":
    asyncio.run(main("qwen3.8-27b"))

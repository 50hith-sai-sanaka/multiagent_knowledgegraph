"""
Neo4j Schema Initialization Script
File: run_schema_init.py
Sprint: Sprint 2 (STORY-005)
"""

import asyncio
import logging
import sys

from src.db.neo4j_client import Neo4jClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("schema_init")


async def main():
    client = Neo4jClient()
    try:
        await client.connect()
        logger.info("Step 1 PASS: Connected to Neo4j.")
        await client.initialize_schema()
        logger.info("Step 2 PASS: Schema constraints and indexes initialized idempotently.")
    except Exception as e:
        logger.error("Schema initialization failed: %s", e)
        sys.exit(1)
    finally:
        await client.close()
        logger.info("Step 3 PASS: Connection closed.")


if __name__ == "__main__":
    asyncio.run(main())

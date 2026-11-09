import asyncio
from src.db.neo4j_client import Neo4jClient

async def main():
    client = Neo4jClient()
    await client.connect()
    print('Step 1 PASS: Connected to Neo4j.')
    await client.initialize_schema()
    print('Step 2 PASS: Schema initialized.')
    await client.close()
    print('Step 3 PASS: Connection closed.')

if __name__ == '__main__':
    asyncio.run(main())

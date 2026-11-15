"""
Stdio transport client for Model Context Protocol.
"""

import asyncio
from contextlib import asynccontextmanager
import os
import subprocess
from typing import AsyncIterator, Tuple
from mcp import StdioServerParameters


@asynccontextmanager
async def stdio_client(
    server_params: StdioServerParameters,
) -> AsyncIterator[Tuple[asyncio.StreamReader, asyncio.StreamWriter]]:
    """Spawns an MCP server subprocess and yields its async (read_stream, write_stream)."""
    env = dict(os.environ)
    if server_params.env:
        env.update(server_params.env)

    # Ensure PYTHONPATH includes workspace root
    if "PYTHONPATH" not in env:
        env["PYTHONPATH"] = "."

    # 10 MB line buffer to prevent LimitOverrunError on large payloads
    process = await asyncio.create_subprocess_exec(
        server_params.command,
        *server_params.args,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        limit=10 * 1024 * 1024,
    )

    try:
        yield process.stdout, process.stdin
    finally:
        if process.stdin:
            process.stdin.close()
            try:
                await process.stdin.wait_closed()
            except Exception:
                pass
        if process.returncode is None:
            try:
                process.terminate()
                await asyncio.wait_for(process.wait(), timeout=2.0)
            except Exception:
                try:
                    process.kill()
                    await asyncio.wait_for(process.wait(), timeout=1.0)
                except Exception:
                    pass


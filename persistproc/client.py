import os

from fastmcp.client import Client


def make_client(port: str = os.getenv("PERSISTPROC_PORT", 8000)):
    return Client(f"http://127.0.0.1:{port}/mcp")

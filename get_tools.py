import requests
import json
MCP_URL = "https://mcp.fortytwo.network/mcp"
s = requests.Session()
s.post(MCP_URL, json={
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "test", "version": "1.0"}}
})
resp = s.post(MCP_URL, json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
print(resp.status_code)
print(resp.text)

import os
import httpx
from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# You do NOT need to edit anything in this file.
# The report link is supplied later on Render's website as an "environment
# variable" called REPORT_URL. If your report ever needs a key, you'll add
# one called API_KEY the same way. Nothing secret lives in this code.
# ---------------------------------------------------------------------------

REPORT_URL = os.environ.get("REPORT_URL", "")
API_KEY = os.environ.get("API_KEY", "")  # leave unset if the link is public

mcp = FastMCP(
    "softinfo-report",
    host="0.0.0.0",
    port=int(os.environ.get("PORT", "8000")),
)


@mcp.tool()
async def get_billing_report() -> str:
    """Fetch the latest SoftInfo billing report.

    Returns the current report data as JSON text. The underlying report is
    refreshed every 15 minutes, so this always reflects recent figures.
    """
    if not REPORT_URL:
        return ("REPORT_URL is not set. Add it as an environment variable "
                "on the hosting service (Render) and redeploy.")

    headers = {}
    if API_KEY:
        # If SoftInfo says the key goes in a different header, this one line
        # is the only thing that changes.
        headers["Authorization"] = f"Bearer {API_KEY}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(REPORT_URL, headers=headers)
        response.raise_for_status()
        return response.text


if __name__ == "__main__":
    mcp.run(transport="streamable-http")

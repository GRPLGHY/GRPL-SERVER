import os
import json
import httpx
from datetime import date
from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# You do NOT edit anything in this file.
# All the real values are set on Render's website as "environment variables":
#
#   WIZAPP_GROUP_CODE   the GroupCode (e.g. avn0116)
#   WIZAPP_USERNAME     the userName from SoftInfo's document
#   WIZAPP_PASSWORD     the passwd from SoftInfo's document (no spaces!)
#   REPORT_ID           HOW0000268   (Stock Analysis report)
#   FILTER_ID           NF00000286   (its named filter)
#
# Nothing secret lives in this code.
# ---------------------------------------------------------------------------

GROUP_CODE = os.environ.get("WIZAPP_GROUP_CODE", "")
USERNAME   = os.environ.get("WIZAPP_USERNAME", "")
PASSWORD   = os.environ.get("WIZAPP_PASSWORD", "")
REPORT_ID  = os.environ.get("REPORT_ID", "")
FILTER_ID  = os.environ.get("FILTER_ID", "")

BASE = "https://wizapp.in"

mcp = FastMCP(
    "softinfo-reports",
    host="0.0.0.0",
    port=int(os.environ.get("PORT", "8000")),
)


def _extract_token(resp_text: str) -> str:
    """The login steps may return a bare token, or a token wrapped in JSON.
    This pulls the token out either way."""
    t = (resp_text or "").strip()
    try:
        data = json.loads(t)
        if isinstance(data, str):
            return data
        if isinstance(data, dict):
            for k in ("refreshToken", "RefreshToken", "accessToken",
                      "AccessToken", "token", "Token", "data", "result"):
                v = data.get(k)
                if isinstance(v, str) and v:
                    return v
    except Exception:
        pass
    return t.strip('"')


async def _get_access_token(client: httpx.AsyncClient) -> str:
    # Step 1: show ID (login) -> get a refresh token
    r1 = await client.post(
        f"{BASE}/restWizappservice/validateUser",
        params={"GroupCode": GROUP_CODE},
        headers={"Content-Type": "application/json"},
        json={"userName": USERNAME, "passwd": PASSWORD},
    )
    r1.raise_for_status()
    refresh_token = _extract_token(r1.text)

    # Step 2: swap refresh token -> short-lived access token (the "pass")
    r2 = await client.get(
        f"{BASE}/restWizappservice/getAccessToken",
        params={"GroupCode": GROUP_CODE},
        headers={"Authorization": f"Bearer {refresh_token}"},
    )
    r2.raise_for_status()
    return _extract_token(r2.text)


@mcp.tool()
async def get_stock_analysis_report(from_date: str = "", to_date: str = "") -> str:
    """Fetch the SoftInfo Stock Analysis report and return its data.

    Optional dates use the format YYYY-MM-DD (for example 2026-06-01).
    If no dates are given, today's date is used for both the start and end.
    """
    missing = [n for n, v in [
        ("WIZAPP_GROUP_CODE", GROUP_CODE), ("WIZAPP_USERNAME", USERNAME),
        ("WIZAPP_PASSWORD", PASSWORD), ("REPORT_ID", REPORT_ID),
        ("FILTER_ID", FILTER_ID),
    ] if not v]
    if missing:
        return ("Setup not finished. These values are not set in Render yet: "
                + ", ".join(missing))

    today = date.today().isoformat()
    from_date = from_date or today
    to_date = to_date or today

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            access_token = await _get_access_token(client)

            # Step 3: request the report -> get back where the file lives
            r3 = await client.post(
                f"{BASE}/wowservice/GetReportOutput",
                params={
                    "ReportId": REPORT_ID,
                    "FromDate": from_date,
                    "ToDate": to_date,
                    "primaryFilterId": FILTER_ID,
                    "outputFormat": "csv",
                },
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {access_token}",
                },
                json=[],
            )
            r3.raise_for_status()

            try:
                meta = r3.json()
            except Exception:
                return ("The report request did not return the expected info. "
                        f"Raw reply:\n{r3.text[:1500]}")

            file_url = ""
            if isinstance(meta, dict):
                file_url = meta.get("urlFilePath") or meta.get("UrlFilePath") or ""
            if not file_url:
                return ("No file location came back. Full reply:\n"
                        f"{json.dumps(meta)[:1500]}")

            # Step 4: download the actual file (spaces in the name need encoding)
            r4 = await client.get(file_url.replace(" ", "%20"))
            r4.raise_for_status()
            csv_text = r4.text

        return f"Stock Analysis report ({from_date} to {to_date}):\n\n{csv_text}"

    except httpx.HTTPStatusError as e:
        return (f"The server replied with an error at one step "
                f"(status {e.response.status_code}). Reply: {e.response.text[:800]}")
    except Exception as e:
        return f"Something went wrong while fetching the report: {e}"


if __name__ == "__main__":
    mcp.run(transport="streamable-http")

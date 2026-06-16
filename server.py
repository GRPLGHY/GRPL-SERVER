import os
import json
import httpx
from datetime import date
from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# THE LOGIN  -  set these three on Render as environment variables:
#     WIZAPP_GROUP_CODE   the GroupCode  (avn0116)
#     WIZAPP_USERNAME     the userName from SoftInfo's document
#     WIZAPP_PASSWORD     the passwd from the document  (NO spaces)
# Nothing secret is written in this file.
#
# THE REPORT CODES  -  not secret. If SoftInfo ever changes a report's
# code, this is the only spot to edit (then re-upload this file):
STOCK_REPORT_ID       = "HOW0000275"   # Stock Analysis
CUSTOMER_REPORT_ID    = "HOW0000277"   # Customer Analysis
TRANSACTION_REPORT_ID = "HOW0000276"   # Transaction Analysis
# ---------------------------------------------------------------------------

GROUP_CODE = os.environ.get("WIZAPP_GROUP_CODE", "")
USERNAME   = os.environ.get("WIZAPP_USERNAME", "")
PASSWORD   = os.environ.get("WIZAPP_PASSWORD", "")

BASE = "https://wizapp.in"

mcp = FastMCP(
    "softinfo-reports",
    host="0.0.0.0",
    port=int(os.environ.get("PORT", "8000")),
)


def _extract_token(resp_text: str) -> str:
    """Login steps may return a bare token or one wrapped in JSON; handle both."""
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
    # Step 1: log in -> refresh token
    r1 = await client.post(
        f"{BASE}/restWizappservice/validateUser",
        params={"GroupCode": GROUP_CODE},
        headers={"Content-Type": "application/json"},
        json={"userName": USERNAME, "passwd": PASSWORD},
    )
    r1.raise_for_status()
    refresh_token = _extract_token(r1.text)

    # Step 2: refresh token -> short-lived access token
    r2 = await client.get(
        f"{BASE}/restWizappservice/getAccessToken",
        params={"GroupCode": GROUP_CODE},
        headers={"Authorization": f"Bearer {refresh_token}"},
    )
    r2.raise_for_status()
    return _extract_token(r2.text)


async def _fetch_report(report_id: str, from_date: str, to_date: str,
                        filter_id: str = "") -> str:
    missing = [n for n, v in [
        ("WIZAPP_GROUP_CODE", GROUP_CODE),
        ("WIZAPP_USERNAME", USERNAME),
        ("WIZAPP_PASSWORD", PASSWORD),
    ] if not v]
    if missing:
        return "Setup not finished. Not set in Render yet: " + ", ".join(missing)

    today = date.today().isoformat()
    from_date = from_date or today
    to_date = to_date or today

    params = {
        "ReportId": report_id,
        "FromDate": from_date,
        "ToDate": to_date,
        "outputFormat": "csv",
    }
    if filter_id:
        params["primaryFilterId"] = filter_id

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            access_token = await _get_access_token(client)

            # Step 3: request the report -> JSON telling us where the file is
            r3 = await client.post(
                f"{BASE}/wowservice/GetReportOutput",
                params=params,
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

        return f"Report data ({from_date} to {to_date}):\n\n{csv_text}"

    except httpx.HTTPStatusError as e:
        return (f"The server replied with an error (status "
                f"{e.response.status_code}). Reply: {e.response.text[:800]}")
    except Exception as e:
        return f"Something went wrong while fetching the report: {e}"


@mcp.tool()
async def get_stock_analysis_report(from_date: str = "", to_date: str = "") -> str:
    """Fetch the SoftInfo STOCK ANALYSIS report and return its data.

    Optional dates use the format YYYY-MM-DD (e.g. 2026-06-01). If no dates
    are given, today is used for both start and end.
    """
    return await _fetch_report(STOCK_REPORT_ID, from_date, to_date)


@mcp.tool()
async def get_customer_analysis_report(from_date: str = "", to_date: str = "") -> str:
    """Fetch the SoftInfo CUSTOMER ANALYSIS report and return its data.

    Optional dates use the format YYYY-MM-DD (e.g. 2026-06-01). If no dates
    are given, today is used for both start and end.
    """
    return await _fetch_report(CUSTOMER_REPORT_ID, from_date, to_date)


@mcp.tool()
async def get_transaction_analysis_report(from_date: str = "", to_date: str = "") -> str:
    """Fetch the SoftInfo TRANSACTION ANALYSIS report and return its data.

    Optional dates use the format YYYY-MM-DD (e.g. 2026-06-01). If no dates
    are given, today is used for both start and end.
    """
    return await _fetch_report(TRANSACTION_REPORT_ID, from_date, to_date)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")

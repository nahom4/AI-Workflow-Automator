"""Append new leads to a Google Spreadsheet (Sheets API v4, httpx)."""
from __future__ import annotations
import httpx

APPEND_URL = "https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/A1:append"

_HEADER = ["Title", "URL", "Score", "Reasons", "Source"]

async def ensure_header(sheet_id: str, access_token: str) -> None:
    """Write the header row if A1 is empty."""
    async with httpx.AsyncClient(timeout=15) as client:
        check = await client.get(
            f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/A1:E1",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        data = check.json()
        if data.get("values"):
            return
        await client.post(
            APPEND_URL.format(sheet_id=sheet_id),
            params={"valueInputOption": "RAW"},
            headers={"Authorization": f"Bearer {access_token}"},
            json={"values": [_HEADER]},
        )

async def append_leads(
    *,
    sheet_id: str,
    access_token: str,
    leads: list[dict],
) -> int:
    """Append lead rows; returns number of rows written. Raises on API error."""
    if not leads:
        return 0
    await ensure_header(sheet_id, access_token)
    rows = [
        [
            lead.get("title", ""),
            lead.get("url", ""),
            str(round(float(lead.get("score", 0)), 1)),
            lead.get("matched_reasons", ""),
            lead.get("source_domain", ""),
        ]
        for lead in leads
    ]
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            APPEND_URL.format(sheet_id=sheet_id),
            params={"valueInputOption": "RAW"},
            headers={"Authorization": f"Bearer {access_token}"},
            json={"values": rows},
        )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Sheets API error {resp.status_code}: {resp.text[:200]}")
    return len(rows)

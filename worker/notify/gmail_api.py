"""Send lead digest via Gmail API (OAuth2 access token, httpx)."""
from __future__ import annotations
import base64
import email.mime.multipart
import email.mime.text
import httpx

SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"

def _build_raw(*, to: str, sender: str, subject: str, html: str) -> str:
    msg = email.mime.multipart.MIMEMultipart("alternative")
    msg["To"] = to
    msg["From"] = sender
    msg["Subject"] = subject
    msg.attach(email.mime.text.MIMEText(html, "html"))
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    return raw

def _leads_html(automation_name: str, leads: list[dict]) -> str:
    rows = "".join(
        f'<tr><td style="padding:6px 12px;border-bottom:1px solid #eee">'
        f'<a href="{l.get("url","")}">{l.get("title","")}</a></td>'
        f'<td style="padding:6px 12px;border-bottom:1px solid #eee;color:#888">'
        f'{round(float(l.get("score",0)),1)}/10</td>'
        f'<td style="padding:6px 12px;border-bottom:1px solid #eee;color:#aaa;font-size:12px">'
        f'{l.get("matched_reasons","")}</td></tr>'
        for l in leads
    )
    return f"""
<html><body style="font-family:sans-serif;color:#222">
<h2 style="color:#4f46e5">{automation_name} — {len(leads)} new result(s)</h2>
<table style="border-collapse:collapse;width:100%">
  <thead><tr style="background:#f5f5f5">
    <th style="padding:8px 12px;text-align:left">Result</th>
    <th style="padding:8px 12px;text-align:left">Score</th>
    <th style="padding:8px 12px;text-align:left">Reasons</th>
  </tr></thead>
  <tbody>{rows}</tbody>
</table>
</body></html>"""

async def send_digest(
    *,
    to: str,
    sender_email: str,
    automation_name: str,
    leads: list[dict],
    access_token: str,
) -> None:
    """Send a lead digest email via Gmail API. Raises on failure."""
    subject = f"[Automator] {len(leads)} new result(s) — {automation_name}"
    raw = _build_raw(
        to=to,
        sender=sender_email,
        subject=subject,
        html=_leads_html(automation_name, leads),
    )
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            SEND_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            json={"raw": raw},
        )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Gmail API error {resp.status_code}: {resp.text[:200]}")

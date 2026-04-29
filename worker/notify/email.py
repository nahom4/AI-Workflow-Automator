"""Send new-lead digest emails via Resend."""

from __future__ import annotations

from worker.config import RESEND_API_KEY, RESEND_FROM


async def send_lead_digest(
    *,
    to: str,
    automation_name: str,
    leads: list[dict],
) -> None:
    if not RESEND_API_KEY:
        raise RuntimeError("RESEND_API_KEY not set")
    if not leads:
        return

    import resend  # lazy — not installed locally

    resend.api_key = RESEND_API_KEY

    items_html = "".join(
        f"<li><a href='{lead['url']}'>{lead['title']}</a> — score {lead['score']:.1f}</li>"
        for lead in leads
    )

    resend.Emails.send(
        {
            "from": RESEND_FROM,
            "to": [to],
            "subject": f"[{automation_name}] {len(leads)} new lead(s)",
            "html": f"<h2>{automation_name}</h2><ul>{items_html}</ul>",
        }
    )

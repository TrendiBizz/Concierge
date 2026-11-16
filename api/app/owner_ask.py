"""Read-only "Ask Concierge" for the business owner.

It answers from two things only: the information the owner has already added (the business brief) and today's
counts. It has no tools, so it cannot send, book, change or look anything up: the worst a wrong answer can do is be wrong.
"""
from . import db, llm, owner_knowledge, sales

MAX_BRIEF = 6000

SYSTEM = (
    "You answer questions for the owner of a small business, using ONLY the business brief and the figures below. "
    "If the answer is not there, say you do not have it and suggest adding it under Business information. "
    "You cannot send messages, change anything or contact anyone, and you must not claim to. Be short and plain.\n\n"
    "{brief}\n\n{figures}")


async def brief(tenant: dict) -> str:
    """The business brief: profile fields plus the text of the owner's own knowledge documents."""
    lines = [f"Business: {tenant['name']}"]
    for key, label in (("site_url", "Website"), ("greeting", "Greeting"), ("business_phone", "Phone"),
                       ("business_address", "Address"), ("timezone", "Timezone")):
        if tenant.get(key):
            lines.append(f"{label}: {tenant[key]}")
    rows = await db.pool().fetch(
        "SELECT min(title) AS title, string_agg(content, ' ' ORDER BY id) AS text FROM chunks "
        "WHERE tenant_id=$1 AND url LIKE $2 GROUP BY url ORDER BY min(title)",
        tenant["id"], owner_knowledge.PREFIX + "%")
    for r in rows:
        lines.append(f"\n## {r['title']}\n{r['text']}")
    return "\n".join(lines)[:MAX_BRIEF]


def figures(s: dict) -> str:
    return (f"Figures right now: {s['new_leads']} new leads in the last day, "
            f"{s['leads_waiting'] if s['leads_waiting'] is not None else 'unknown'} waiting for a reply, "
            f"{s['overdue_todos']} overdue to-dos.")


async def ask(tenant: dict, question: str) -> str:
    text = (question or "").strip()
    if not text:
        raise ValueError("Type a question")
    prompt = SYSTEM.format(brief=await brief(tenant), figures=figures(await sales.summary(tenant, 1)))
    reply = await llm.complete([{"role": "system", "content": prompt}, {"role": "user", "content": text[:1000]}],
                               temperature=0.2, max_tokens=400)
    return (reply.content or "").strip() or "I could not answer that."

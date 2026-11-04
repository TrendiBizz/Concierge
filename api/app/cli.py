"""Command-line helper for the demo workflow.

Run inside the container:
  docker compose exec api python -m app.cli demo --name "Acme Forklifts" --url https://acme.example

or locally with DATABASE_URL / XAI_API_KEY set:
  python -m app.cli demo --name "Acme Forklifts" --url https://acme.example
"""

import argparse
import asyncio
import json

from . import db, ingest, tenants
from .config import get_settings


async def _demo(args: argparse.Namespace) -> None:
    settings = get_settings()
    await db.init()
    try:
        tenant = await tenants.create(args.name, args.url, slug=args.slug, incentive=args.incentive or "")
        print(f"Created tenant '{tenant['slug']}'")

        print(f"Crawling {args.url} (up to {args.max_pages} pages)...")
        result = await ingest.ingest_site(tenant, max_pages=args.max_pages)
        print(f"Indexed {result['pages']} pages / {result['chunks']} chunks")
        if result["chunks"] == 0:
            print(
                "WARNING: nothing indexed. The site may render with JavaScript or block bots. "
                "Paste content in with POST /admin/tenants/<slug>/ingest-text instead."
            )

        questions: list[str] = []
        if result["chunks"] and settings.anthropic_api_key:
            questions = await ingest.generate_demo_questions(tenant)

        base = settings.public_base_url
        print()
        print(f"Demo page (presenter view): {base}/demo/{tenant['slug']}?presenter=1")
        print("Embed snippet:")
        print(f'  <script src="{base}/widget.js" data-key="{tenant["public_key"]}" defer></script>')
        if questions:
            print("Questions to ask in the demo:")
            for i, q in enumerate(questions, 1):
                print(f"  {i}. {q}")
    finally:
        await db.close()


async def _crawl(args: argparse.Namespace) -> None:
    await db.init()
    try:
        tenant = await tenants.get_by_slug(args.slug)
        if tenant is None:
            raise SystemExit(f"Unknown tenant: {args.slug}")
        print(json.dumps(await ingest.ingest_site(tenant, max_pages=args.max_pages)))
    finally:
        await db.close()


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    demo = sub.add_parser("demo", help="Create a tenant, crawl its site, and print the demo URL + test questions")
    demo.add_argument("--name", required=True)
    demo.add_argument("--url", required=True)
    demo.add_argument("--slug")
    demo.add_argument("--incentive", help="e.g. '10% off when you book online'")
    demo.add_argument("--max-pages", type=int, default=30)
    demo.set_defaults(func=_demo)

    crawl = sub.add_parser("crawl", help="Re-crawl an existing tenant")
    crawl.add_argument("slug")
    crawl.add_argument("--max-pages", type=int, default=40)
    crawl.set_defaults(func=_crawl)

    args = parser.parse_args()
    asyncio.run(args.func(args))


if __name__ == "__main__":
    main()

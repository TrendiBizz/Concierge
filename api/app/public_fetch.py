"""Bounded HTTPS requests pinned to verified public IPs, including redirects and webhooks."""
import asyncio
import ipaddress
import socket
from urllib.parse import SplitResult, urljoin, urlsplit
import httpx

MAX_BYTES = 3_000_000
MAX_WEBHOOK_RESPONSE_BYTES = 65_536


def _is_public_ip(ip: str) -> bool:
    """True only for globally routable unicast internet addresses (unwrapping IPv4-mapped IPv6)."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped
    return (
        addr.is_global
        and not addr.is_private
        and not addr.is_loopback
        and not addr.is_link_local
        and not addr.is_multicast
        and not addr.is_reserved
        and not addr.is_unspecified
    )


def validate_public_https_url(url: str) -> SplitResult:
    """Validate that a URL is a plain public HTTPS URL on port 443 with no credentials."""
    if not isinstance(url, str):
        raise ValueError('Webhook URL must be a public HTTPS address')
    cleaned = url.strip()
    if not cleaned or any(ch.isspace() or ord(ch) < 32 for ch in cleaned):
        raise ValueError('Webhook URL must be a public HTTPS address')
    parts = urlsplit(cleaned)
    if (parts.scheme.lower() != 'https' or not parts.hostname
            or parts.username or parts.password or parts.port not in (None, 443)):
        raise ValueError('Webhook URL must be a public HTTPS address on port 443')
    host = parts.hostname.rstrip('.').lower()
    if not host or host == 'localhost' or host.endswith('.localhost') or host.endswith('.internal'):
        raise ValueError('Webhook URL must resolve only to public internet addresses')
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        if not _is_public_ip(host):
            raise ValueError('Webhook URL must resolve only to public internet addresses')
    return parts


async def public_addresses(host):
    try:
        rows = await asyncio.get_running_loop().getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        addresses = list(dict.fromkeys(row[4][0] for row in rows))
        if not addresses or any(not _is_public_ip(ip) for ip in addresses):
            raise ValueError('Website must resolve only to public internet addresses')
        return addresses
    except socket.gaierror:
        raise ValueError('Website hostname could not be resolved') from None


async def validate_webhook_url(url: str) -> tuple[SplitResult, list[str]]:
    """Validate URL syntax and confirm DNS resolves strictly to public internet addresses."""
    parts = validate_public_https_url(url)
    addresses = await public_addresses(parts.hostname)
    return parts, addresses


async def post_public(
    url: str,
    *,
    content: bytes | str,
    headers: dict[str, str] | None = None,
    timeout: float = 10.0,
    client: httpx.AsyncClient | None = None,
) -> httpx.Response:
    """POST to a verified public HTTPS endpoint pinned to its validated IP; never follows redirects."""
    parts, addresses = await validate_webhook_url(url)
    target = httpx.URL(url.strip()).copy_with(host=addresses[0])
    req_headers = dict(headers or {})
    req_headers['Host'] = parts.hostname
    owns_client = client is None
    if owns_client:
        client = httpx.AsyncClient(timeout=timeout, follow_redirects=False)
    try:
        async with client.stream(
            'POST',
            target,
            content=content,
            headers=req_headers,
            extensions={'sni_hostname': parts.hostname},
            follow_redirects=False,
        ) as response:
            body = bytearray()
            async for chunk in response.aiter_bytes():
                remaining = MAX_WEBHOOK_RESPONSE_BYTES - len(body)
                if remaining <= 0:
                    break
                body.extend(chunk[:remaining])
            return httpx.Response(
                response.status_code,
                headers={
                    k: v for k, v in response.headers.items()
                    if k.lower() not in ('content-encoding', 'content-length', 'transfer-encoding')
                },
                content=bytes(body),
                request=httpx.Request('POST', url.strip()),
            )
    finally:
        if owns_client:
            await client.aclose()


class PublicClient:
    def __init__(self, client, host):
        self.client = client
        self.host = host.lower().removeprefix('www.')

    async def get(self, url):
        for _ in range(6):
            parts = urlsplit(url)
            if (parts.scheme != 'https' or not parts.hostname or parts.username or parts.password
                    or parts.port not in (None, 443) or parts.hostname.lower().removeprefix('www.') != self.host):
                raise ValueError('Website imports require same-site public HTTPS addresses')
            addresses = await public_addresses(parts.hostname)
            # Connect to the validated address, retaining TLS hostname verification.
            target = httpx.URL(url).copy_with(host=addresses[0])
            async with self.client.stream('GET', target, headers={'Host': parts.hostname},
                                          extensions={'sni_hostname': parts.hostname}) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers.get('location', ''))
                    continue
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    content.extend(chunk)
                    if len(content) > MAX_BYTES:
                        raise ValueError('Website response exceeds import size limit')
                return httpx.Response(response.status_code, headers={k: v for k, v in response.headers.items() if k.lower() not in ('content-encoding', 'content-length', 'transfer-encoding')}, content=bytes(content), request=httpx.Request('GET', url))
        raise ValueError('Too many website redirects')

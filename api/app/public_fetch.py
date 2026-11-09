"""Bounded HTTPS requests pinned to verified public IPs, including redirects."""
import asyncio
import ipaddress
import socket
from urllib.parse import urljoin, urlsplit
import httpx

MAX_BYTES = 3_000_000


async def public_addresses(host):
    try:
        rows = await asyncio.get_running_loop().getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        addresses = list(dict.fromkeys(row[4][0] for row in rows))
        if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
            raise ValueError('Website must resolve only to public internet addresses')
        return addresses
    except socket.gaierror:
        raise ValueError('Website hostname could not be resolved') from None


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

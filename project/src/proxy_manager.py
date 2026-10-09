# -*- coding: utf-8 -*-
"""
Proxy manager — loads proxies from file, rotates them across sessions.
Supports socks5:// and http:// formats with auth.
"""
import os
import time
import random
import asyncio
from dataclasses import dataclass, field


@dataclass
class Proxy:
    raw: str
    protocol: str = "socks5"
    host: str = ""
    port: int = 0
    username: str = ""
    password: str = ""
    uses: int = 0
    fails: int = 0
    successes: int = 0
    last_used: float = 0.0
    available: bool = True

    @property
    def key(self):
        return f"{self.host}:{self.port}"


class ProxyManager:
    def __init__(self, proxy_file="proxy.txt"):
        self.proxies: list[Proxy] = []
        self.lock = asyncio.Lock()
        self._idx = 0
        self._load(proxy_file)

    def _load(self, path):
        if not os.path.isfile(path):
            return
        seen = set()
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                p = self._parse(line)
                if p and p.key not in seen:
                    seen.add(p.key)
                    self.proxies.append(p)

    @staticmethod
    def _parse(raw):
        try:
            protocol = "socks5"
            rest = raw.strip()
            for pf in ["socks5://", "socks4://", "http://", "https://"]:
                if rest.lower().startswith(pf):
                    protocol = pf.rstrip(":/")
                    rest = rest[len(pf):]
                    break

            user, password, hostpart = "", "", rest
            if "@" in rest:
                auth, hostpart = rest.rsplit("@", 1)
                if ":" in auth:
                    user, password = auth.split(":", 1)
                else:
                    user = auth

            parts = hostpart.split(":")
            if len(parts) >= 2:
                host = parts[0]
                port = int(parts[1])
            else:
                return None

            if port <= 0 or port > 65535:
                return None

            return Proxy(raw=raw, protocol=protocol, host=host, port=port,
                         username=user, password=password)
        except Exception:
            return None

    async def get(self) -> Proxy | None:
        async with self.lock:
            if not self.proxies:
                return None
            available = [p for p in self.proxies if p.available]
            if not available:
                return None
            p = available[self._idx % len(available)]
            self._idx += 1
            p.uses += 1
            p.last_used = time.time()
            return p

    async def release(self, proxy: Proxy, success: bool):
        async with self.lock:
            if success:
                proxy.successes += 1
                proxy.fails = 0
            else:
                proxy.fails += 1
                if proxy.fails >= 5:
                    proxy.available = False

    def get_playwright_config(self, proxy: Proxy | None = None):
        if proxy is None:
            return None
        return {
            "server": f"{proxy.protocol}://{proxy.host}:{proxy.port}",
            "username": proxy.username or None,
            "password": proxy.password or None,
        }

    def get_aiohttp_connector(self, proxy: Proxy | None = None):
        if proxy is None:
            return None
        from aiohttp_socks import ProxyConnector, ProxyType
        pt_map = {"socks5": ProxyType.SOCKS5, "socks4": ProxyType.SOCKS4, "http": ProxyType.HTTP}
        pt = pt_map.get(proxy.protocol, ProxyType.SOCKS5)
        return ProxyConnector(
            proxy_type=pt,
            host=proxy.host,
            port=proxy.port,
            username=proxy.username or None,
            password=proxy.password or None,
            rdns=True,
        )

    @property
    def total(self):
        return len(self.proxies)

    @property
    def available_count(self):
        return sum(1 for p in self.proxies if p.available)

    def stats(self):
        return {
            "total": len(self.proxies),
            "available": self.available_count,
            "dead": sum(1 for p in self.proxies if not p.available),
        }
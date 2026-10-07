from __future__ import annotations
import re
from .models import RoutingDecision

HOST = {
    "cpu", "memory", "ram", "disk", "ssd", "nvme", "driver", "windows", "boot",
    "process", "gpu", "freeze", "crash", "slow", "storage", "update"
}
NETWORK = {
    "internet", "wifi", "wi-fi", "ethernet", "dns", "dhcp", "gateway", "router",
    "latency", "packet", "loss", "vpn", "network", "disconnect", "connection"
}


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9-]+", text.lower()))


def route(symptom: str) -> RoutingDecision:
    tokens = _tokens(symptom)
    h = sorted(tokens & HOST)
    n = sorted(tokens & NETWORK)
    if h and n:
        # A single generic crossover term (for example latency/freeze) should not
        # force both engines when one domain has materially stronger signal.
        if len(h) >= len(n) + 2:
            return RoutingDecision("host", ("host",),
                                   (f"host signal dominates: {', '.join(h)}", f"secondary network terms: {', '.join(n)}"), False)
        if len(n) >= len(h) + 2:
            return RoutingDecision("network", ("network",),
                                   (f"network signal dominates: {', '.join(n)}", f"secondary host terms: {', '.join(h)}"), False)
        return RoutingDecision("mixed", ("host", "network", "correlation"),
                               (f"host terms: {', '.join(h)}", f"network terms: {', '.join(n)}"), True)
    if n:
        return RoutingDecision("network", ("network",), (f"network terms: {', '.join(n)}",), False)
    if h:
        return RoutingDecision("host", ("host",), (f"host terms: {', '.join(h)}",), False)
    return RoutingDecision("unknown", ("host", "network"),
                           ("symptom lacks enough deterministic routing signal",), True)

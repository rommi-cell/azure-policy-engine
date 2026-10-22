"""NSG rule evaluation (simulated Azure Network Security Groups).

Rules are checked in priority order (lowest number first). The first rule
that matches the traffic decides Allow or Deny. If no rule matches, the
traffic is denied, which mirrors Azure's default deny for inbound traffic.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class NsgRule:
    name: str
    priority: int
    direction: str       # "Inbound" or "Outbound"
    protocol: str        # "TCP", "UDP", or "*"
    port: str            # a number such as "443", or "*"
    access: str          # "Allow" or "Deny"


@dataclass
class Decision:
    allowed: bool
    matched_rule: Optional[NsgRule]
    explanation: str


def port_matches(rule_port: str, requested_port: int) -> bool:
    return rule_port == "*" or rule_port == str(requested_port)


def protocol_matches(rule_protocol: str, requested_protocol: str) -> bool:
    return rule_protocol == "*" or rule_protocol.upper() == requested_protocol.upper()


def evaluate_nsg(rules, direction, protocol, port) -> Decision:
    """Return the decision for one traffic flow, using the first matching rule by priority."""
    for rule in sorted(rules, key=lambda r: r.priority):
        if rule.direction != direction:
            continue
        if not protocol_matches(rule.protocol, protocol):
            continue
        if not port_matches(rule.port, port):
            continue
        allowed = rule.access == "Allow"
        verb = "allowed" if allowed else "blocked"
        return Decision(
            allowed=allowed,
            matched_rule=rule,
            explanation=f"Traffic {verb} by rule '{rule.name}' (priority {rule.priority}).",
        )
    return Decision(
        allowed=False,
        matched_rule=None,
        explanation="No rule matched, so traffic is blocked by the default deny.",
    )
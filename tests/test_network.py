from app.network import NsgRule, evaluate_nsg


def test_lower_priority_number_wins():
    rules = [
        NsgRule("allow-https", 200, "Inbound", "TCP", "443", "Allow"),
        NsgRule("deny-all", 100, "Inbound", "*", "*", "Deny"),
    ]
    decision = evaluate_nsg(rules, "Inbound", "TCP", 443)
    assert decision.allowed is False
    assert decision.matched_rule.name == "deny-all"


def test_specific_allow_before_deny_all():
    rules = [
        NsgRule("allow-https", 100, "Inbound", "TCP", "443", "Allow"),
        NsgRule("deny-all", 200, "Inbound", "*", "*", "Deny"),
    ]
    decision = evaluate_nsg(rules, "Inbound", "TCP", 443)
    assert decision.allowed is True
    assert decision.matched_rule.name == "allow-https"


def test_no_matching_rule_is_denied_by_default():
    rules = [NsgRule("allow-https", 100, "Inbound", "TCP", "443", "Allow")]
    decision = evaluate_nsg(rules, "Inbound", "TCP", 22)
    assert decision.allowed is False
    assert decision.matched_rule is None


def test_direction_is_respected():
    rules = [NsgRule("allow-out", 100, "Outbound", "TCP", "443", "Allow")]
    decision = evaluate_nsg(rules, "Inbound", "TCP", 443)
    assert decision.allowed is False


def test_protocol_must_match():
    rules = [NsgRule("allow-udp", 100, "Inbound", "UDP", "53", "Allow")]
    decision = evaluate_nsg(rules, "Inbound", "TCP", 53)
    assert decision.allowed is False


def test_wildcard_port_and_protocol_match():
    rules = [NsgRule("allow-all", 100, "Inbound", "*", "*", "Allow")]
    decision = evaluate_nsg(rules, "Inbound", "UDP", 8080)
    assert decision.allowed is True
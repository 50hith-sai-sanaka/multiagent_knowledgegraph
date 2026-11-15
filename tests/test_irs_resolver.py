"""
Tests for Identity Resolution Service (IRS)
File: tests/test_irs_resolver.py
Story: STORY-002
"""

from src.irs.resolver import IdentityResolutionService
from src.schemas.models import GraphOperation


def test_malware_alias_normalization_and_whitespace():
    irs = IdentityResolutionService()
    assert irs.canonicalize_target("Malware", "Heodo") == "emotet"
    assert irs.canonicalize_target("Malware", "Geodo") == "emotet"
    assert irs.canonicalize_target("Malware", "Emotet") == "emotet"
    assert irs.canonicalize_target("Malware", "RedLine") == "redline stealer"
    assert irs.canonicalize_target("Malware", "QakBot") == "qbot"
    assert irs.canonicalize_target("Malware", "Unknown-Malware!") == "unknown malware"
    assert irs.canonicalize_target("Malware", "Unknown   Malware") == "unknown malware"


def test_ioc_defanging_and_canonicalization():
    irs = IdentityResolutionService()
    # IPv4 with port and defang
    assert irs.canonicalize_ioc("ip", "185.220.101.4:8080") == "185.220.101.4"
    assert irs.canonicalize_ioc("ip", "185[.]220[.]101[.]4") == "185.220.101.4"

    # IPv6 preservation (must NOT truncate on colons)
    assert irs.canonicalize_ioc("ip", "2001:0db8:85a3::8a2e:0370:7334") == "2001:0db8:85a3::8a2e:0370:7334"
    assert irs.canonicalize_ioc("ip", "[2001:db8::1]:8080") == "2001:db8::1"

    # Scheme-less URL and defanged URL (RFC 3986: hostname lowercased, path/query case preserved)
    assert irs.canonicalize_ioc("url", "HXXP://Evil-C2[.]com/Gate.php?Id=AbC") == "http://evil-c2.com/Gate.php?Id=AbC"
    assert irs.canonicalize_ioc("url", "evil-c2.com/gate.php") == "http://evil-c2.com/gate.php"

    # Domain
    assert irs.canonicalize_ioc("domain", "EVIL-C2[.]COM.") == "evil-c2.com"

    # Hash lowercasing
    assert (
        irs.canonicalize_ioc("sha256", "E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855")
        == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )


def test_deterministic_sorted_lock_keys():
    irs = IdentityResolutionService()
    # Functional edge
    keys = irs.build_lock_keys("IP", "185.220.101.4", "USES_C2", is_functional=True)
    assert len(keys) == 2
    assert keys == sorted(keys)
    assert keys == ["entity:ip:185.220.101.4", "slot:ip:185.220.101.4:uses_c2"]

    # Non-functional edge has no slot lock
    keys_non_func = irs.build_lock_keys("IP", "185.220.101.4", "HOSTED_ON", is_functional=False)
    assert len(keys_non_func) == 1
    assert keys_non_func == ["entity:ip:185.220.101.4"]

    # Pure node operation has no slot lock
    keys_node = irs.build_lock_keys("IP", "185.220.101.4")
    assert keys_node == ["entity:ip:185.220.101.4"]


def test_canonicalize_operation():
    irs = IdentityResolutionService()
    raw_op = GraphOperation(
        operation="create_edge",
        lock_keys=["placeholder"],
        node_label="IP",
        node_value="185.220.101.4:443",
        predicate="USES_C2",
        target_label="Malware",
        target_value="Heodo",
        is_functional=True,
    )
    canon_op = irs.canonicalize_operation(raw_op)
    assert canon_op.node_value == "185.220.101.4"
    assert canon_op.target_value == "emotet"
    assert canon_op.lock_keys == ["entity:ip:185.220.101.4", "slot:ip:185.220.101.4:uses_c2"]

    # Verify pure node op leaves lock_keys with only entity key
    node_op = GraphOperation(
        operation="create_node",
        lock_keys=["placeholder"],
        node_label="IP",
        node_value="10.0.0.1",
    )
    canon_node_op = irs.canonicalize_operation(node_op)
    assert canon_node_op.lock_keys == ["entity:ip:10.0.0.1"]


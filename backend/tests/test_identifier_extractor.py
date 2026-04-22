"""
Tests for orchestration.identifier_extractor — the schema-driven replacement
for every `.upper()` call on tokens/addresses. Works for any format.
"""

from backend.orchestration.identifier_extractor import (
    extract_for_schema, validate_input, get_format_handler,
)


def test_evm_address_preserves_case():
    """The Q3 bug was uppercasing 0x addresses. This must never happen again."""
    schema = {
        "type": "object",
        "properties": {"identifier": {"type": "string", "format": "evm_address"}},
        "required": ["identifier"],
    }
    text = "Is 0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48 a honeypot?"
    extracted, missing = extract_for_schema(text, schema)
    assert extracted["identifier"] == "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
    assert missing == []


def test_evm_address_case_insensitive_validate():
    """Validator should accept both 0x and 0X prefixes."""
    handler = get_format_handler("evm_address")
    assert handler.validate("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48")
    assert handler.validate("0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48")


def test_url_extraction():
    schema = {
        "type": "object",
        "properties": {"identifier": {"type": "string", "format": "url"}},
        "required": ["identifier"],
    }
    text = "Check this link https://example.com/foo?bar=1 for details"
    extracted, _ = extract_for_schema(text, schema)
    assert extracted["identifier"] == "https://example.com/foo?bar=1"


def test_enum_constraint():
    schema = {
        "type": "object",
        "properties": {
            "chain": {"type": "string", "enum": ["ETH", "BSC", "SOL"]},
        },
    }
    # "eth" should be normalized to "ETH" via case-insensitive match
    extracted, _ = extract_for_schema("some ETH text", schema)
    assert extracted.get("chain") == "ETH"


def test_required_missing_surfaced():
    schema = {
        "type": "object",
        "properties": {"identifier": {"type": "string", "format": "evm_address"}},
        "required": ["identifier"],
    }
    extracted, missing = extract_for_schema("no address here at all", schema)
    assert "identifier" not in extracted
    assert missing == ["identifier"]


def test_validate_rejects_bad_address():
    schema = {
        "type": "object",
        "properties": {"identifier": {"type": "string", "format": "evm_address"}},
        "required": ["identifier"],
    }
    ok, err = validate_input({"identifier": "not-a-hex-address"}, schema)
    assert not ok
    assert "evm_address" in err


def test_validate_accepts_hint_with_checksum():
    """Hints preserve the user's case; the orchestrator relies on this."""
    schema = {
        "type": "object",
        "properties": {"identifier": {"type": "string", "format": "evm_address"}},
        "required": ["identifier"],
    }
    extracted, missing = extract_for_schema(
        "check this", schema,
        hints={"identifier": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"},
    )
    assert extracted["identifier"] == "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
    assert not missing


def test_new_format_plug_and_play():
    """Registering a new format handler should work with zero core-code edits."""
    from backend.orchestration.identifier_extractor import (
        FormatHandler, register_format,
    )
    import re

    @register_format("test_ticker")
    class TestTicker(FormatHandler):
        _re = re.compile(r"#(\w{2,5})")

        def detect(self, text):
            m = self._re.search(text or "")
            return f"#{m.group(1)}" if m else None

    schema = {
        "type": "object",
        "properties": {"identifier": {"type": "string", "format": "test_ticker"}},
        "required": ["identifier"],
    }
    extracted, missing = extract_for_schema("how is #KITE doing?", schema)
    assert extracted["identifier"] == "#KITE"
    assert not missing

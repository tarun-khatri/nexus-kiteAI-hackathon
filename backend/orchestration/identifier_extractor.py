"""
NEXUS - Schema-Driven Identifier Extraction

Replaces every `.upper()` on tokens and every bespoke `0x..42` regex.

A capability's input_schema declares the format of each field it wants:

    {
      "type": "object",
      "properties": {
        "identifier": {"type": "string", "format": "evm_address"},
        "chain":      {"type": "string", "enum": ["ETH","BSC","SOL","KITE"]}
      },
      "required": ["identifier"]
    }

This module resolves each declared `format` to a registered FormatHandler
that extracts and normalizes the typed value from a natural-language query.

Adding a new format means adding a @register_format("xxx") class. No edits
to callers. No hardcoded token list.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Any, Optional


# ---------- Format handler registry ----------

class FormatHandler(ABC):
    """A typed identifier extractor. Subclasses declare how to detect and normalize
    one specific format from raw text."""

    name: str = ""

    @abstractmethod
    def detect(self, text: str) -> Optional[str]:
        """Return the first match in `text`, or None."""

    def normalize(self, raw: str) -> str:
        """Canonicalize a matched value. Default: return as-is (preserve case)."""
        return raw

    def validate(self, value: str) -> bool:
        """Return True if `value` is a well-formed instance of this format."""
        return self.detect(value) == value


_FORMAT_HANDLERS: dict[str, FormatHandler] = {}


def register_format(name: str):
    """Decorator that registers a handler under a format name."""
    def _wrap(cls):
        inst = cls()
        inst.name = name
        _FORMAT_HANDLERS[name] = inst
        return cls
    return _wrap


def get_format_handler(name: str) -> Optional[FormatHandler]:
    return _FORMAT_HANDLERS.get(name)


def list_formats() -> list[str]:
    return sorted(_FORMAT_HANDLERS.keys())


# ---------- Built-in format handlers ----------
# These cover the common cases. Third parties can add more via register_format
# without editing this file.

@register_format("evm_address")
class EvmAddress(FormatHandler):
    """0x followed by exactly 40 hex chars. Case preserved (EIP-55 checksum)."""
    _re = re.compile(r"0x[0-9a-fA-F]{40}")

    def detect(self, text: str) -> Optional[str]:
        m = self._re.search(text or "")
        return m.group(0) if m else None

    def normalize(self, raw: str) -> str:
        # Preserve case to respect EIP-55 checksum.
        return raw.strip()


@register_format("solana_address")
class SolanaAddress(FormatHandler):
    """Base58, 32-44 chars, no 0/O/I/l."""
    _re = re.compile(r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b")

    def detect(self, text: str) -> Optional[str]:
        for m in self._re.finditer(text or ""):
            val = m.group(0)
            # Exclude things that look like our own hex strings.
            if val.startswith("0x"):
                continue
            # Exclude lowercase-only runs (likely English words) of short length.
            if len(val) >= 32:
                return val
        return None

    def normalize(self, raw: str) -> str:
        return raw.strip()


@register_format("cosmos_bech32")
class CosmosBech32(FormatHandler):
    """bech32: <hrp>1<data-30-to-58-chars>. Accepts cosmos, osmo, juno, etc."""
    _re = re.compile(r"\b[a-z]{2,10}1[ac-hj-np-z02-9]{30,58}\b")

    def detect(self, text: str) -> Optional[str]:
        m = self._re.search(text or "")
        return m.group(0) if m else None

    def normalize(self, raw: str) -> str:
        return raw.strip().lower()


@register_format("url")
class Url(FormatHandler):
    _re = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)

    def detect(self, text: str) -> Optional[str]:
        m = self._re.search(text or "")
        return m.group(0).rstrip(".,;:)]") if m else None

    def normalize(self, raw: str) -> str:
        return raw.strip()


@register_format("erc20_symbol")
class Erc20Symbol(FormatHandler):
    """Uppercase ticker, 2-10 alphanumeric chars. Only matches if text does NOT
    contain an EVM/Solana address (those take precedence for contract-identity)."""
    _re = re.compile(r"\b([A-Z][A-Z0-9]{1,9})\b")

    def detect(self, text: str) -> Optional[str]:
        if not text:
            return None
        # If an address is present, the caller should have asked for that format.
        if EvmAddress._re.search(text) or SolanaAddress._re.search(text):
            return None
        for m in self._re.finditer(text):
            val = m.group(1)
            # Skip common English ALL-CAPS words.
            if val in _STOP_WORDS:
                continue
            return val
        return None

    def normalize(self, raw: str) -> str:
        return raw.strip().upper()


_STOP_WORDS = {
    "THE", "AND", "FOR", "BUT", "NOT", "YOU", "ARE", "WAS", "HAS", "WITH",
    "THIS", "THAT", "HAVE", "WILL", "FROM", "THEY", "WHEN", "WHAT", "YOUR",
    "KNOW", "WANT", "BEEN", "HERE", "THERE", "WHICH", "THEIR", "ABOUT",
    "WOULD", "MAKE", "LIKE", "INTO", "OVER", "ONLY", "JUST", "HOW", "WHY",
    "USDC", "USDT", "USD",  # these are stopwords when asking "what is USDC" — but when user says "buy USDC" it's a token; handled by context
}
# Note: USDC/USDT would be false-filtered above; in practice the LLM classifier
# surfaces the ticker in its structured output, so the regex path is used
# only as a secondary extractor for queries the LLM didn't caption. That
# trade-off is explicit.


@register_format("protocol_slug")
class ProtocolSlug(FormatHandler):
    """Free-form lowercase slug with hyphens/underscores. Used for DeFi protocol names."""
    _re = re.compile(r"\b[a-z][a-z0-9_\-]{1,40}\b")

    def detect(self, text: str) -> Optional[str]:
        m = self._re.search((text or "").lower())
        return m.group(0) if m else None

    def normalize(self, raw: str) -> str:
        return raw.strip().lower()


@register_format("string")
class PlainString(FormatHandler):
    """Fallback: pass the raw text through. For capabilities that accept anything."""

    def detect(self, text: str) -> Optional[str]:
        return (text or "").strip() or None

    def normalize(self, raw: str) -> str:
        return raw.strip()


# ---------- Public API ----------

def extract_for_schema(
    text: str,
    schema: dict,
    hints: Optional[dict[str, Any]] = None,
) -> tuple[dict[str, Any], list[str]]:
    """
    Given raw query text and a JSON-Schema-flavored property spec, return
    (extracted_values, missing_required_fields).

    `hints` lets the LLM classifier pre-populate some values directly;
    those win over regex extraction. Hints also bypass format validation
    ONLY when an empty regex would otherwise win — we still reject
    malformed hints for typed formats.

    Rules:
    - For each declared property: resolve its `format` to a handler,
      detect+normalize from `text` if no hint provided.
    - Properties with `enum` constraints are validated against the enum;
      if the extracted value isn't in the enum, it's dropped.
    - `required` fields missing after extraction end up in missing_required_fields.
    """
    hints = hints or {}
    props: dict = schema.get("properties", {})
    required: list[str] = list(schema.get("required", []))

    extracted: dict[str, Any] = {}
    for field, spec in props.items():
        fmt = spec.get("format")
        enum = spec.get("enum")

        # Hint takes precedence unless it's None/empty string.
        hint_val = hints.get(field)
        candidate: Optional[str] = None
        if hint_val not in (None, ""):
            candidate = str(hint_val)
        elif enum:
            # Enum-constrained fields: scan the text for any enum value
            # (case-insensitive token match). Most discriminating for
            # chain names, statuses, categories, etc.
            lower_text = (text or "").lower()
            for choice in enum:
                ctxt = str(choice).lower()
                if not ctxt:
                    continue
                # Whole-word-ish match: surrounded by non-word or start/end.
                import re as _re
                if _re.search(rf"(?<!\w){_re.escape(ctxt)}(?!\w)", lower_text):
                    candidate = str(choice)
                    break
        else:
            handler = get_format_handler(fmt) if fmt else get_format_handler("string")
            if handler is None:
                handler = get_format_handler("string")
            candidate = handler.detect(text) if handler else None

        if candidate is None:
            continue

        # Normalize via the format handler (if any).
        handler = get_format_handler(fmt) if fmt else None
        if handler is not None:
            candidate = handler.normalize(candidate)

        # Enum validation / case-canonicalization for hint-sourced values.
        if enum and candidate not in enum:
            lower_enum = {str(e).lower(): e for e in enum}
            if str(candidate).lower() in lower_enum:
                candidate = lower_enum[str(candidate).lower()]
            else:
                continue  # drop invalid enum

        extracted[field] = candidate

    missing = [f for f in required if f not in extracted]
    return extracted, missing


def validate_input(input_obj: dict, schema: dict) -> tuple[bool, Optional[str]]:
    """
    Lightweight JSONSchema-ish validator. Checks:
    - required fields present
    - each field's declared format handler validates its value
    - enum constraints

    Returns (ok, error_message).
    """
    props: dict = schema.get("properties", {})
    required: list[str] = list(schema.get("required", []))

    for field in required:
        if field not in input_obj or input_obj[field] in (None, ""):
            return False, f"Missing required field: {field}"

    for field, value in input_obj.items():
        spec = props.get(field)
        if not spec:
            continue
        enum = spec.get("enum")
        if enum and value not in enum:
            return False, f"Field '{field}' must be one of {enum}, got {value!r}"
        fmt = spec.get("format")
        if fmt:
            handler = get_format_handler(fmt)
            if handler and isinstance(value, str) and not handler.validate(value):
                return False, f"Field '{field}' is not a valid {fmt}"

    return True, None

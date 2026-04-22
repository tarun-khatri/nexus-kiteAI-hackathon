"""
Tests for the crypto-signal safety-net in DiscoveryEngine.

The heuristic's job: reject obviously off-topic queries (like pop music,
weather, recipes) even when the LLM force-fits them to a capability.
It MUST NOT reject legitimate crypto queries.
"""

from backend.marketplace.discovery import discovery_engine


# === Off-topic queries — MUST be detected as NO crypto signal ===

def test_taylor_swift_is_not_crypto():
    assert not discovery_engine._has_crypto_signal(
        "can you let me know what does the taylor swift new song mean?"
    )


def test_weather_is_not_crypto():
    assert not discovery_engine._has_crypto_signal("what's the weather in tokyo tomorrow")


def test_recipe_is_not_crypto():
    assert not discovery_engine._has_crypto_signal("recipe for chocolate chip cookies")


def test_general_news_is_not_crypto():
    assert not discovery_engine._has_crypto_signal(
        "summarize news about the french presidential election"
    )


def test_geography_is_not_crypto():
    assert not discovery_engine._has_crypto_signal("what is the capital of france")


def test_empty_is_not_crypto():
    assert not discovery_engine._has_crypto_signal("")
    assert not discovery_engine._has_crypto_signal("   ")


# === Legitimate crypto queries — MUST be detected as having signal ===

def test_token_symbol_is_crypto():
    assert discovery_engine._has_crypto_signal("what's the sentiment on BTC")
    assert discovery_engine._has_crypto_signal("analyze ETH")
    # Lowercased still matches.
    assert discovery_engine._has_crypto_signal("eth price today")


def test_context_keyword_is_crypto():
    assert discovery_engine._has_crypto_signal("best DeFi yields on Arbitrum")
    assert discovery_engine._has_crypto_signal("top NFTs by volume")
    assert discovery_engine._has_crypto_signal("is this token a rug?")
    assert discovery_engine._has_crypto_signal("honeypot check on this address")
    assert discovery_engine._has_crypto_signal("liquidity depth for UNI")
    assert discovery_engine._has_crypto_signal("TVL trend on Ethereum")


def test_evm_address_is_crypto():
    assert discovery_engine._has_crypto_signal(
        "is 0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48 safe?"
    )
    # Even without any crypto keyword, the address alone is enough.
    assert discovery_engine._has_crypto_signal(
        "what about 0xdAC17F958D2ee523a2206206994597C13D831ec7"
    )


def test_multi_word_context_phrase():
    assert discovery_engine._has_crypto_signal("check the contract address for KITE")
    assert discovery_engine._has_crypto_signal("market cap leaders this week")


def test_chain_name_is_crypto():
    assert discovery_engine._has_crypto_signal("bitcoin fear and greed index today")
    assert discovery_engine._has_crypto_signal("solana network congestion")


def test_punctuation_does_not_block_match():
    # Common punctuation around a keyword shouldn't hide it.
    assert discovery_engine._has_crypto_signal("is ETH pumping?!")
    assert discovery_engine._has_crypto_signal("(defi) yields...")

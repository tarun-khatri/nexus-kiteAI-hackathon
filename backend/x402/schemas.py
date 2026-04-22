"""
NEXUS - x402 Output Schemas for Agent Services
Defines input/output schemas per Kite's x402 service provider spec.
Ref: https://docs.gokite.ai/kite-agent-passport/service-provider-guide

These schemas are included in the HTTP 402 response so that
AI agents (and the Kite MCP layer) can discover what each service
accepts and returns - enabling autonomous agent-to-agent interaction.
"""


DATA_AGENT_SCHEMA = {
    "input": {
        "discoverable": True,
        "method": "POST",
        "type": "http",
        "body": {
            "query": {
                "description": "Token symbol to analyze (e.g. KITE, BTC, ETH)",
                "required": True,
                "type": "string",
            },
            "data_types": {
                "description": "Data categories to fetch",
                "type": "array",
                "default": ["twitter", "price", "whale", "news", "historical"],
                "items": {
                    "type": "string",
                    "enum": ["twitter", "price", "whale", "news", "historical", "fear_greed"],
                },
            },
        },
    },
    "output": {
        "properties": {
            "data": {
                "description": "Collected data from all requested sources",
                "type": "object",
                "properties": {
                    "twitter": {"description": "Tweets and social mentions", "type": "object"},
                    "price": {"description": "Current price, volume, market cap", "type": "object"},
                    "whale": {"description": "Large transactions and whale activity", "type": "object"},
                    "news": {"description": "Recent news articles", "type": "object"},
                    "historical": {"description": "Historical price data for technical analysis", "type": "array"},
                },
            },
            "agent": {"description": "Agent name that collected the data", "type": "string"},
            "timestamp": {"description": "ISO 8601 collection timestamp", "type": "string"},
        },
        "required": ["data"],
        "type": "object",
    },
}


ANALYST_AGENT_SCHEMA = {
    "input": {
        "discoverable": True,
        "method": "POST",
        "type": "http",
        "body": {
            "query": {
                "description": "Token symbol to analyze",
                "required": True,
                "type": "string",
            },
            "data": {
                "description": "Raw data from DataAgent to analyze",
                "required": True,
                "type": "object",
            },
            "analysis_types": {
                "description": "Analysis types to run",
                "type": "array",
                "default": ["sentiment", "price_trend", "whale", "news"],
                "items": {
                    "type": "string",
                    "enum": ["sentiment", "price_trend", "whale", "news"],
                },
            },
        },
    },
    "output": {
        "properties": {
            "analysis": {
                "description": "Analysis results across all dimensions",
                "type": "object",
                "properties": {
                    "sentiment": {"description": "VADER + crypto-aware sentiment scores", "type": "object"},
                    "price_trend": {"description": "Technical indicators: RSI, MACD, Bollinger Bands", "type": "object"},
                    "whale": {"description": "Whale activity interpretation and signals", "type": "object"},
                    "news": {"description": "News sentiment summary", "type": "object"},
                    "overall": {"description": "Weighted verdict and confidence score", "type": "object"},
                },
            },
            "verdict": {"description": "Strong Buy / Buy / Neutral / Sell / Strong Sell", "type": "string"},
            "score": {"description": "Overall confidence score 0-100", "type": "number"},
        },
        "required": ["analysis"],
        "type": "object",
    },
}


AUDIT_AGENT_SCHEMA = {
    "input": {
        "discoverable": True,
        "method": "POST",
        "type": "http",
        "body": {
            "target_agent": {
                "description": "Name of the agent being audited",
                "required": True,
                "type": "string",
            },
            "output": {
                "description": "Agent output to verify for accuracy",
                "required": True,
                "type": "object",
            },
            "raw_inputs": {
                "description": "Original raw data for cross-reference verification",
                "type": "object",
            },
        },
    },
    "output": {
        "properties": {
            "quality_score": {"description": "Quality score 0-100", "type": "number"},
            "verified": {"description": "Whether the output passed all audit checks", "type": "boolean"},
            "passed_checks": {"description": "Number of checks that passed", "type": "integer"},
            "total_checks": {"description": "Total number of checks run", "type": "integer"},
            "checks": {
                "description": "Individual verification check results",
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "passed": {"type": "boolean"},
                        "detail": {"type": "string"},
                    },
                },
            },
        },
        "required": ["quality_score", "verified"],
        "type": "object",
    },
}

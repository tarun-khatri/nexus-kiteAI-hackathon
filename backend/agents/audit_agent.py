"""
NEXUS - AuditAgent
The Quality Inspector.

Verifies other agents' outputs for accuracy and consistency:
- Data freshness checks
- Sentiment consistency verification
- Price accuracy cross-reference
- Logical consistency analysis

Price: $0.0001 per audit
"""

import time
import random
from datetime import datetime
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from backend.agents.base_agent import BaseAgent
from backend.data_sources.coingecko import CoinGeckoClient


class AuditAgent(BaseAgent):
    """
    AuditAgent - Ensures quality and trust in the Nexus economy.
    Verifies outputs from other agents and issues quality scores.
    """

    def __init__(self):
        super().__init__(
            agent_id="audit_agent",
            name="Nexus-AuditAgent-v1",
            description="Verifies other agents' outputs for accuracy and quality",
            capabilities=["quality_audit", "data_verification", "consistency_check"],
            price_per_query=0.0001,
            keywords=[
                "audit", "verify", "quality", "validate", "check accuracy",
                "double check", "cross reference",
            ],
            example_queries=[
                "Audit the analysis",
                "Verify this report",
                "Quality check the data",
            ],
            # Data-flow declarations.
            # AuditAgent CONSUMES analysis_output (so it runs after any analyzer).
            # PROVIDES quality_score for downstream consumers.
            consumes=["analysis_output"],
            provides=["quality_score"],
        )
        self.sentiment_analyzer = SentimentIntensityAnalyzer()
        self.coingecko = CoinGeckoClient()

    def prepare_request(self, capability: str, context: dict) -> dict:
        """
        AuditAgent collects ALL previous outputs from context and audits
        them collectively. Works with ANY agent output shape -- AnalystAgent,
        DeFi, DEX, Security, or any future type.
        """
        # Collect every previous agent's output into one dict for auditing.
        all_outputs = {}
        target_name = "unknown"
        for prev_id, prev_result in (context.get("outputs") or {}).items():
            if not isinstance(prev_result, dict):
                continue
            all_outputs[prev_id] = prev_result
            # The "target" is whoever produced the most substantive output.
            if prev_result.get("agent"):
                target_name = prev_result["agent"]
        return {
            "type": "audit",
            "capability": capability,
            "target_agent": target_name,
            "output": all_outputs,       # ALL outputs, not just "analysis"
            "raw_inputs": all_outputs,   # same thing -- audit can cross-ref
        }

    async def handle_request(self, request: dict) -> dict:
        """
        Audit the outputs from other agents. DYNAMIC: works with ANY output
        shape, not just AnalystAgent. Runs generic checks (freshness,
        completeness, data presence) on whatever data was produced.
        """
        start = await self.start_work(f"Auditing {request.get('target_agent', 'unknown')}")

        target_agent = request.get("target_agent", "unknown")
        output = request.get("output", {})
        raw_inputs = request.get("raw_inputs", {})

        checks = []

        # --- DYNAMIC CHECKS: work with ANY agent output shape ---

        # Check 1: Data freshness -- look for timestamps in ANY output
        for agent_id, agent_output in (output.items() if isinstance(output, dict) else []):
            if isinstance(agent_output, dict):
                ts = agent_output.get("timestamp")
                if ts:
                    try:
                        data_time = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                        age_seconds = (datetime.utcnow() - data_time.replace(tzinfo=None)).total_seconds()
                        checks.append({
                            "check": "data_freshness",
                            "description": f"Is {agent_id} data less than 5 minutes old?",
                            "passed": age_seconds < 300,
                            "detail": f"Data age: {age_seconds:.0f}s",
                        })
                    except Exception:
                        pass

        # Check 2: Data QUALITY -- not just existence but actual useful content
        for agent_id, agent_output in (output.items() if isinstance(output, dict) else []):
            if not isinstance(agent_output, dict):
                continue

            data = agent_output.get("data")
            if isinstance(data, dict):
                # Count how many data sub-fields have actual content (not empty dicts/lists)
                non_empty = 0
                total = 0
                for k, v in data.items():
                    if k in ("source", "data_source_real", "timestamp"):
                        continue
                    total += 1
                    if isinstance(v, dict) and len(v) > 0:
                        non_empty += 1
                    elif isinstance(v, list) and len(v) > 0:
                        non_empty += 1
                    elif isinstance(v, (int, float)) and v != 0:
                        non_empty += 1
                    elif isinstance(v, str) and v:
                        non_empty += 1

                if total > 0:
                    quality_pct = (non_empty / total) * 100
                    checks.append({
                        "check": "data_quality",
                        "description": f"Does {agent_id} data have substantive content?",
                        "passed": quality_pct >= 50,  # At least half should be non-empty
                        "detail": f"{non_empty}/{total} data fields non-empty ({quality_pct:.0f}%)",
                    })

            # Check degraded sources explicitly
            degraded = agent_output.get("degraded_sources")
            if isinstance(degraded, list):
                total_sources = len(degraded) + 2  # rough estimate of total tried
                degraded_count = len(degraded)
                passed = degraded_count <= 2  # Allow up to 2 degraded sources
                checks.append({
                    "check": "source_health",
                    "description": f"Are {agent_id} data sources healthy?",
                    "passed": passed,
                    "detail": f"{degraded_count} source(s) degraded: {', '.join(degraded[:3])}",
                })

        # Check 3: If AnalystAgent ran, verify analysis completeness
        for agent_id, agent_output in (output.items() if isinstance(output, dict) else []):
            if isinstance(agent_output, dict) and "analysis" in agent_output:
                analysis = agent_output["analysis"]
                # Count how many analysis sections have content
                analysis_sections = [k for k in analysis if isinstance(analysis[k], dict) and len(analysis[k]) > 0]
                checks.append({
                    "check": "analysis_completeness",
                    "description": f"Did {agent_id} produce comprehensive analysis?",
                    "passed": len(analysis_sections) >= 3,  # Need at least 3 non-empty sections
                    "detail": f"{len(analysis_sections)} analysis sections: {', '.join(analysis_sections[:5])}",
                })

                overall = analysis.get("overall", {})
                if overall:
                    checks.append({
                        "check": "verdict_present",
                        "description": "Does the analysis include an overall verdict?",
                        "passed": bool(overall.get("verdict")) and overall.get("score", 0) > 0,
                        "detail": f"Verdict: {overall.get('verdict', 'N/A')}, Score: {overall.get('score', 0)}",
                    })

        # Check 4: If Security agent ran, verify risk score exists
        for agent_id, agent_output in (output.items() if isinstance(output, dict) else []):
            if isinstance(agent_output, dict):
                data = agent_output.get("data", {})
                if isinstance(data, dict) and "risk_score" in data:
                    checks.append({
                        "check": "security_score_valid",
                        "description": "Is the security risk assessment complete?",
                        "passed": 0 <= data["risk_score"] <= 100 and bool(data.get("risk_level")),
                        "detail": f"Risk: {data.get('risk_level', '?')} ({data['risk_score']}/100)",
                    })

        # If NO checks ran, mark as failed (we expected to verify something)
        if not checks:
            checks.append({
                "check": "no_data",
                "description": "No verifiable output from any agent",
                "passed": False,
                "detail": "Agents produced no auditable data",
            })

        passed = sum(1 for c in checks if c["passed"])
        total = len(checks)
        quality_score = int((passed / total) * 100)

        result = {
            "agent": self.name,
            "target_agent": target_agent,
            "quality_score": quality_score,
            "checks": checks,
            "passed_checks": sum(1 for c in checks if c["passed"]),
            "total_checks": len(checks),
            "verified": quality_score >= 70,
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Emit audit result to dashboard
        from backend.websocket.manager import ws_manager
        await ws_manager.emit_audit_result(self.name, target_agent, quality_score, checks)

        duration = await self.complete_work(f"Audit of {target_agent}: {quality_score}/100", start)
        result["duration_ms"] = duration

        return result

    async def check_data_freshness(self, output: dict) -> list[dict]:
        """Check if the data is recent enough"""
        checks = []
        timestamp_str = output.get("timestamp")
        if timestamp_str:
            try:
                data_time = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                age_seconds = (datetime.utcnow() - data_time.replace(tzinfo=None)).total_seconds()
                checks.append({
                    "check": "data_freshness",
                    "description": "Is the data less than 5 minutes old?",
                    "passed": age_seconds < 300,
                    "detail": f"Data age: {age_seconds:.0f} seconds",
                })
            except Exception:
                checks.append({
                    "check": "data_freshness",
                    "description": "Is the data timestamp valid?",
                    "passed": False,
                    "detail": "Could not parse timestamp",
                })
        return checks

    def check_sentiment_consistency(self, output: dict, raw_inputs: dict) -> list[dict]:
        """Re-analyze a sample of tweets to verify sentiment score"""
        checks = []
        analysis = output.get("analysis", {})
        sentiment = analysis.get("sentiment", {})
        twitter_data = raw_inputs.get("data", {}).get("twitter", {})
        tweets = twitter_data.get("tweets", [])

        if sentiment.get("average_score") is not None and tweets:
            # Re-analyze a random sample of tweets
            sample_size = min(5, len(tweets))
            sample = random.sample(tweets, sample_size)

            recheck_scores = []
            for tweet in sample:
                text = tweet.get("text", "")
                if text:
                    score = self.sentiment_analyzer.polarity_scores(text)
                    recheck_scores.append(score["compound"])

            if recheck_scores:
                recheck_avg = sum(recheck_scores) / len(recheck_scores)
                original_avg = sentiment["average_score"]
                diff = abs(original_avg - recheck_avg)

                checks.append({
                    "check": "sentiment_consistency",
                    "description": "Does re-analysis of sample tweets match the reported sentiment?",
                    "passed": diff < 0.3,  # Within 30% tolerance
                    "detail": f"Original: {original_avg:.3f}, Recheck ({sample_size} tweets): {recheck_avg:.3f}, Diff: {diff:.3f}",
                })

        return checks

    async def check_price_accuracy(self, output: dict) -> list[dict]:
        """Cross-reference reported price with a second source"""
        checks = []
        analysis = output.get("analysis", {})
        price_trend = analysis.get("price_trend", {})
        reported_price = price_trend.get("current_price")

        if reported_price and reported_price > 0:
            query = output.get("query", "KITE")
            try:
                verified_data = await self.coingecko.get_current_price(query)
                verified_price = verified_data.get("price_usd", 0)

                if verified_price > 0:
                    diff_pct = abs(reported_price - verified_price) / verified_price * 100
                    checks.append({
                        "check": "price_accuracy",
                        "description": "Does the reported price match CoinGecko within 2%?",
                        "passed": diff_pct < 2,
                        "detail": f"Reported: ${reported_price:.4f}, Verified: ${verified_price:.4f}, Diff: {diff_pct:.2f}%",
                    })
            except Exception:
                pass

        return checks

    def check_logical_consistency(self, output: dict) -> list[dict]:
        """Check if the overall assessment logically follows from the data"""
        checks = []
        analysis = output.get("analysis", {})
        overall = analysis.get("overall", {})
        sentiment = analysis.get("sentiment", {})
        price = analysis.get("price_trend", {})

        if overall and sentiment and price:
            verdict = overall.get("verdict", "")
            sentiment_verdict = sentiment.get("verdict", "")
            trend = price.get("trend", "")

            # Check: bullish verdict shouldn't come with bearish signals
            bullish_signals = 0
            bearish_signals = 0

            if "Bullish" in sentiment_verdict:
                bullish_signals += 1
            elif "Bearish" in sentiment_verdict:
                bearish_signals += 1

            if trend == "Uptrend":
                bullish_signals += 1
            elif trend == "Downtrend":
                bearish_signals += 1

            is_consistent = True
            if "Buy" in verdict and bearish_signals > bullish_signals:
                is_consistent = False
            elif "Sell" in verdict and bullish_signals > bearish_signals:
                is_consistent = False

            checks.append({
                "check": "logical_consistency",
                "description": "Does the verdict logically follow from sentiment and price data?",
                "passed": is_consistent,
                "detail": f"Verdict: {verdict}, Sentiment: {sentiment_verdict}, Trend: {trend}",
            })

        return checks

    def check_completeness(self, output: dict) -> list[dict]:
        """Check if all expected sections are present"""
        checks = []
        analysis = output.get("analysis", {})
        expected_sections = ["sentiment", "price_trend", "whale", "overall"]

        present = [s for s in expected_sections if s in analysis]
        missing = [s for s in expected_sections if s not in analysis]

        checks.append({
            "check": "completeness",
            "description": "Are all expected analysis sections present?",
            "passed": len(missing) <= 1,  # Allow 1 missing section
            "detail": f"Present: {', '.join(present)}. Missing: {', '.join(missing) or 'None'}",
        })

        return checks

    async def cleanup(self):
        await self.coingecko.close()

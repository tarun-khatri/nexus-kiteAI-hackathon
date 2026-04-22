"""
NEXUS - AnalystAgent
The Intelligence Expert.

Takes raw data from DataAgent and produces actionable insights:
- Sentiment analysis (VADER - free, local, no API needed)
- Price trend analysis (pandas/numpy - free)
- Whale activity interpretation (rule-based - free)
- News summarization (free LLM via Groq/Gemini/Ollama)

Price: $0.0002 per analysis
"""

import time
import numpy as np
import pandas as pd
from datetime import datetime
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from backend.agents.base_agent import BaseAgent
from backend.llm import llm_router


class AnalystAgent(BaseAgent):
    """
    AnalystAgent - Turns raw data into intelligence.
    Uses free, local analysis tools (VADER, pandas) + free LLMs.
    """

    def __init__(self):
        super().__init__(
            agent_id="analyst_agent",
            name="Nexus-AnalystAgent-v1",
            description="Analyzes raw data to produce sentiment scores, price trends, and insights",
            capabilities=[
                "sentiment_analysis", "price_trend", "whale_analysis",
                "news_summary", "data_analysis", "technical_analysis", "price_analysis",
            ],
            price_per_query=0.0002,
            keywords=[
                "analyze", "analysis", "sentiment", "trend", "rsi", "macd",
                "bollinger", "technical", "bullish", "bearish", "momentum",
                "forecast", "insight", "opinion", "feel", "think",
                "how is", "what about",
            ],
            example_queries=[
                "Analyze ETH sentiment",
                "Price trend for BTC",
                "Technical indicators for SOL",
                "What do people think about KITE",
            ],
            # Data-flow declarations.
            # AnalystAgent CONSUMES raw_data (any agent that produces it works).
            # AnalystAgent PROVIDES analysis_output for downstream agents.
            consumes=["raw_data"],
            provides=["analysis_output"],
        )
        # VADER sentiment analyzer - 100% free, runs locally
        self.sentiment_analyzer = SentimentIntensityAnalyzer()

    def prepare_request(self, capability: str, context: dict) -> dict:
        """
        AnalystAgent looks up raw data in the shared context (whatever previous
        agent put it there). Capability-agnostic: same analysis runs regardless
        of which specific capability triggered it (sentiment_analysis, price_trend, etc).
        """
        # Walk the previous outputs and pull the first thing that looks like data.
        raw_data = {}
        for prev_id, prev_result in (context.get("outputs") or {}).items():
            if isinstance(prev_result, dict) and isinstance(prev_result.get("data"), dict):
                raw_data = prev_result["data"]
                break
        return {
            "type": "full_analysis",
            "capability": capability,
            "query": context.get("query", "KITE"),
            "data": raw_data,
        }

    async def handle_request(self, request: dict) -> dict:
        """
        Main entry point. Receives raw data and returns analysis.
        request = {
            "type": "full_analysis",
            "query": "KITE",
            "data": { ... raw data from DataAgent ... }
        }
        """
        start = await self.start_work(f"Analyzing data for: {request.get('query', 'unknown')}")

        query = request.get("query", "KITE")
        raw_data = request.get("data", {})
        analysis_types = request.get("analysis_types", ["sentiment", "price_trend", "whale", "news", "overall"])

        result = {
            "agent": self.name,
            "query": query,
            "timestamp": datetime.utcnow().isoformat(),
            "analysis": {},
        }

        # Run requested analyses
        if "sentiment" in analysis_types and "twitter" in raw_data:
            result["analysis"]["sentiment"] = self.analyze_sentiment(raw_data["twitter"])

        if "price_trend" in analysis_types and "price" in raw_data:
            historical = raw_data.get("historical", [])
            print(f"[Analyst] Historical data points: {len(historical)}")
            result["analysis"]["price_trend"] = self.analyze_price_trend(
                raw_data["price"], historical
            )

        if "whale" in analysis_types and "whale" in raw_data:
            result["analysis"]["whale"] = self.analyze_whale_activity(raw_data["whale"])

        if "news" in analysis_types and "news" in raw_data:
            result["analysis"]["news"] = await self.analyze_news(raw_data["news"], query)

        if "overall" in analysis_types:
            result["analysis"]["overall"] = self.generate_overall_assessment(result["analysis"])

        duration = await self.complete_work(f"Analysis complete for {query}", start)
        result["duration_ms"] = duration

        return result

    # Crypto-specific sentiment lexicon (VADER doesn't know these)
    CRYPTO_LEXICON = {
        # Bullish terms
        "bullish": 2.5, "moon": 2.0, "mooning": 2.5, "pump": 1.5, "pumping": 2.0,
        "ath": 2.0, "breakout": 1.8, "accumulate": 1.5, "accumulating": 1.5,
        "hodl": 1.5, "hodling": 1.5, "diamond hands": 2.0, "wagmi": 2.0,
        "buy the dip": 1.5, "btd": 1.5, "undervalued": 2.0, "gem": 1.5,
        "alpha": 1.5, "100x": 2.5, "10x": 2.0, "sending": 1.5, "lfg": 2.0,
        "ngmi": -1.5, "bearish": -2.0, "rekt": -2.5, "dump": -2.0, "dumping": -2.5,
        # Bearish terms
        "rug": -3.0, "rugged": -3.0, "rugpull": -3.0, "scam": -3.0,
        "ponzi": -3.0, "crash": -2.5, "crashing": -2.5, "dead": -2.0,
        "sell": -1.0, "selling": -1.5, "paper hands": -1.5, "short": -1.0,
        "overvalued": -2.0, "exit scam": -3.0, "down bad": -2.0,
        # Neutral but important
        "whale": 0.5, "dyor": 0.0, "nfa": 0.0, "airdrop": 1.0,
        "staking": 1.0, "defi": 0.5, "nft": 0.3,
    }

    def _apply_crypto_lexicon(self, text: str) -> float:
        """Apply crypto-specific sentiment adjustments"""
        text_lower = text.lower()
        adjustment = 0.0
        for term, score in self.CRYPTO_LEXICON.items():
            if term in text_lower:
                adjustment += score * 0.1  # Scale down to VADER range
        return max(-1.0, min(1.0, adjustment))

    def analyze_sentiment(self, twitter_data: dict) -> dict:
        """
        Analyze sentiment using VADER + crypto-specific lexicon.
        VADER handles general social media text.
        Crypto lexicon handles domain-specific terms (moon, rug, hodl, etc.)
        """
        tweets = twitter_data.get("tweets", [])
        if not tweets:
            return {
                "verdict": "No Data",
                "bullish_pct": 0,
                "bearish_pct": 0,
                "neutral_pct": 0,
                "average_score": 0,
                "total_analyzed": 0,
                "confidence": "low",
            }

        scores = []
        positive_count = 0
        negative_count = 0
        neutral_count = 0

        for tweet in tweets:
            text = tweet.get("text", "")
            if not text:
                continue

            vader_score = self.sentiment_analyzer.polarity_scores(text)
            compound = vader_score["compound"]

            # Apply crypto-specific lexicon adjustment
            crypto_adj = self._apply_crypto_lexicon(text)
            compound = max(-1.0, min(1.0, compound + crypto_adj))

            scores.append(compound)

            if compound > 0.05:
                positive_count += 1
            elif compound < -0.05:
                negative_count += 1
            else:
                neutral_count += 1

        total = len(scores)
        if total == 0:
            return {"verdict": "No Data", "total_analyzed": 0, "confidence": "low"}

        avg_score = sum(scores) / total
        bullish_pct = round(positive_count / total * 100, 1)
        bearish_pct = round(negative_count / total * 100, 1)
        neutral_pct = round(neutral_count / total * 100, 1)

        # Determine verdict
        if avg_score > 0.2:
            verdict = "Very Bullish"
        elif avg_score > 0.05:
            verdict = "Bullish"
        elif avg_score < -0.2:
            verdict = "Very Bearish"
        elif avg_score < -0.05:
            verdict = "Bearish"
        else:
            verdict = "Neutral"

        # Confidence based on sample size
        confidence = "high" if total >= 20 else "medium" if total >= 10 else "low"

        return {
            "verdict": verdict,
            "average_score": round(avg_score, 4),
            "bullish_pct": bullish_pct,
            "bearish_pct": bearish_pct,
            "neutral_pct": neutral_pct,
            "total_analyzed": total,
            "confidence": confidence,
            "score_distribution": {
                "very_positive": len([s for s in scores if s > 0.5]),
                "positive": len([s for s in scores if 0.05 < s <= 0.5]),
                "neutral": len([s for s in scores if -0.05 <= s <= 0.05]),
                "negative": len([s for s in scores if -0.5 <= s < -0.05]),
                "very_negative": len([s for s in scores if s < -0.5]),
            },
        }

    def analyze_price_trend(self, current_price: dict, historical: list) -> dict:
        """
        Advanced technical analysis using pandas/numpy.
        Indicators: SMA, EMA, RSI, MACD, Bollinger Bands, volatility.
        """
        result = {
            "current_price": current_price.get("price_usd", 0),
            "change_24h_pct": current_price.get("change_24h_pct", 0),
            "volume_24h": current_price.get("volume_24h", 0),
            "market_cap": current_price.get("market_cap", 0),
        }

        if historical and len(historical) > 7:
            prices = [p["price"] for p in historical]
            df = pd.DataFrame({"price": prices})

            # === Moving Averages ===
            df["sma_7"] = df["price"].rolling(7).mean()
            df["ema_12"] = df["price"].ewm(span=12, adjust=False).mean()
            df["ema_26"] = df["price"].ewm(span=26, adjust=False).mean()
            if len(prices) >= 30:
                df["sma_30"] = df["price"].rolling(30).mean()

            # === RSI (Relative Strength Index) ===
            delta = df["price"].diff()
            gain = delta.where(delta > 0, 0)
            loss = (-delta).where(delta < 0, 0)
            avg_gain = gain.rolling(14).mean()
            avg_loss = loss.rolling(14).mean()
            rs = avg_gain / avg_loss.replace(0, float('nan'))
            df["rsi"] = 100 - (100 / (1 + rs))

            # === MACD ===
            df["macd_line"] = df["ema_12"] - df["ema_26"]
            df["macd_signal"] = df["macd_line"].ewm(span=9, adjust=False).mean()
            df["macd_histogram"] = df["macd_line"] - df["macd_signal"]

            # === Bollinger Bands ===
            df["bb_middle"] = df["price"].rolling(20).mean()
            bb_std = df["price"].rolling(20).std()
            df["bb_upper"] = df["bb_middle"] + (bb_std * 2)
            df["bb_lower"] = df["bb_middle"] - (bb_std * 2)

            # === Trend detection ===
            sma_7_current = df["sma_7"].iloc[-1]
            sma_7_prev = df["sma_7"].iloc[-2] if len(df) > 1 else sma_7_current

            if len(prices) >= 30:
                sma_30_current = df["sma_30"].iloc[-1]
                trend = "Uptrend" if sma_7_current > sma_30_current else "Downtrend"
            else:
                trend = "Uptrend" if sma_7_current > sma_7_prev else "Downtrend"

            # === Volatility ===
            returns = df["price"].pct_change().dropna()
            volatility = returns.std() * 100

            # Price range
            high_30d = max(prices)
            low_30d = min(prices)
            range_pct = ((high_30d - low_30d) / low_30d * 100) if low_30d > 0 else 0

            # Get latest indicator values safely
            def safe_val(series, decimals=6):
                val = series.iloc[-1] if len(series) > 0 else None
                if val is not None and not pd.isna(val):
                    return round(float(val), decimals)
                return None

            # === RSI Interpretation ===
            rsi_val = safe_val(df["rsi"], 1)
            if rsi_val is not None:
                if rsi_val > 70:
                    rsi_signal = "Overbought"
                elif rsi_val < 30:
                    rsi_signal = "Oversold"
                else:
                    rsi_signal = "Neutral"
            else:
                rsi_signal = "N/A"

            # === MACD Interpretation ===
            macd_hist = safe_val(df["macd_histogram"], 8)
            macd_signal_val = "Bullish" if macd_hist and macd_hist > 0 else "Bearish" if macd_hist and macd_hist < 0 else "Neutral"

            # === Bollinger Band Position ===
            current = prices[-1]
            bb_upper_val = safe_val(df["bb_upper"])
            bb_lower_val = safe_val(df["bb_lower"])
            if bb_upper_val and bb_lower_val:
                bb_width = bb_upper_val - bb_lower_val
                bb_position = "Upper Band" if current > bb_upper_val else "Lower Band" if current < bb_lower_val else "Middle"
            else:
                bb_position = "N/A"

            result.update({
                "trend": trend,
                "sma_7": safe_val(df["sma_7"]),
                "sma_30": safe_val(df["sma_30"]) if "sma_30" in df.columns else None,
                "ema_12": safe_val(df["ema_12"]),
                "ema_26": safe_val(df["ema_26"]),
                "rsi": rsi_val,
                "rsi_signal": rsi_signal,
                "macd_line": safe_val(df["macd_line"], 8),
                "macd_signal": safe_val(df["macd_signal"], 8),
                "macd_histogram": macd_hist,
                "macd_interpretation": macd_signal_val,
                "bollinger_upper": bb_upper_val,
                "bollinger_lower": bb_lower_val,
                "bollinger_middle": safe_val(df["bb_middle"]),
                "bollinger_position": bb_position,
                "volatility_pct": round(volatility, 2),
                "high_30d": round(high_30d, 6),
                "low_30d": round(low_30d, 6),
                "range_30d_pct": round(range_pct, 2),
            })
        else:
            change = current_price.get("change_24h_pct", 0)
            result["trend"] = "Uptrend" if change > 0 else "Downtrend" if change < 0 else "Sideways"

        # Trend strength (multi-factor)
        change = abs(result.get("change_24h_pct", 0))
        rsi = result.get("rsi")
        if change > 10 or (rsi and (rsi > 80 or rsi < 20)):
            result["trend_strength"] = "Strong"
        elif change > 5 or (rsi and (rsi > 65 or rsi < 35)):
            result["trend_strength"] = "Moderate"
        else:
            result["trend_strength"] = "Weak"

        return result

    def analyze_whale_activity(self, whale_data: dict) -> dict:
        """Interpret whale transaction data"""
        return {
            "net_flow": whale_data.get("net_flow", "neutral"),
            "large_buys": whale_data.get("large_buys", 0),
            "large_sells": whale_data.get("large_sells", 0),
            "interpretation": whale_data.get("analysis", "No whale data available"),
            "signal": (
                "Bullish" if whale_data.get("net_flow") == "accumulation"
                else "Bearish" if whale_data.get("net_flow") == "distribution"
                else "Neutral"
            ),
        }

    async def analyze_news(self, news_data: dict, query: str) -> dict:
        """Summarize news using free LLM"""
        articles = news_data.get("articles", [])
        if not articles:
            return {"summary": "No recent news found.", "sentiment": "neutral", "key_topics": []}

        # Prepare headlines for LLM summarization
        headlines = "\n".join([f"- {a['title']}" for a in articles[:10]])

        summary = await llm_router.generate(
            prompt=f"Here are recent news headlines about {query}:\n{headlines}\n\nProvide a 2-3 sentence summary of the overall news sentiment and key themes. Be concise.",
            system_prompt="You are a financial news analyst. Summarize news concisely. Output only the summary, nothing else.",
            max_tokens=200,
        )

        # Analyze headline sentiment with VADER
        headline_scores = []
        for article in articles:
            score = self.sentiment_analyzer.polarity_scores(article.get("title", ""))
            headline_scores.append(score["compound"])

        avg_news_sentiment = sum(headline_scores) / len(headline_scores) if headline_scores else 0

        return {
            "summary": summary,
            "sentiment": "positive" if avg_news_sentiment > 0.1 else "negative" if avg_news_sentiment < -0.1 else "neutral",
            "sentiment_score": round(avg_news_sentiment, 4),
            "articles_analyzed": len(articles),
            "key_topics": [a["title"][:60] for a in articles[:5]],
        }

    def generate_overall_assessment(self, analyses: dict) -> dict:
        """
        Combine all analysis signals into a final verdict.
        Uses a weighted scoring model.
        """
        score = 50  # Start neutral

        # Sentiment weight: 35%
        sentiment = analyses.get("sentiment", {})
        if sentiment.get("verdict") == "Very Bullish":
            score += 17
        elif sentiment.get("verdict") == "Bullish":
            score += 10
        elif sentiment.get("verdict") == "Very Bearish":
            score -= 17
        elif sentiment.get("verdict") == "Bearish":
            score -= 10

        # Price trend weight: 30%
        price = analyses.get("price_trend", {})
        if price.get("trend") == "Uptrend":
            score += 10
            if price.get("trend_strength") == "Strong":
                score += 5
        elif price.get("trend") == "Downtrend":
            score -= 10
            if price.get("trend_strength") == "Strong":
                score -= 5

        # Whale activity weight: 20%
        whale = analyses.get("whale", {})
        if whale.get("signal") == "Bullish":
            score += 10
        elif whale.get("signal") == "Bearish":
            score -= 10

        # News sentiment weight: 15%
        news = analyses.get("news", {})
        if news.get("sentiment") == "positive":
            score += 7
        elif news.get("sentiment") == "negative":
            score -= 7

        # Clamp score
        score = max(0, min(100, score))

        # Determine verdict
        if score >= 80:
            verdict = "Strong Buy"
        elif score >= 65:
            verdict = "Buy"
        elif score >= 45:
            verdict = "Neutral"
        elif score >= 30:
            verdict = "Sell"
        else:
            verdict = "Strong Sell"

        # Confidence based on data quality
        data_sources = sum(1 for v in analyses.values() if v)
        confidence = "high" if data_sources >= 4 else "medium" if data_sources >= 2 else "low"

        return {
            "score": score,
            "verdict": verdict,
            "confidence": confidence,
            "signal_breakdown": {
                "sentiment": sentiment.get("verdict", "N/A"),
                "price_trend": price.get("trend", "N/A"),
                "whale_activity": whale.get("signal", "N/A"),
                "news_sentiment": news.get("sentiment", "N/A"),
            },
        }

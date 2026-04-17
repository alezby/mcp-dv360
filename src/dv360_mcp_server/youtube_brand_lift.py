"""YouTube Brand Lift Auditor - Pre-flight estimation of brand lift metrics."""

import re
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Industry benchmark data based on YouTube/Google published research and industry studies.
# Tuples are (low_pct, mid_pct, high_pct) lift estimates.
INDUSTRY_BENCHMARKS: Dict[str, Dict[str, Tuple[float, float, float]]] = {
    "CPG": {
        "awareness_lift": (2.0, 3.5, 5.0),
        "ad_recall_lift": (5.0, 10.0, 15.0),
        "consideration_lift": (1.0, 2.0, 3.0),
        "purchase_intent_lift": (1.0, 2.0, 3.0),
    },
    "AUTO": {
        "awareness_lift": (3.0, 5.0, 7.0),
        "ad_recall_lift": (8.0, 13.0, 18.0),
        "consideration_lift": (2.0, 3.5, 5.0),
        "purchase_intent_lift": (1.0, 2.5, 4.0),
    },
    "TECH": {
        "awareness_lift": (2.0, 4.0, 6.0),
        "ad_recall_lift": (6.0, 10.0, 14.0),
        "consideration_lift": (1.0, 2.5, 4.0),
        "purchase_intent_lift": (1.0, 2.0, 3.0),
    },
    "RETAIL": {
        "awareness_lift": (2.0, 3.5, 5.0),
        "ad_recall_lift": (5.0, 8.5, 12.0),
        "consideration_lift": (1.0, 2.0, 3.0),
        "purchase_intent_lift": (1.0, 2.5, 4.0),
    },
    "FINANCE": {
        "awareness_lift": (1.0, 2.5, 4.0),
        "ad_recall_lift": (4.0, 7.0, 10.0),
        "consideration_lift": (1.0, 2.0, 3.0),
        "purchase_intent_lift": (0.5, 1.25, 2.0),
    },
    "ENTERTAINMENT": {
        "awareness_lift": (4.0, 6.0, 8.0),
        "ad_recall_lift": (8.0, 14.0, 20.0),
        "consideration_lift": (2.0, 4.0, 6.0),
        "purchase_intent_lift": (2.0, 3.5, 5.0),
    },
    "HEALTHCARE": {
        "awareness_lift": (1.0, 2.0, 3.0),
        "ad_recall_lift": (4.0, 6.5, 9.0),
        "consideration_lift": (1.0, 2.0, 3.0),
        "purchase_intent_lift": (0.5, 1.25, 2.0),
    },
    "TRAVEL": {
        "awareness_lift": (2.0, 4.0, 6.0),
        "ad_recall_lift": (6.0, 11.0, 16.0),
        "consideration_lift": (2.0, 3.5, 5.0),
        "purchase_intent_lift": (1.5, 2.5, 4.0),
    },
    "DEFAULT": {
        "awareness_lift": (2.0, 3.5, 5.0),
        "ad_recall_lift": (5.0, 8.5, 12.0),
        "consideration_lift": (1.0, 2.5, 4.0),
        "purchase_intent_lift": (1.0, 2.0, 3.0),
    },
}

# Each entry: (min_sec, max_sec, score, label, note)
DURATION_SCORING: List[Tuple] = [
    (0, 6, 80, "BUMPER", "High recall potential, limited storytelling capacity"),
    (7, 15, 92, "SHORT", "Optimal recall and awareness balance"),
    (16, 30, 95, "STANDARD", "Best overall brand lift potential"),
    (31, 60, 78, "LONG", "Good for consideration; expect lower completion rates"),
    (61, float("inf"), 60, "EXTENDED", "High engagement risk; use only for targeted premium audiences"),
]

FORMAT_SCORING: Dict[str, Dict[str, Any]] = {
    "SKIPPABLE_IN_STREAM": {
        "score": 82,
        "strength": "Wide reach, cost-efficient, viewer intent signal via skip behavior",
        "consideration_multiplier": 1.1,
        "recall_multiplier": 0.95,
    },
    "NON_SKIPPABLE_IN_STREAM": {
        "score": 90,
        "strength": "Guaranteed 100% completion, strong brand message delivery",
        "consideration_multiplier": 1.2,
        "recall_multiplier": 1.25,
    },
    "BUMPER": {
        "score": 85,
        "strength": "High-frequency reach, strong ad recall at scale",
        "consideration_multiplier": 0.8,
        "recall_multiplier": 1.35,
    },
    "IN_FEED": {
        "score": 75,
        "strength": "High-intent audience in discovery context",
        "consideration_multiplier": 1.15,
        "recall_multiplier": 0.85,
    },
    "OUTSTREAM": {
        "score": 65,
        "strength": "Broad reach outside YouTube ecosystem",
        "consideration_multiplier": 0.9,
        "recall_multiplier": 0.80,
    },
    "UNKNOWN": {
        "score": 70,
        "strength": "Format not specified; scoring based on defaults",
        "consideration_multiplier": 1.0,
        "recall_multiplier": 1.0,
    },
}

TARGETING_VALUE: Dict[str, Dict[str, Any]] = {
    "AFFINITY_AUDIENCE": {"points": 12, "label": "Affinity Audiences"},
    "CUSTOM_AFFINITY": {"points": 15, "label": "Custom Affinity"},
    "IN_MARKET_AUDIENCE": {"points": 18, "label": "In-Market Audiences"},
    "CUSTOM_INTENT": {"points": 20, "label": "Custom Intent Audiences"},
    "LIFE_EVENT": {"points": 14, "label": "Life Events"},
    "DEMOGRAPHIC": {"points": 8, "label": "Demographic Targeting"},
    "GEOGRAPHIC": {"points": 6, "label": "Geographic Targeting"},
    "KEYWORD": {"points": 16, "label": "Content Keywords"},
    "PLACEMENT": {"points": 14, "label": "Placement Targeting"},
    "REMARKETING": {"points": 10, "label": "Remarketing / Retargeting"},
    "FIRST_PARTY": {"points": 18, "label": "First-Party Audiences"},
}


class YouTubeBrandLiftAuditor:
    """Pre-flight brand lift estimator for YouTube video campaigns in DV360."""

    def __init__(self, dv360_client=None):
        self.client = dv360_client

    async def audit(
        self,
        advertiser_id: str,
        creative_id: Optional[str] = None,
        line_item_id: Optional[str] = None,
        campaign_id: Optional[str] = None,
        industry_vertical: str = "DEFAULT",
        campaign_objective: str = "AWARENESS",
        video_duration_seconds: Optional[int] = None,
        video_format: Optional[str] = None,
        target_frequency: Optional[float] = None,
        budget_usd: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Run a pre-flight brand lift audit and return a structured report."""

        creative_data: Dict = {}
        line_item_data: Dict = {}
        targeting_data: Dict = {}
        historical_perf: Dict = {}

        if self.client and creative_id:
            try:
                creative_data = await self.client.get_creative_details(advertiser_id, creative_id)
            except Exception as e:
                logger.warning("Could not fetch creative %s: %s", creative_id, e)

        if self.client and line_item_id:
            try:
                line_item_data = await self.client.get_line_item_details(advertiser_id, line_item_id)
                targeting_data = await self.client.get_targeting_options(advertiser_id, line_item_id)
            except Exception as e:
                logger.warning("Could not fetch line item %s: %s", line_item_id, e)

        if self.client and campaign_id:
            try:
                historical_perf = await self.client.get_real_campaign_performance(
                    advertiser_id, campaign_id, "LAST_30_DAYS"
                )
            except Exception as e:
                logger.warning("Could not fetch campaign performance for %s: %s", campaign_id, e)

        duration_s, format_key = self._extract_creative_attributes(
            creative_data, video_duration_seconds, video_format
        )

        creative_score, creative_details = self._score_creative(duration_s, format_key, campaign_objective)
        targeting_score, targeting_details = self._score_targeting(targeting_data, line_item_data)

        overall_score = round(creative_score * 0.40 + targeting_score * 0.60)

        vertical = industry_vertical.upper()
        benchmarks = INDUSTRY_BENCHMARKS.get(vertical, INDUSTRY_BENCHMARKS["DEFAULT"])

        predicted_lift = self._predict_brand_lift(
            benchmarks, creative_score, targeting_score, format_key, campaign_objective, target_frequency
        )

        risk_flags = self._generate_risk_flags(
            duration_s, format_key, campaign_objective, creative_score, targeting_score, target_frequency
        )

        recommendations = self._generate_recommendations(
            duration_s, format_key, campaign_objective, creative_score, targeting_score,
            targeting_data, target_frequency
        )

        return {
            "audit_summary": {
                "overall_score": overall_score,
                "lift_potential": self._classify_lift_potential(overall_score),
                "recommendation": self._classify_readiness(overall_score, risk_flags),
                "industry_vertical": vertical,
                "campaign_objective": campaign_objective.upper(),
            },
            "creative_assessment": {
                "score": creative_score,
                **creative_details,
            },
            "targeting_assessment": {
                "score": targeting_score,
                **targeting_details,
            },
            "predicted_brand_lift": predicted_lift,
            "industry_benchmarks": {
                "vertical": vertical,
                "awareness_lift_range": f"{benchmarks['awareness_lift'][0]:.1f}%-{benchmarks['awareness_lift'][2]:.1f}%",
                "ad_recall_lift_range": f"{benchmarks['ad_recall_lift'][0]:.1f}%-{benchmarks['ad_recall_lift'][2]:.1f}%",
                "consideration_lift_range": f"{benchmarks['consideration_lift'][0]:.1f}%-{benchmarks['consideration_lift'][2]:.1f}%",
                "purchase_intent_lift_range": f"{benchmarks['purchase_intent_lift'][0]:.1f}%-{benchmarks['purchase_intent_lift'][2]:.1f}%",
            },
            "historical_context": self._build_historical_context(historical_perf),
            "risk_flags": risk_flags,
            "recommendations": recommendations,
        }

    # ─── Private helpers ─────────────────────────────────────────────────────

    def _extract_creative_attributes(
        self,
        creative_data: Dict,
        manual_duration: Optional[int],
        manual_format: Optional[str],
    ) -> Tuple[Optional[int], str]:
        duration_s = manual_duration
        if creative_data and not manual_duration:
            raw = creative_data.get("videoDuration", "")
            if raw:
                duration_s = self._parse_duration(raw)

        format_key = "UNKNOWN"
        if manual_format:
            format_key = self._normalize_format(manual_format)
        elif creative_data:
            format_key = self._normalize_format(creative_data.get("creativeType", ""))

        return duration_s, format_key

    def _parse_duration(self, raw: Any) -> Optional[int]:
        if isinstance(raw, (int, float)):
            return int(raw)
        if isinstance(raw, str):
            m = re.match(r"PT(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?", raw)
            if m:
                return int(int(m.group(1) or 0) * 60 + float(m.group(2) or 0))
            try:
                return int(float(raw))
            except ValueError:
                pass
        return None

    def _normalize_format(self, raw: str) -> str:
        u = raw.upper()
        if "BUMPER" in u:
            return "BUMPER"
        if "NON_SKIPPABLE" in u:
            return "NON_SKIPPABLE_IN_STREAM"
        if "SKIPPABLE" in u or "TRUEVIEW" in u:
            return "SKIPPABLE_IN_STREAM"
        if "IN_FEED" in u or "DISCOVERY" in u:
            return "IN_FEED"
        if "OUTSTREAM" in u:
            return "OUTSTREAM"
        return "UNKNOWN"

    def _score_creative(
        self, duration_s: Optional[int], format_key: str, objective: str
    ) -> Tuple[int, Dict]:
        scores: List[int] = []
        strengths: List[str] = []
        improvements: List[str] = []
        duration_label = "UNKNOWN"
        duration_note = ""

        if duration_s is not None:
            for min_s, max_s, d_score, label, note in DURATION_SCORING:
                if min_s <= duration_s <= max_s:
                    scores.append(d_score)
                    duration_label = label
                    duration_note = note
                    if d_score >= 90:
                        strengths.append(f"Duration ({duration_s}s) is in the optimal range for brand lift")
                    elif d_score >= 78:
                        strengths.append(f"Duration ({duration_s}s) is acceptable")
                    else:
                        improvements.append("Consider cutting the video to 15-30s for better brand lift")
                    break

        fmt_info = FORMAT_SCORING.get(format_key, FORMAT_SCORING["UNKNOWN"])
        scores.append(fmt_info["score"])
        strengths.append(fmt_info["strength"])

        obj = objective.upper()
        alignment_score = 0
        if obj == "AWARENESS":
            if format_key in ("SKIPPABLE_IN_STREAM", "BUMPER", "NON_SKIPPABLE_IN_STREAM"):
                alignment_score = 5
                strengths.append("Format aligns well with awareness objective")
        elif obj == "CONSIDERATION":
            if format_key in ("SKIPPABLE_IN_STREAM", "IN_FEED"):
                alignment_score = 5
                strengths.append("Format supports consideration via viewer intent signals")
            elif format_key == "BUMPER":
                alignment_score = -5
                improvements.append("Bumper ads are less effective for consideration; consider TrueView in-stream")
        elif obj == "ACTION":
            if format_key in ("SKIPPABLE_IN_STREAM", "IN_FEED"):
                alignment_score = 3
            elif format_key == "BUMPER":
                alignment_score = -10
                improvements.append("Bumper ads are not recommended for direct action objectives")

        base = round(sum(scores) / max(len(scores), 1)) + alignment_score
        final = max(0, min(100, base))

        alignment_label = "GOOD" if alignment_score >= 3 else ("FAIR" if alignment_score >= 0 else "POOR")

        return final, {
            "format": format_key,
            "duration_seconds": duration_s,
            "duration_category": duration_label,
            "duration_note": duration_note,
            "objective_format_alignment": alignment_label,
            "strengths": strengths,
            "improvements": improvements,
        }

    def _score_targeting(self, targeting_data: Dict, line_item_data: Dict) -> Tuple[int, Dict]:
        detected: List[str] = []
        total_points = 0
        strengths: List[str] = []
        improvements: List[str] = []

        if line_item_data.get("targetingExpansion", {}).get("enableOptimization"):
            total_points += 10
            strengths.append("Google audience expansion enabled")

        for t_opt in line_item_data.get("assignedTargetingOptions", []):
            t_type = t_opt.get("targetingType", "").upper()
            key = self._map_targeting_type(t_type)
            if key and key not in detected:
                detected.append(key)
                total_points += TARGETING_VALUE[key]["points"]

        if isinstance(targeting_data, dict) and targeting_data.get("audienceTargeting"):
            if "IN_MARKET_AUDIENCE" not in detected:
                detected.append("IN_MARKET_AUDIENCE")
                total_points += TARGETING_VALUE["IN_MARKET_AUDIENCE"]["points"]

        if not detected or (detected == ["GEOGRAPHIC"]):
            improvements.append("No audience-based targeting detected; add affinity or in-market audiences")
            improvements.append("Consider adding demographic targeting at minimum")

        raw_score = 45 + min(total_points, 55)
        final_score = max(20, min(100, raw_score))

        if "IN_MARKET_AUDIENCE" in detected or "CUSTOM_INTENT" in detected:
            strengths.append("Intent-based audiences signal high purchase readiness")
        if "AFFINITY_AUDIENCE" in detected or "CUSTOM_AFFINITY" in detected:
            strengths.append("Affinity audiences improve brand relevance")
        if len(detected) >= 3:
            strengths.append("Multi-layer targeting improves precision and lift efficiency")
        if len(detected) < 2:
            improvements.append("Add complementary audience layers for better targeting coverage")
        if "KEYWORD" not in detected:
            improvements.append("Content keyword targeting can improve contextual brand relevance")

        reach = "BROAD" if final_score < 60 else ("TARGETED" if final_score < 80 else "PRECISION")

        return final_score, {
            "detected_targeting_types": detected,
            "reach_estimate": reach,
            "strengths": strengths,
            "improvements": improvements,
        }

    def _map_targeting_type(self, t_type: str) -> Optional[str]:
        if "CUSTOM_AFFINITY" in t_type:
            return "CUSTOM_AFFINITY"
        if "AFFINITY" in t_type:
            return "AFFINITY_AUDIENCE"
        if "IN_MARKET" in t_type or "AUDIENCE_GROUP" in t_type:
            return "IN_MARKET_AUDIENCE"
        if "CUSTOM_INTENT" in t_type:
            return "CUSTOM_INTENT"
        if "LIFE_EVENT" in t_type:
            return "LIFE_EVENT"
        if "KEYWORD" in t_type:
            return "KEYWORD"
        if "PLACEMENT" in t_type:
            return "PLACEMENT"
        if "REMARKETING" in t_type or "USER_LIST" in t_type:
            return "REMARKETING"
        if "DEMOGRAPHIC" in t_type or "AGE_RANGE" in t_type or "GENDER" in t_type:
            return "DEMOGRAPHIC"
        if "GEO" in t_type or "GEOGRAPHIC" in t_type:
            return "GEOGRAPHIC"
        return None

    def _predict_brand_lift(
        self,
        benchmarks: Dict,
        creative_score: int,
        targeting_score: int,
        format_key: str,
        objective: str,
        frequency: Optional[float],
    ) -> Dict:
        # Creative multiplier: 0.65–1.35 based on creative score (0–100)
        c_mult = 0.65 + (creative_score / 100) * 0.70
        # Targeting multiplier: 0.75–1.25
        t_mult = 0.75 + (targeting_score / 100) * 0.50
        combined = (c_mult + t_mult) / 2

        freq_mult = 1.0
        if frequency:
            if 3 <= frequency <= 5:
                freq_mult = 1.10
            elif frequency < 2:
                freq_mult = 0.85
            elif frequency > 7:
                freq_mult = 0.90

        fmt = FORMAT_SCORING.get(format_key, FORMAT_SCORING["UNKNOWN"])
        recall_m = fmt["recall_multiplier"]
        consider_m = fmt["consideration_multiplier"]

        def _adjust(base: Tuple[float, float, float], m: float, fmt_m: float = 1.0) -> Dict:
            lo, mid, hi = base
            return {
                "low": round(lo * m * fmt_m * freq_mult, 1),
                "mid": round(mid * m * fmt_m * freq_mult, 1),
                "high": round(hi * m * fmt_m * freq_mult, 1),
            }

        confidence = "LOW"
        if creative_score > 50 and targeting_score > 50:
            confidence = "MEDIUM"
        if creative_score > 70 and targeting_score > 70:
            confidence = "HIGH"

        return {
            "brand_awareness_lift_pct": _adjust(benchmarks["awareness_lift"], combined),
            "ad_recall_lift_pct": _adjust(benchmarks["ad_recall_lift"], combined, recall_m),
            "brand_consideration_lift_pct": _adjust(benchmarks["consideration_lift"], combined, consider_m),
            "purchase_intent_lift_pct": _adjust(benchmarks["purchase_intent_lift"], combined),
            "confidence": confidence,
            "methodology": (
                "Benchmark adjustment model using creative quality score, targeting effectiveness, "
                "format-specific multipliers, and frequency modifiers applied to industry lift benchmarks."
            ),
        }

    def _generate_risk_flags(
        self,
        duration_s: Optional[int],
        format_key: str,
        objective: str,
        creative_score: int,
        targeting_score: int,
        frequency: Optional[float],
    ) -> List[Dict]:
        flags: List[Dict] = []
        obj = objective.upper()

        if creative_score < 60:
            flags.append({
                "severity": "HIGH",
                "category": "CREATIVE",
                "message": (
                    f"Creative score ({creative_score}/100) is below threshold. "
                    "Significant brand lift improvement possible with creative optimization."
                ),
            })

        if targeting_score < 50:
            flags.append({
                "severity": "HIGH",
                "category": "TARGETING",
                "message": (
                    "Insufficient audience targeting detected. "
                    "Brand lift will be diluted by reaching irrelevant audiences."
                ),
            })

        if duration_s is not None:
            if duration_s > 30 and obj == "AWARENESS":
                flags.append({
                    "severity": "WARNING",
                    "category": "CREATIVE",
                    "message": (
                        f"Video duration ({duration_s}s) exceeds optimal 15-30s range for awareness campaigns. "
                        "Expect lower completion rates."
                    ),
                })
            if duration_s > 60:
                flags.append({
                    "severity": "WARNING",
                    "category": "CREATIVE",
                    "message": (
                        f"Extended duration ({duration_s}s) may result in high skip or abandon rates "
                        "unless targeting premium engaged audiences."
                    ),
                })

        if format_key == "BUMPER" and obj in ("CONSIDERATION", "ACTION"):
            flags.append({
                "severity": "WARNING",
                "category": "FORMAT_OBJECTIVE_MISMATCH",
                "message": (
                    "Bumper ad format (≤6s) is sub-optimal for consideration or action objectives; "
                    "insufficient time for meaningful message delivery."
                ),
            })

        if format_key == "NON_SKIPPABLE_IN_STREAM" and duration_s and duration_s > 30:
            flags.append({
                "severity": "WARNING",
                "category": "CREATIVE",
                "message": (
                    f"Non-skippable ads over 30s ({duration_s}s) risk negative user experience. "
                    "Consider a 15-20s cut."
                ),
            })

        if frequency and frequency > 8:
            flags.append({
                "severity": "WARNING",
                "category": "FREQUENCY",
                "message": (
                    f"Target frequency ({frequency:.1f}/week) exceeds recommended threshold of 7. "
                    "Risk of ad fatigue and negative brand sentiment."
                ),
            })

        return flags

    def _generate_recommendations(
        self,
        duration_s: Optional[int],
        format_key: str,
        objective: str,
        creative_score: int,
        targeting_score: int,
        targeting_data: Dict,
        frequency: Optional[float],
    ) -> List[str]:
        recs: List[str] = []
        obj = objective.upper()

        if duration_s:
            if duration_s > 30 and obj != "CONSIDERATION":
                recs.append(
                    f"Create a 15s or 30s cut of the {duration_s}s video for higher recall and awareness lift"
                )
            if duration_s <= 6 and obj == "CONSIDERATION":
                recs.append(
                    "Complement bumpers with a TrueView (15-30s skippable) version for meaningful consideration lift"
                )

        if obj == "CONSIDERATION" and format_key == "BUMPER":
            recs.append("Switch to TrueView in-stream (skippable) or in-feed video for consideration campaigns")
        elif obj == "ACTION" and format_key == "BUMPER":
            recs.append("Bumper ads drive recall, not action; use TrueView in-stream or in-feed for conversion objectives")

        if targeting_score < 70:
            recs.append("Add affinity or in-market audiences to improve targeting precision and lift efficiency")
        if targeting_score < 85:
            recs.append("Layer custom intent audiences (based on search behavior) to reach high-value users")

        if format_key == "BUMPER":
            recs.append("Run bumper ads in sequence with TrueView campaigns to amplify brand recall (AB sequencing)")

        if not frequency:
            recs.append("Set frequency capping at 3-5 impressions per week to maximize lift while avoiding ad fatigue")
        elif frequency < 2:
            recs.append("Increase frequency to 3-5 per week to build brand memory and improve awareness")
        elif frequency > 7:
            recs.append("Reduce frequency cap to 5-7 per week to prevent ad fatigue and preserve brand sentiment")

        recs.append(
            "Enable Brand Lift measurement in Google Ads / DV360 to validate actual lift post-flight"
        )

        return recs[:6]

    def _classify_lift_potential(self, score: int) -> str:
        if score >= 80:
            return "HIGH"
        if score >= 65:
            return "MEDIUM_HIGH"
        if score >= 50:
            return "MEDIUM"
        if score >= 35:
            return "LOW_MEDIUM"
        return "LOW"

    def _classify_readiness(self, score: int, flags: List[Dict]) -> str:
        high_flags = sum(1 for f in flags if f["severity"] == "HIGH")
        if high_flags > 0:
            return "NOT_READY_ACTION_REQUIRED"
        if score >= 70:
            return "READY_TO_FLIGHT"
        if score >= 55:
            return "PROCEED_WITH_CAUTION"
        return "OPTIMIZATION_RECOMMENDED"

    def _build_historical_context(self, perf_data: Dict) -> Dict:
        if not perf_data or "error" in perf_data:
            return {
                "data_available": False,
                "note": "No historical performance data available for this campaign",
            }

        metrics = perf_data.get("metrics", {})
        impressions = metrics.get("impressions") or perf_data.get("impressions")
        ctr = metrics.get("ctr") or perf_data.get("ctr")

        context: Dict[str, Any] = {
            "data_available": bool(impressions or ctr),
            "impressions": impressions,
            "ctr": ctr,
        }

        if ctr:
            try:
                v = float(ctr)
                context["ctr_benchmark"] = (
                    "ABOVE_AVERAGE" if v > 0.003 else ("AVERAGE" if v > 0.001 else "BELOW_AVERAGE")
                )
            except (ValueError, TypeError):
                pass

        return context

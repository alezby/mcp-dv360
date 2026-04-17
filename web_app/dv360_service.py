"""Thin DV360 + Bid Manager service that runs on user OAuth credentials."""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

_VIDEO_CREATIVE_TYPES = {
    "CREATIVE_TYPE_SKIPPABLE_IN_STREAM",
    "CREATIVE_TYPE_NON_SKIPPABLE_IN_STREAM",
    "CREATIVE_TYPE_BUMPER",
    "CREATIVE_TYPE_IN_STREAM",
    "CREATIVE_TYPE_VIDEO",
    "VIDEO",
}


class DV360Service:
    """
    Lightweight DV360 v4 + Bid Manager v2 API wrapper.
    Implements the interface expected by YouTubeBrandLiftAuditor.
    """

    def __init__(self, credentials: Credentials):
        self.credentials = credentials
        self._dv360 = None
        self._bm = None
        self._executor = ThreadPoolExecutor(max_workers=4)

    # ─── Service builders ────────────────────────────────────────────────────

    def _get_dv360(self):
        if not self._dv360:
            self._dv360 = build(
                "displayvideo", "v4",
                credentials=self.credentials,
                cache_discovery=False,
            )
        return self._dv360

    def _get_bm(self):
        if not self._bm:
            self._bm = build(
                "doubleclickbidmanager", "v2",
                credentials=self.credentials,
                cache_discovery=False,
            )
        return self._bm

    async def _run(self, request) -> Any:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, request.execute)

    # ─── Listing endpoints (used by the frontend) ────────────────────────────

    async def list_advertisers(self) -> List[Dict]:
        svc = self._get_dv360()
        all_advertisers: List[Dict] = []

        try:
            resp = await self._run(svc.partners().list())
            partners = resp.get("partners", [])
        except HttpError as e:
            logger.warning("Could not list partners: %s", e)
            partners = []

        if partners:
            for partner in partners:
                pid = partner.get("partnerId")
                try:
                    resp = await self._run(
                        svc.advertisers().list(partnerId=pid)
                    )
                    for adv in resp.get("advertisers", []):
                        adv["_partnerId"] = pid
                        all_advertisers.append(adv)
                except HttpError as e:
                    logger.warning("Could not list advertisers for partner %s: %s", pid, e)
        else:
            # Some accounts work without explicit partner_id
            try:
                resp = await self._run(svc.advertisers().list())
                all_advertisers = resp.get("advertisers", [])
            except HttpError as e:
                logger.warning("Could not list advertisers: %s", e)

        return [
            {
                "id": a.get("advertiserId"),
                "name": a.get("displayName", "Unknown"),
                "status": a.get("entityStatus", "UNKNOWN"),
            }
            for a in all_advertisers
            if a.get("advertiserId")
        ]

    async def list_campaigns(self, advertiser_id: str) -> List[Dict]:
        svc = self._get_dv360()
        resp = await self._run(
            svc.advertisers().campaigns().list(advertiserId=advertiser_id)
        )
        return [
            {
                "id": c.get("campaignId"),
                "name": c.get("displayName", "Unknown"),
                "status": c.get("entityStatus", "UNKNOWN"),
                "goal": c.get("campaignGoal", {}).get("campaignGoalType", ""),
            }
            for c in resp.get("campaigns", [])
            if c.get("campaignId")
        ]

    async def list_video_creatives(self, advertiser_id: str) -> List[Dict]:
        svc = self._get_dv360()
        resp = await self._run(
            svc.advertisers().creatives().list(advertiserId=advertiser_id)
        )
        result = []
        for c in resp.get("creatives", []):
            ct = c.get("creativeType", "").upper()
            if any(vt in ct for vt in _VIDEO_CREATIVE_TYPES):
                result.append({
                    "id": c.get("creativeId"),
                    "name": c.get("displayName", "Unknown"),
                    "type": c.get("creativeType", ""),
                    "duration": c.get("videoDuration", ""),
                })
        return result

    async def list_line_items(
        self, advertiser_id: str, campaign_id: Optional[str] = None
    ) -> List[Dict]:
        svc = self._get_dv360()
        kwargs: Dict[str, Any] = {"advertiserId": advertiser_id}
        if campaign_id:
            kwargs["filter"] = f'campaignId="{campaign_id}"'
        resp = await self._run(svc.advertisers().lineItems().list(**kwargs))
        return [
            {
                "id": li.get("lineItemId"),
                "name": li.get("displayName", "Unknown"),
                "status": li.get("entityStatus", "UNKNOWN"),
                "type": li.get("lineItemType", ""),
            }
            for li in resp.get("lineItems", [])
            if li.get("lineItemId")
        ]

    # ─── Methods required by YouTubeBrandLiftAuditor ─────────────────────────

    async def get_creative_details(self, advertiser_id: str, creative_id: str) -> Dict:
        svc = self._get_dv360()
        return await self._run(
            svc.advertisers().creatives().get(
                advertiserId=advertiser_id, creativeId=creative_id
            )
        )

    async def get_line_item_details(self, advertiser_id: str, line_item_id: str) -> Dict:
        svc = self._get_dv360()
        return await self._run(
            svc.advertisers().lineItems().get(
                advertiserId=advertiser_id, lineItemId=line_item_id
            )
        )

    async def get_targeting_options(self, advertiser_id: str, line_item_id: str) -> Dict:
        li = await self.get_line_item_details(advertiser_id, line_item_id)
        return li.get("targetingExpansion", {})

    async def get_real_campaign_performance(
        self, advertiser_id: str, campaign_id: str, date_range: str
    ) -> Dict:
        svc = self._get_bm()
        query_body = {
            "metadata": {
                "title": f"BL-Audit-{campaign_id}",
                "dataRange": {"range": date_range},
                "format": "CSV",
            },
            "params": {
                "type": "STANDARD",
                "groupBys": ["FILTER_CAMPAIGN"],
                "filters": [
                    {"type": "FILTER_ADVERTISER", "value": advertiser_id},
                    {"type": "FILTER_CAMPAIGN", "value": campaign_id},
                ],
                "metrics": ["METRIC_IMPRESSIONS", "METRIC_CLICKS", "METRIC_CTR"],
            },
            "schedule": {"frequency": "ONE_TIME"},
        }
        try:
            resp = await self._run(svc.queries().create(body=query_body))
            return {"query_id": resp.get("queryId"), "status": "query_created"}
        except HttpError as e:
            return {"error": str(e)}

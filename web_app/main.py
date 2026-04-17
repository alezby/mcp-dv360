"""YouTube Brand Lift Auditor — FastAPI web application."""

import os
import secrets
import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from pydantic import BaseModel

# Allow HTTP for local development (remove in production)
os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

# Add project root so we can import the auditor
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.dv360_mcp_server.youtube_brand_lift import YouTubeBrandLiftAuditor
from web_app.dv360_service import DV360Service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── App setup ───────────────────────────────────────────────────────────────

app = FastAPI(title="YouTube Brand Lift Auditor")

_static = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(_static)), name="static")

SECRET_KEY = os.environ.get("SECRET_KEY", secrets.token_hex(32))
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, max_age=3600)

# ─── OAuth config ────────────────────────────────────────────────────────────

CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
REDIRECT_URI = os.environ.get("REDIRECT_URI", "http://localhost:8000/auth/callback")

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/display-video",
    "https://www.googleapis.com/auth/doubleclickbidmanager",
]

# In-memory token store: session_id → {"token": ..., "refresh_token": ..., "email": ...}
_tokens: dict = {}


def _client_config() -> dict:
    return {
        "web": {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }


def _get_credentials(request: Request) -> Optional[Credentials]:
    sid = request.session.get("sid")
    if not sid:
        return None
    data = _tokens.get(sid)
    if not data:
        return None
    return Credentials(
        token=data["token"],
        refresh_token=data.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        scopes=SCOPES,
    )


def _require_auth(request: Request) -> Credentials:
    creds = _get_credentials(request)
    if not creds:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return creds


# ─── Auth routes ─────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse((_static / "index.html").read_text())


@app.get("/auth/status")
async def auth_status(request: Request):
    sid = request.session.get("sid")
    data = _tokens.get(sid) if sid else None
    return {
        "authenticated": data is not None,
        "email": data.get("email") if data else None,
    }


@app.get("/auth/login")
async def auth_login(request: Request):
    if not CLIENT_ID or not CLIENT_SECRET:
        raise HTTPException(
            status_code=500,
            detail="Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET environment variables.",
        )
    flow = Flow.from_client_config(_client_config(), scopes=SCOPES)
    flow.redirect_uri = REDIRECT_URI
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    request.session["oauth_state"] = state
    return RedirectResponse(auth_url)


@app.get("/auth/callback")
async def auth_callback(request: Request, code: str, state: str):
    if state != request.session.get("oauth_state"):
        raise HTTPException(status_code=400, detail="OAuth state mismatch — please try again.")

    flow = Flow.from_client_config(_client_config(), scopes=SCOPES, state=state)
    flow.redirect_uri = REDIRECT_URI
    flow.fetch_token(code=code)
    creds = flow.credentials

    # Fetch basic user info
    email = None
    try:
        import googleapiclient.discovery as disc
        people = disc.build("oauth2", "v2", credentials=creds, cache_discovery=False)
        info = people.userinfo().get().execute()
        email = info.get("email")
    except Exception:
        pass

    sid = secrets.token_hex(16)
    _tokens[sid] = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "email": email,
    }
    request.session["sid"] = sid
    return RedirectResponse("/")


@app.get("/auth/logout")
async def auth_logout(request: Request):
    sid = request.session.pop("sid", None)
    if sid:
        _tokens.pop(sid, None)
    return RedirectResponse("/")


# ─── DV360 data endpoints ─────────────────────────────────────────────────────

@app.get("/api/advertisers")
async def api_advertisers(request: Request):
    creds = _require_auth(request)
    svc = DV360Service(creds)
    try:
        return await svc.list_advertisers()
    except Exception as e:
        logger.error("list_advertisers failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/api/campaigns/{advertiser_id}")
async def api_campaigns(advertiser_id: str, request: Request):
    creds = _require_auth(request)
    svc = DV360Service(creds)
    try:
        return await svc.list_campaigns(advertiser_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/api/creatives/{advertiser_id}")
async def api_creatives(advertiser_id: str, request: Request):
    creds = _require_auth(request)
    svc = DV360Service(creds)
    try:
        return await svc.list_video_creatives(advertiser_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/api/line-items/{advertiser_id}")
async def api_line_items(
    advertiser_id: str, request: Request, campaign_id: Optional[str] = None
):
    creds = _require_auth(request)
    svc = DV360Service(creds)
    try:
        return await svc.list_line_items(advertiser_id, campaign_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


# ─── Audit endpoint ───────────────────────────────────────────────────────────

class AuditRequest(BaseModel):
    advertiser_id: str
    creative_id: Optional[str] = None
    line_item_id: Optional[str] = None
    campaign_id: Optional[str] = None
    industry_vertical: str = "DEFAULT"
    campaign_objective: str = "AWARENESS"
    video_duration_seconds: Optional[int] = None
    video_format: Optional[str] = None
    target_frequency: Optional[float] = None
    budget_usd: Optional[float] = None


@app.post("/api/audit")
async def api_audit(body: AuditRequest, request: Request):
    creds = _require_auth(request)
    svc = DV360Service(creds)
    auditor = YouTubeBrandLiftAuditor(dv360_client=svc)
    try:
        result = await auditor.audit(
            advertiser_id=body.advertiser_id,
            creative_id=body.creative_id,
            line_item_id=body.line_item_id,
            campaign_id=body.campaign_id,
            industry_vertical=body.industry_vertical,
            campaign_objective=body.campaign_objective,
            video_duration_seconds=body.video_duration_seconds,
            video_format=body.video_format,
            target_frequency=body.target_frequency,
            budget_usd=body.budget_usd,
        )
        return result
    except Exception as e:
        logger.error("audit failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

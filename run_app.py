#!/usr/bin/env python3
"""Start the YouTube Brand Lift Auditor web app.

Usage (local):
  GOOGLE_CLIENT_ID=xxx GOOGLE_CLIENT_SECRET=yyy python run_app.py

Cloud Run sets PORT automatically; reload is disabled in production.
"""
import os
import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    dev = os.environ.get("ENVIRONMENT") != "production"
    uvicorn.run("web_app.main:app", host="0.0.0.0", port=port, reload=dev)

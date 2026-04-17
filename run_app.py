#!/usr/bin/env python3
"""Start the YouTube Brand Lift Auditor web app.

Usage:
  GOOGLE_CLIENT_ID=xxx GOOGLE_CLIENT_SECRET=yyy python run_app.py
"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("web_app.main:app", host="0.0.0.0", port=8000, reload=True)

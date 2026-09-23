#!/bin/bash
# One-click startup script for Team Gemini Dino Jump Event v1.1
cd "$(dirname "$0")"
echo "🦖 Starting Team Gemini Dino Jump Event Server..."
python3 server/app.py

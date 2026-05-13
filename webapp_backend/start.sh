#!/bin/bash
cd "$(dirname "$0")"
echo "Starting ChArm Vision API on http://localhost:8765"
python api_server.py

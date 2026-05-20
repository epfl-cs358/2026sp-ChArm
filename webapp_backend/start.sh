#!/bin/bash
cd "$(dirname "$0")"
echo "Starting ChArm Vision API on http://localhost:8765"
"${CHARM_PYTHON:-python3}" api_server.py

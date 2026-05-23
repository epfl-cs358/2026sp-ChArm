#!/bin/bash
set -e

# ANSI escape codes for coloring
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== ChArm Setup Script ===${NC}"

# Check for Python 3
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: python3 is not installed. Please install Python 3 and try again.${NC}"
    exit 1
fi

# Check for Node.js
if ! command -v node &> /dev/null; then
    echo -e "${YELLOW}Warning: Node.js is not installed. Frontend build/run will not work without Node.js.${NC}"
fi

# Check for NPM
if ! command -v npm &> /dev/null; then
    echo -e "${YELLOW}Warning: NPM is not installed. Frontend dependencies cannot be installed.${NC}"
fi

# Create virtual environment in root if it doesn't exist
if [ ! -d "venv" ]; then
    echo -e "${BLUE}Creating Python virtual environment in 'venv'...${NC}"
    python3 -m venv venv
else
    echo -e "${GREEN}Virtual environment 'venv' already exists.${NC}"
fi

# Upgrade pip and install requirements in the virtual environment
echo -e "${BLUE}Upgrading pip and installing requirements...${NC}"
./venv/bin/python -m pip install --upgrade pip
./venv/bin/python -m pip install -r requirements.txt

# Run the python setup wizard
echo -e "${BLUE}Starting interactive setup wizard...${NC}"
./venv/bin/python setup_wizard.py

#!/bin/bash
set -e

cd "$(dirname "$0")"

echo "=== Pressroom MCP Server — Install ==="
echo ""

# Create venv if not exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

echo "Installing dependencies..."
source venv/bin/activate
pip install -q -r requirements.txt

# Create .env if not exists
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "Created .env from .env.example"
fi

echo ""
echo "=== Installation complete ==="
echo ""
echo "To run standalone:"
echo "  source venv/bin/activate"
echo "  python server.py"
echo ""
echo "To add to Claude Code, add this to ~/.claude/settings.json:"
echo '  {
    "mcpServers": {
      "pressroom": {
        "command": "'$(pwd)'/venv/bin/python",
        "args": ["'$(pwd)'/server.py"],
        "env": {
          "PRESSROOM_URL": "http://localhost:8000"
        }
      }
    }
  }'
echo ""

#!/bin/bash
# Substack Scraper - Start Script
# Runs both the live server and scraper with a single command

cd "$(dirname "$0")"

# Activate virtual environment
source venv/bin/activate

# Kill any existing processes on port 8080
echo "🔄 Checking port 8080..."
lsof -ti:8080 | xargs kill -9 2>/dev/null
pkill -f "python.*live_server" 2>/dev/null
sleep 2

echo "=============================================="
echo "🚀 SUBSTACK SCRAPER - STARTING"
echo "=============================================="
echo ""

# Start live server in background
echo "🌐 Starting live server on http://localhost:8080..."
python live_server.py &
SERVER_PID=$!
sleep 2

# Open browser (macOS)
open http://localhost:8080 2>/dev/null || echo "   Open http://localhost:8080 in your browser"

echo ""
echo "📊 Starting scraper..."
echo ""

# Run scraper in foreground
python substack_scraper.py

# When scraper finishes, keep server running
echo ""
echo "=============================================="
echo "✅ Scraping complete! Server still running."
echo "   Press Ctrl+C to stop the server."
echo "=============================================="

# Wait for server
wait $SERVER_PID

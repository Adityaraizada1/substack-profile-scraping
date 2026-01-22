"""
Live Profile Viewer Server
Serves the HTML viewer and provides live CSV data endpoint.
Auto-refreshes data as the scraper runs.
"""

import http.server
import socketserver
import json
from pathlib import Path
from urllib.parse import urlparse

PORT = 8080
DIRECTORY = Path(__file__).parent
CSV_FILE = DIRECTORY / "substack_profiles.csv"
SKIPPED_FILE = DIRECTORY / "skipped_profiles.json"
HTML_FILE = DIRECTORY / "profile_viewer.html"


class LiveViewerHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DIRECTORY), **kwargs)

    def do_GET(self):
        parsed_path = urlparse(self.path)
        
        # Serve CSV data as API endpoint
        if parsed_path.path == '/api/csv':
            self.serve_csv()
        elif parsed_path.path == '/api/skipped':
            self.serve_skipped_json()
        # Serve HTML viewer as root
        elif parsed_path.path == '/' or parsed_path.path == '/index.html':
            self.serve_html()
        else:
            super().do_GET()

    def serve_csv(self):
        """Serve the CSV file contents."""
        try:
            if CSV_FILE.exists():
                with open(CSV_FILE, 'r', encoding='utf-8') as f:
                    content = f.read()
                self.send_response(200)
                self.send_header('Content-Type', 'text/csv; charset=utf-8')
                self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(content.encode('utf-8'))
            else:
                self.send_response(404)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'CSV file not found'}).encode())
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e)}).encode())

    def serve_skipped_json(self):
        """Serve the skipped profiles JSON file."""
        try:
            if SKIPPED_FILE.exists():
                with open(SKIPPED_FILE, 'r', encoding='utf-8') as f:
                    content = f.read()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(content.encode('utf-8'))
            else:
                # Return empty list if file doesn't exist
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps([]).encode())
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e)}).encode())

    def serve_html(self):
        """Serve the HTML viewer."""
        try:
            with open(HTML_FILE, 'r', encoding='utf-8') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            self.wfile.write(content.encode('utf-8'))
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(f'Error: {e}'.encode())

    def log_message(self, format, *args):
        # Only log non-API requests to reduce noise
        # Safely handle cases where args[0] might not be a string
        try:
            if args and isinstance(args[0], str) and '/api/' not in args[0]:
                super().log_message(format, *args)
        except Exception:
            pass  # Silently ignore logging errors


import sys

def main():
    global PORT
    if len(sys.argv) > 1 and sys.argv[1] == '--port':
        try:
            PORT = int(sys.argv[2])
        except (IndexError, ValueError):
            print("Usage: python live_server.py [--port <number>]")
            sys.exit(1)

    print("=" * 50)
    print("🌐 LIVE PROFILE VIEWER SERVER")
    print("=" * 50)
    print(f"\n📂 Serving from: {DIRECTORY}")
    print(f"📄 CSV file: {CSV_FILE.name}")
    print(f"📄 Skipped file: {SKIPPED_FILE.name}")
    print(f"\n🚀 Server running at: http://localhost:{PORT}")
    print(f"   Open this URL in your browser!")
    print(f"\n⏱️  Data refreshes automatically every 3 seconds")
    print("   Press Ctrl+C to stop the server\n")

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), LiveViewerHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n\n👋 Server stopped.")


if __name__ == "__main__":
    main()

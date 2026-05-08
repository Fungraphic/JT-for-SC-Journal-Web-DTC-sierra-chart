#!/usr/bin/env python3
"""Serveur HTTP minimal pour le Journal Web DTC.
Usage: ./serve.sh [port]
Défaut: port 8888
Ouvrir: http://localhost:8888
"""
import http.server
import socketserver
import sys
import os

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8888
os.chdir(os.path.dirname(os.path.abspath(__file__)))

class Handler(http.SimpleHTTPRequestHandler):
    extensions_map = {'.html': 'text/html', '.css': 'text/css', '.js': 'application/javascript'}

with socketserver.TCPServer(("", PORT), Handler) as httpd:
    print(f"JT for SC — Journal Web DTC")
    print(f"Ouvrir: http://localhost:{PORT}")
    print(f"Ctrl+C pour arrêter")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêté.")
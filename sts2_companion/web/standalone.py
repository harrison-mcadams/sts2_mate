"""
Zero-dependency Built-in HTTP Server for Slay the Spire 2 Companion.
Runs on any standard Python 3 installation (including fresh SteamOS / Steam Deck with no pip).
"""

import json
import mimetypes
import os
import queue
import sys
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional

from ..core.extractor import STS2Extractor
from ..core.miner import STS2HistoryMiner
from ..core.save_parser import STS2SaveParser
from ..core.watcher import STS2LiveWatcher
from ..advisor.evaluator import STS2CardRewardAdvisor


class SafeThreadingHTTPServer(ThreadingHTTPServer):
    """Threading server that suppresses harmless client disconnect tracebacks."""
    daemon_threads = True

    def handle_error(self, request, client_address):
        exc_type, _, _ = sys.exc_info()
        # Suppress standard client disconnect errors (e.g. mobile tab close, network switch)
        if exc_type in (ConnectionResetError, BrokenPipeError, ConnectionAbortedError, TimeoutError):
            return
        super().handle_error(request, client_address)


class STS2RequestHandler(BaseHTTPRequestHandler):
    parser: STS2SaveParser
    miner: STS2HistoryMiner
    watcher: STS2LiveWatcher
    advisor: STS2CardRewardAdvisor
    data_dir: str
    static_dir: str
    templates_dir: str

    def log_message(self, format, *args):
        # Silence console log spam; keep terminal clean on Steam Deck
        pass

    def do_GET(self):
        try:
            parsed_url = urllib.parse.urlparse(self.path)
            path = parsed_url.path
            query = urllib.parse.parse_qs(parsed_url.query)

            if path == "/" or path == "/index.html":
                self._serve_file(os.path.join(self.templates_dir, "index.html"), "text/html; charset=utf-8")
            elif path.startswith("/static/"):
                rel_path = path.replace("/static/", "", 1).lstrip("/")
                file_path = os.path.join(self.static_dir, rel_path)
                mime_type, _ = mimetypes.guess_type(file_path)
                self._serve_file(file_path, mime_type or "application/octet-stream")
            elif path in ("/favicon.ico", "/apple-touch-icon.png", "/apple-touch-icon-precomposed.png"):
                self.send_response(204)
                self.end_headers()
            elif path == "/api/state":
                self._send_json(self.watcher.get_state())
            elif path == "/api/cards":
                char = query.get("character", [""])[0].lower()
                q = query.get("q", [""])[0].lower()
                results = []
                for cid, c in self.parser.cards_db.items():
                    if char and c.get("character", "").lower() != char and c.get("character", "") != "colorless":
                        continue
                    if q and q not in c.get("name", "").lower() and q not in cid.lower():
                        continue
                    results.append(c)
                results.sort(key=lambda x: x.get("name", ""))
                self._send_json(results)
            elif path == "/api/relics":
                q = query.get("q", [""])[0].lower()
                results = []
                for rid, r in self.parser.relics_db.items():
                    if q and q not in r.get("name", "").lower() and q not in rid.lower():
                        continue
                    results.append(r)
                results.sort(key=lambda x: x.get("name", ""))
                self._send_json(results)
            elif path == "/api/stats":
                force = query.get("refresh", ["false"])[0].lower() == "true"
                stats = self.miner.mine_all(force_refresh=force)
                self.advisor.update_player_stats(stats)
                self._send_json(stats)
            elif path == "/api/events":
                self._handle_sse_stream()
            else:
                self.send_error(404, "Not Found")
        except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
            pass

    def do_POST(self):
        try:
            parsed_url = urllib.parse.urlparse(self.path)
            path = parsed_url.path

            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"

            if path == "/api/advise":
                try:
                    data = json.loads(body)
                except Exception:
                    data = {}
                card_ids_or_names = data.get("cards", [])
                if not card_ids_or_names:
                    self._send_json({"error": "No cards provided"}, status=400)
                    return

                resolved_ids = []
                for item in card_ids_or_names:
                    item_str = str(item).strip()
                    if item_str.startswith("CARD.") and item_str in self.parser.cards_db:
                        resolved_ids.append(item_str)
                    else:
                        matched = False
                        for cid, cinfo in self.parser.cards_db.items():
                            if cinfo.get("name", "").lower() == item_str.lower():
                                resolved_ids.append(cid)
                                matched = True
                                break
                        if not matched:
                            resolved_ids.append(f"CARD.{item_str.upper().replace(' ', '_')}")

                current_run = self.watcher.get_state()
                result = self.advisor.evaluate_reward(resolved_ids, current_run)
                self._send_json(result)
            elif path == "/api/sync":
                try:
                    extractor = STS2Extractor()
                    res = extractor.extract_all(output_dir=self.data_dir)
                    self.parser._load_databases()
                    self.advisor.cards_db = self.parser.cards_db
                    self._send_json({"success": True, "extracted": res})
                except Exception as e:
                    self._send_json({"success": False, "error": str(e)}, status=500)
            else:
                self.send_error(404, "Not Found")
        except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
            pass

    def _handle_sse_stream(self):
        """Streams live run updates via Server-Sent Events with heartbeat."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        event_q = queue.Queue(maxsize=20)

        def on_change(state):
            try:
                event_q.put_nowait(state)
            except Exception:
                pass

        self.watcher.subscribe(on_change)

        try:
            # Push initial state immediately
            init_json = json.dumps(self.watcher.get_state(), ensure_ascii=False)
            self.wfile.write(f"data: {init_json}\n\n".encode("utf-8"))
            self.wfile.flush()

            while True:
                try:
                    state = event_q.get(timeout=8.0)
                    state_json = json.dumps(state, ensure_ascii=False)
                    self.wfile.write(f"data: {state_json}\n\n".encode("utf-8"))
                    self.wfile.flush()
                except queue.Empty:
                    # Heartbeat comment to keep socket active
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
        except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
            pass
        finally:
            try:
                self.watcher._subscribers.remove(on_change)
            except Exception:
                pass

    def _serve_file(self, full_path: str, content_type: str):
        if not os.path.exists(full_path):
            self.send_error(404, "File Not Found")
            return
        try:
            with open(full_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(content)
        except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
            pass
        except Exception as e:
            self.send_error(500, f"Internal error: {e}")

    def _send_json(self, data: Any, status: int = 200):
        try:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
            pass


def run_standalone_server(
    host: str = "127.0.0.1",
    port: int = 5050,
    data_dir: str = "data",
    save_dir: Optional[str] = None
) -> None:
    """Launches the zero-dependency companion HTTP server."""
    base_web = os.path.dirname(os.path.abspath(__file__))
    static_dir = os.path.join(base_web, "static")
    templates_dir = os.path.join(base_web, "templates")

    effective_save = save_dir or ""
    history_dir = os.path.join(effective_save, "history") if effective_save else None

    parser = STS2SaveParser(data_dir=data_dir)
    miner = STS2HistoryMiner(history_dir=history_dir, data_dir=data_dir) if history_dir else STS2HistoryMiner(data_dir=data_dir)
    watcher = STS2LiveWatcher(profile_dir=effective_save, data_dir=data_dir) if effective_save else STS2LiveWatcher(data_dir=data_dir)
    advisor = STS2CardRewardAdvisor(parser.cards_db, miner.mine_all())

    watcher.start()

    class ConfiguredHandler(STS2RequestHandler):
        pass

    ConfiguredHandler.parser = parser
    ConfiguredHandler.miner = miner
    ConfiguredHandler.watcher = watcher
    ConfiguredHandler.advisor = advisor
    ConfiguredHandler.data_dir = data_dir
    ConfiguredHandler.static_dir = static_dir
    ConfiguredHandler.templates_dir = templates_dir

    server = SafeThreadingHTTPServer((host, port), ConfiguredHandler)
    server.serve_forever()

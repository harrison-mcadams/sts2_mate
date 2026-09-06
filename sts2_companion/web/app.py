"""
Flask Web Application & Companion Server for Slay the Spire 2.
"""

import json
import os
import queue
import time
from typing import Any, Dict, List, Optional
from flask import Flask, Response, jsonify, render_template, request

from ..core.extractor import STS2Extractor
from ..core.miner import STS2HistoryMiner
from ..core.save_parser import STS2SaveParser
from ..core.watcher import STS2LiveWatcher
from ..advisor.evaluator import STS2CardRewardAdvisor
from ..core.paths import get_default_save_dir


def create_app(data_dir: str = "data", save_dir: Optional[str] = None) -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")

    effective_save = save_dir or get_default_save_dir() or ""
    history_dir = os.path.join(effective_save, "history") if effective_save else None

    parser = STS2SaveParser(data_dir=data_dir)
    miner = STS2HistoryMiner(history_dir=history_dir, data_dir=data_dir) if history_dir else STS2HistoryMiner(data_dir=data_dir)
    watcher = STS2LiveWatcher(profile_dir=effective_save, data_dir=data_dir) if effective_save else STS2LiveWatcher(data_dir=data_dir)
    advisor = STS2CardRewardAdvisor(parser.cards_db, miner.mine_all())

    # Event queue for SSE updates
    event_queues: List[queue.Queue] = []

    def on_state_change(new_state: Dict[str, Any]):
        msg = f"data: {json.dumps(new_state)}\n\n"
        for q in list(event_queues):
            try:
                q.put_nowait(msg)
            except Exception:
                pass

    watcher.subscribe(on_state_change)
    watcher.start()

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/api/state")
    def get_state():
        state = watcher.get_state()
        return jsonify(state)

    @app.route("/api/events")
    def sse_events():
        def stream():
            q = queue.Queue(maxsize=20)
            event_queues.append(q)
            # Send current state initially
            initial_state = watcher.get_state()
            yield f"data: {json.dumps(initial_state)}\n\n"
            try:
                while True:
                    msg = q.get()
                    yield msg
            except GeneratorExit:
                event_queues.remove(q)

        return Response(stream(), mimetype="text/event-stream")

    @app.route("/api/cards")
    def get_cards():
        char = request.args.get("character")
        query = request.args.get("q", "").lower()
        results = []
        for cid, c in parser.cards_db.items():
            if char and c.get("character", "").lower() != char.lower() and c.get("character", "") != "colorless":
                continue
            if query and query not in c.get("name", "").lower() and query not in cid.lower():
                continue
            results.append(c)
        results.sort(key=lambda x: x.get("name", ""))
        return jsonify(results)

    @app.route("/api/relics")
    def get_relics():
        query = request.args.get("q", "").lower()
        results = []
        for rid, r in parser.relics_db.items():
            if query and query not in r.get("name", "").lower() and query not in rid.lower():
                continue
            results.append(r)
        results.sort(key=lambda x: x.get("name", ""))
        return jsonify(results)

    @app.route("/api/stats")
    def get_stats():
        force = request.args.get("refresh", "false").lower() == "true"
        stats = miner.mine_all(force_refresh=force)
        advisor.update_player_stats(stats)
        return jsonify(stats)

    @app.route("/api/advise", methods=["POST"])
    def advise_card_reward():
        data = request.get_json() or {}
        card_ids_or_names = data.get("cards", [])
        if not card_ids_or_names:
            return jsonify({"error": "No cards provided"}), 400

        # Resolve card names to IDs if needed
        resolved_ids = []
        for item in card_ids_or_names:
            item_str = str(item).strip()
            if item_str.startswith("CARD.") and item_str in parser.cards_db:
                resolved_ids.append(item_str)
            else:
                # Find by exact or fuzzy name
                matched = False
                for cid, cinfo in parser.cards_db.items():
                    if cinfo.get("name", "").lower() == item_str.lower():
                        resolved_ids.append(cid)
                        matched = True
                        break
                if not matched:
                    resolved_ids.append(f"CARD.{item_str.upper().replace(' ', '_')}")

        current_run = watcher.get_state()
        result = advisor.evaluate_reward(resolved_ids, current_run)
        return jsonify(result)

    @app.route("/api/sync", methods=["POST"])
    def resync_database():
        try:
            extractor = STS2Extractor()
            res = extractor.extract_all(output_dir=data_dir)
            parser._load_databases()
            advisor.cards_db = parser.cards_db
            return jsonify({"success": True, "extracted": res})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    return app

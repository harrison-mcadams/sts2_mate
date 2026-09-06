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
from ..advisor.ai_advisor import GeminiSTS2Advisor
from ..advisor.deck_engine import GeminiDeckEngine
from ..advisor.shop_advisor import STS2ShopAdvisor
from ..core.paths import get_default_save_dir
from ..core.config import get_gemini_api_key, get_gemini_model, load_config, save_config


def create_app(data_dir: str = "data", save_dir: Optional[str] = None) -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")

    effective_save = save_dir or get_default_save_dir() or ""
    history_dir = os.path.join(effective_save, "history") if effective_save else None

    parser = STS2SaveParser(data_dir=data_dir)
    miner = STS2HistoryMiner(history_dir=history_dir, data_dir=data_dir) if history_dir else STS2HistoryMiner(data_dir=data_dir)
    mined_stats = miner.mine_all()
    watcher = STS2LiveWatcher(profile_dir=effective_save, data_dir=data_dir) if effective_save else STS2LiveWatcher(data_dir=data_dir)
    advisor = STS2CardRewardAdvisor(parser.cards_db, mined_stats)
    ai_advisor = GeminiSTS2Advisor(parser.cards_db, parser.relics_db, mined_stats)
    deck_engine = GeminiDeckEngine(parser.cards_db, parser.relics_db, mined_stats)
    shop_advisor = STS2ShopAdvisor(parser.cards_db, parser.relics_db, parser.potions_db, mined_stats)

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

    @app.route("/api/potions")
    def get_potions():
        query = request.args.get("q", "").lower()
        results = []
        for pid, p in parser.potions_db.items():
            if query and query not in p.get("name", "").lower() and query not in pid.lower():
                continue
            results.append(p)
        results.sort(key=lambda x: x.get("name", ""))
        return jsonify(results)

    @app.route("/api/stats")
    def get_stats():
        force = request.args.get("refresh", "false").lower() == "true"
        stats = miner.mine_all(force_refresh=force)
        advisor.update_player_stats(stats)
        shop_advisor.update_player_stats(stats)
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

    @app.route("/api/ai_evaluate", methods=["POST"])
    def ai_evaluate_reward():
        data = request.get_json() or {}
        card_ids_or_names = data.get("cards") or data.get("card_ids") or []
        resolved_ids = []
        for item in card_ids_or_names:
            item_str = str(item).strip()
            if item_str.startswith("CARD.") and item_str in parser.cards_db:
                resolved_ids.append(item_str)
            else:
                matched = False
                for cid, cinfo in parser.cards_db.items():
                    if cinfo.get("name", "").lower() == item_str.lower():
                        resolved_ids.append(cid)
                        matched = True
                        break
                if not matched:
                    resolved_ids.append(f"CARD.{item_str.upper().replace(' ', '_')}")

        current_run = watcher.get_state()
        result = ai_advisor.evaluate(resolved_ids, current_run, fallback_advisor=advisor)
        return jsonify(result)

    @app.route("/api/ai_chat", methods=["POST"])
    def ai_chat():
        data = request.get_json() or {}
        user_message = str(data.get("message", "")).strip()
        if not user_message:
            return jsonify({"success": False, "error": "No message provided."}), 400

        history = data.get("history", [])
        card_ids_or_names = data.get("cards") or data.get("card_ids") or []
        initial_recommendation = data.get("initial_recommendation")

        resolved_ids = []
        for item in card_ids_or_names:
            item_str = str(item).strip()
            if item_str.startswith("CARD.") and item_str in parser.cards_db:
                resolved_ids.append(item_str)
            else:
                matched = False
                for cid, cinfo in parser.cards_db.items():
                    if cinfo.get("name", "").lower() == item_str.lower():
                        resolved_ids.append(cid)
                        matched = True
                        break
                if not matched:
                    resolved_ids.append(f"CARD.{item_str.upper().replace(' ', '_')}")

        current_run = watcher.get_state()
        result = ai_advisor.chat_followup(
            user_message=user_message,
            history=history,
            offered_card_ids=resolved_ids,
            active_run=current_run,
            initial_recommendation=initial_recommendation,
        )
        return jsonify(result)

    @app.route("/api/config", methods=["GET", "POST"])
    def handle_config():
        if request.method == "POST":
            data = request.get_json() or {}
            updates = {}
            if "gemini_api_key" in data:
                updates["gemini_api_key"] = str(data["gemini_api_key"]).strip()
            if "gemini_model" in data:
                updates["gemini_model"] = str(data["gemini_model"]).strip()
            if "enable_search_grounding" in data:
                updates["enable_search_grounding"] = bool(data["enable_search_grounding"])
            saved = save_config(updates)
            has_key = bool(get_gemini_api_key())
            return jsonify({
                "success": True,
                "config": {
                    "gemini_api_key_configured": has_key,
                    "gemini_model": get_gemini_model(),
                    "enable_search_grounding": saved.get("enable_search_grounding", True)
                }
            })
        else:
            cfg = load_config()
            has_key = bool(get_gemini_api_key())
            raw_key = cfg.get("gemini_api_key", "")
            masked = (raw_key[:4] + "..." + raw_key[-4:]) if len(raw_key) > 8 else ("configured" if has_key else "")
            return jsonify({
                "gemini_api_key_configured": has_key,
                "masked_key": masked,
                "gemini_model": get_gemini_model(),
                "enable_search_grounding": cfg.get("enable_search_grounding", True)
            })

    @app.route("/api/screen_grab", methods=["POST"])
    def screen_grab_cards():
        try:
            from sts2_companion.core.screen_reader import get_screen_reader
            sr = get_screen_reader()

            current_run = watcher.get_state()
            char_hint = current_run.get("character") if current_run else None

            result = sr.grab_and_detect(character_hint=char_hint)
            if not result.get("success"):
                return jsonify(result), 400

            detected_cards = result.get("cards", [])
            card_names = [c["name"] for c in detected_cards]

            evaluation = None
            ai_evaluation = None
            if card_names:
                resolved_ids = []
                for item in card_names:
                    item_str = str(item).strip()
                    matched = False
                    for cid, cinfo in parser.cards_db.items():
                        if cinfo.get("name", "").lower() == item_str.lower():
                            resolved_ids.append(cid)
                            matched = True
                            break
                    if not matched:
                        resolved_ids.append(f"CARD.{item_str.upper().replace(' ', '_')}")

                evaluation = advisor.evaluate_reward(resolved_ids, current_run)
                # Automatically run AI evaluation if key is available
                if get_gemini_api_key():
                    ai_evaluation = ai_advisor.evaluate(resolved_ids, current_run, fallback_advisor=advisor)

            return jsonify({
                "success": True,
                "source": result.get("source"),
                "cards": detected_cards,
                "card_names": card_names,
                "evaluation": evaluation,
                "ai_evaluation": ai_evaluation
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/deck_analysis", methods=["POST"])
    def analyze_deck():
        data = request.get_json() or {}
        force = bool(data.get("force_refresh", False))
        current_run = watcher.get_state()
        if not current_run or not current_run.get("deck"):
            return jsonify({
                "success": False,
                "error": "No active run or deck found. Launch Slay the Spire 2 or start a run to analyze."
            }), 400

        result = deck_engine.analyze_deck(current_run, force_refresh=force)
        return jsonify(result)

    @app.route("/api/deck_chat", methods=["POST"])
    def chat_deck_strategy():
        data = request.get_json() or {}
        user_msg = str(data.get("message", "")).strip()
        if not user_msg:
            return jsonify({"success": False, "error": "No message provided."}), 400

        history = data.get("history", [])
        current_run = watcher.get_state()
        if not current_run or not current_run.get("deck"):
            return jsonify({"success": False, "error": "No active deck loaded to discuss."}), 400

        result = deck_engine.chat_about_deck(user_msg, current_run, conversation_history=history)
        return jsonify(result)

    @app.route("/api/shop_advise", methods=["POST"])
    def advise_shop():
        data = request.get_json() or {}
        current_run = watcher.get_state() or {}
        result = shop_advisor.evaluate_shop(data, current_run)
        return jsonify(result)

    @app.route("/api/shop_screen_grab", methods=["POST"])
    def screen_grab_shop():
        try:
            from sts2_companion.core.screen_reader import get_screen_reader
            sr = get_screen_reader()
            current_run = watcher.get_state() or {}
            char_hint = current_run.get("character")
            result = sr.grab_and_detect_shop(character_hint=char_hint)
            if not result.get("success"):
                return jsonify(result), 400

            shop_data = {
                "gold": current_run.get("gold", 0),
                "removal_cost": 75,
                "removal_available": True,
                "cards": result.get("cards", []),
                "relics": result.get("relics", []),
                "potions": []
            }
            evaluation = shop_advisor.evaluate_shop(shop_data, current_run)
            return jsonify({
                "success": True,
                "source": result.get("source"),
                "cards": result.get("cards", []),
                "relics": result.get("relics", []),
                "evaluation": evaluation
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/sync", methods=["POST"])
    def resync_database():
        try:
            extractor = STS2Extractor()
            res = extractor.extract_all(output_dir=data_dir)
            parser._load_databases()
            advisor.cards_db = parser.cards_db
            ai_advisor.cards_db = parser.cards_db
            ai_advisor.relics_db = parser.relics_db
            deck_engine.cards_db = parser.cards_db
            deck_engine.relics_db = parser.relics_db
            shop_advisor.cards_db = parser.cards_db
            shop_advisor.relics_db = parser.relics_db
            shop_advisor.potions_db = parser.potions_db
            return jsonify({"success": True, "extracted": res})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    return app

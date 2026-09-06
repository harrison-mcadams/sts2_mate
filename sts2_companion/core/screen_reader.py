"""
STS2 Mate - Screen Grabber & OCR Card Recognition Engine.
Captures Slay the Spire 2 window/screen on PC, runs native Windows OCR,
and matches offered cards against the ground-truth STS2 card database.
"""

import asyncio
import difflib
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple
from PIL import Image

try:
    import mss
    HAS_MSS = True
except ImportError:
    HAS_MSS = False

try:
    import win32gui
    import win32process
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

try:
    import winocr
    HAS_WINOCR = True
except ImportError:
    HAS_WINOCR = False

logger = logging.getLogger("sts2_companion.screen_reader")

CARDS_DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "sts2_cards.json")
RELICS_DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "sts2_relics.json")

COMMON_STOPWORDS = {
    "form", "strike", "blade", "slash", "wall", "wave", "soul", "shot",
    "blast", "card", "cards", "turn", "deal", "gain", "lose", "draw",
    "skip", "choose", "reward", "select", "energy", "cost", "damage", "block",
    "attack", "skill", "power", "curse", "status", "mock", "common", "uncommon",
    "rare", "basic", "special", "upgrade", "exhaust", "retain", "ethereal",
    "unplayable", "innate", "target", "enemy", "enemies", "random", "times"
}


class ScreenReader:
    def __init__(self, cards_path: Optional[str] = None, relics_path: Optional[str] = None):
        self.cards_path = cards_path or CARDS_DATA_PATH
        self.relics_path = relics_path or RELICS_DATA_PATH
        self.cards: Dict[str, Dict[str, Any]] = {}
        self.normalized_cards: Dict[str, Dict[str, Any]] = {}
        self.character_cards: Dict[str, List[Dict[str, Any]]] = {}
        self.distinctive_words: Dict[str, List[Dict[str, Any]]] = {}
        self.normalized_relics: Dict[str, Dict[str, Any]] = {}
        self._load_cards()
        self._load_relics()

    def _load_relics(self):
        if not os.path.exists(self.relics_path):
            return
        try:
            with open(self.relics_path, "r", encoding="utf-8") as f:
                relics = json.load(f)
            for rid, rinfo in relics.items():
                name = rinfo.get("name", "").strip()
                if name:
                    self.normalized_relics[self._normalize(name)] = rinfo
            logger.info(f"Loaded {len(self.normalized_relics)} relics for OCR recognition.")
        except Exception as e:
            logger.error(f"Error loading relics for ScreenReader: {e}")

    def _load_cards(self):
        if not os.path.exists(self.cards_path):
            logger.warning(f"Cards database not found at {self.cards_path}")
            return

        try:
            with open(self.cards_path, "r", encoding="utf-8") as f:
                self.cards = json.load(f)

            for cid, cinfo in self.cards.items():
                if cid.startswith("CARD.MOCK_") or "mock" in cid.lower():
                    continue
                name = cinfo.get("name", "").strip()
                if not name or "mock" in name.lower():
                    continue

                norm = self._normalize(name)
                self.normalized_cards[norm] = cinfo

                char = cinfo.get("character", "colorless").lower()
                if char not in self.character_cards:
                    self.character_cards[char] = []
                self.character_cards[char].append(cinfo)

                # Index distinctive words
                words = [self._normalize(w) for w in name.split()]
                for w in words:
                    if len(w) >= 4 and w not in COMMON_STOPWORDS:
                        self.distinctive_words.setdefault(w, []).append(cinfo)

            logger.info(f"Loaded {len(self.normalized_cards)} cards for OCR recognition.")
        except Exception as e:
            logger.error(f"Error loading cards for ScreenReader: {e}")

    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r"[^a-z0-9]", "", text.lower())

    def find_game_window(self) -> Optional[Tuple[int, Dict[str, int]]]:
        """
        Locates the Slay the Spire 2 window on Windows.
        Returns (hwnd, {'left': ..., 'top': ..., 'width': ..., 'height': ...}) or None.
        """
        if not HAS_WIN32:
            return None

        found_hwnd = None

        def enum_cb(hwnd, _):
            nonlocal found_hwnd
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd).strip()
                if "slay the spire 2" in title.lower() or "slay the spire ii" in title.lower():
                    found_hwnd = hwnd
                elif not found_hwnd and "slay the spire" in title.lower():
                    found_hwnd = hwnd
            return True

        try:
            win32gui.EnumWindows(enum_cb, None)
        except Exception as e:
            logger.warning(f"Error enumerating windows: {e}")

        if not found_hwnd:
            return None

        try:
            rect = win32gui.GetWindowRect(found_hwnd)
            left, top, right, bottom = rect
            width = right - left
            height = bottom - top
            if width > 100 and height > 100:
                return found_hwnd, {
                    "left": left,
                    "top": top,
                    "width": width,
                    "height": height,
                }
        except Exception as e:
            logger.warning(f"Error getting window rect for {found_hwnd}: {e}")

        return None

    def capture(self, hwnd: Optional[int] = None, custom_bbox: Optional[Dict[str, int]] = None) -> Tuple[Optional[Image.Image], str]:
        """
        Captures the screen using mss.
        Returns (PIL.Image, source_description).
        """
        if not HAS_MSS:
            return None, "mss library not installed"

        try:
            with mss.mss() as sct:
                # 1. Custom bounding box if provided
                if custom_bbox:
                    shot = sct.grab(custom_bbox)
                    img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
                    return img, "custom_region"

                # 2. Try STS2 game window
                win_info = self.find_game_window()
                if win_info:
                    _, rect = win_info
                    if rect["width"] > 200 and rect["height"] > 200:
                        shot = sct.grab(rect)
                        img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
                        return img, "game_window"

                # 3. Fallback to primary monitor
                mon = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                shot = sct.grab(mon)
                img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
                return img, "primary_monitor"
        except Exception as e:
            logger.error(f"Failed to capture screen: {e}")
            return None, f"Capture error: {str(e)}"

    async def detect_cards(
        self,
        img: Image.Image,
        character_hint: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Runs native Windows OCR on the image, detects card names, and orders them left-to-right.
        """
        if not HAS_WINOCR:
            logger.error("winocr not installed. OCR requires Windows 10/11.")
            return []

        w, h = img.size
        # Crop slightly to focus on card rewards area and exclude taskbars
        crop_top = int(h * 0.10)
        crop_bottom = int(h * 0.90)
        cropped_img = img.crop((0, crop_top, w, crop_bottom))
        offset_y = crop_top

        try:
            ocr_result = await winocr.recognize_pil(cropped_img, "en")
        except Exception as e:
            logger.error(f"OCR recognition error: {e}")
            return []

        # Gather OCR lines and words
        ocr_lines = []
        for line in ocr_result.lines:
            text = line.text.strip()
            if not text or len(text) < 2:
                continue

            if line.words:
                min_x = min(w.bounding_rect.x for w in line.words)
                max_x = max(w.bounding_rect.x + w.bounding_rect.width for w in line.words)
                min_y = min(w.bounding_rect.y for w in line.words) + offset_y
                max_y = max(w.bounding_rect.y + w.bounding_rect.height for w in line.words) + offset_y
                center_x = (min_x + max_x) / 2.0
                center_y = (min_y + max_y) / 2.0
            else:
                center_x = w / 2.0
                center_y = h / 2.0
                min_x, max_x, min_y, max_y = 0, 0, 0, 0

            ocr_lines.append({
                "text": text,
                "norm": self._normalize(text),
                "center_x": center_x,
                "center_y": center_y,
                "words": [w.text for w in line.words] if line.words else [text],
                "bbox": (min_x, min_y, max_x, max_y)
            })

        candidates = []
        char_filter = character_hint.lower() if character_hint else None

        for item in ocr_lines:
            norm_line = item["norm"]
            if len(norm_line) < 3:
                continue

            if norm_line in {
                "skip", "chooseacard", "cardreward", "proceed", "combat", "floor", "select",
                "attack", "skill", "power", "curse", "status", "choose", "reward"
            }:
                continue

            # 1. Exact match against normalized card names
            if norm_line in self.normalized_cards:
                card = self.normalized_cards[norm_line]
                candidates.append({
                    "card": card,
                    "confidence": 1.0,
                    "center_x": item["center_x"],
                    "center_y": item["center_y"],
                    "matched_text": item["text"]
                })
                continue

            # 2. Distinctive word token match in the line
            for word in item["words"]:
                norm_w = self._normalize(word)
                if norm_w in self.distinctive_words:
                    matching_cards = self.distinctive_words[norm_w]
                    if char_filter:
                        char_matches = [c for c in matching_cards if c.get("character", "").lower() == char_filter]
                        if len(char_matches) == 1:
                            candidates.append({
                                "card": char_matches[0],
                                "confidence": 0.95,
                                "center_x": item["center_x"],
                                "center_y": item["center_y"],
                                "matched_text": item["text"]
                            })
                            continue
                    if len(matching_cards) == 1:
                        candidates.append({
                            "card": matching_cards[0],
                            "confidence": 0.90,
                            "center_x": item["center_x"],
                            "center_y": item["center_y"],
                            "matched_text": item["text"]
                        })
                        continue

            # 3. Fuzzy match against normalized cards
            best_ratio = 0.0
            best_card = None

            for c_norm, c_info in self.normalized_cards.items():
                if abs(len(c_norm) - len(norm_line)) > 4:
                    continue

                ratio = difflib.SequenceMatcher(None, norm_line, c_norm).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_card = c_info

            if best_ratio >= 0.80 and best_card:
                conf = round(best_ratio, 2)
                if char_filter and best_card.get("character", "").lower() == char_filter:
                    conf = min(1.0, conf + 0.05)

                candidates.append({
                    "card": best_card,
                    "confidence": conf,
                    "center_x": item["center_x"],
                    "center_y": item["center_y"],
                    "matched_text": item["text"]
                })

        # Multi-line / adjacent line combination
        if len(candidates) < 3 and len(ocr_lines) >= 2:
            for i in range(len(ocr_lines) - 1):
                comb_text = ocr_lines[i]["text"] + " " + ocr_lines[i + 1]["text"]
                comb_norm = self._normalize(comb_text)
                if comb_norm in self.normalized_cards:
                    card = self.normalized_cards[comb_norm]
                    candidates.append({
                        "card": card,
                        "confidence": 0.98,
                        "center_x": (ocr_lines[i]["center_x"] + ocr_lines[i + 1]["center_x"]) / 2.0,
                        "center_y": ocr_lines[i]["center_y"],
                        "matched_text": comb_text
                    })

        if not candidates:
            return []

        # Sort candidates left-to-right by X position
        candidates.sort(key=lambda c: c["center_x"])

        # Cluster by spatial X distance (cards separated by at least 10% screen width)
        min_slot_distance = w * 0.10
        clustered_slots: List[List[Dict[str, Any]]] = []

        for cand in candidates:
            if not clustered_slots:
                clustered_slots.append([cand])
            else:
                last_slot = clustered_slots[-1]
                avg_x = sum(c["center_x"] for c in last_slot) / len(last_slot)
                if abs(cand["center_x"] - avg_x) < min_slot_distance:
                    last_slot.append(cand)
                else:
                    clustered_slots.append([cand])

        # For each horizontal slot, pick highest confidence card
        detected_cards = []
        seen_card_names = set()

        for slot in clustered_slots:
            slot.sort(key=lambda c: c["confidence"], reverse=True)
            best = slot[0]
            cname = best["card"]["name"]
            if cname in seen_card_names:
                # If duplicate in same slot clustering, skip
                continue

            detected_cards.append({
                "name": cname,
                "id": best["card"]["id"],
                "character": best["card"].get("character", "colorless"),
                "type": best["card"].get("card_type", "Unknown"),
                "rarity": best["card"].get("rarity", "Common"),
                "cost": best["card"].get("cost", 1),
                "confidence": best["confidence"],
                "matched_text": best["matched_text"],
                "slot_x": round(best["center_x"], 1)
            })
            seen_card_names.add(cname)

        return detected_cards[:4]

    def grab_and_detect(self, character_hint: Optional[str] = None) -> Dict[str, Any]:
        """
        Synchronous top-level entry point: captures screen and detects offered cards.
        """
        img, source = self.capture()
        if img is None:
            return {
                "success": False,
                "error": source,
                "cards": []
            }

        try:
            detected = asyncio.run(self.detect_cards(img, character_hint=character_hint))
            return {
                "success": True,
                "source": source,
                "image_size": [img.size[0], img.size[1]],
                "count": len(detected),
                "cards": detected,
            }
        except Exception as e:
            logger.error(f"Error in grab_and_detect: {e}")
            return {
                "success": False,
                "error": str(e),
                "cards": []
            }

    async def detect_shop(self, img: Image.Image, character_hint: Optional[str] = None) -> Dict[str, Any]:
        """Runs OCR on shop screen and matches cards and relics."""
        if not HAS_WINOCR:
            return {"cards": [], "relics": []}

        w, h = img.size
        try:
            ocr_result = await winocr.recognize_pil(img, "en")
        except Exception as e:
            logger.error(f"Shop OCR error: {e}")
            return {"cards": [], "relics": []}

        recognized_cards = []
        recognized_relics = []
        seen_cards = set()
        seen_relics = set()

        for line in ocr_result.lines:
            text = line.text.strip()
            norm = self._normalize(text)
            if len(norm) < 3:
                continue

            # Check cards
            if norm in self.normalized_cards:
                c = self.normalized_cards[norm]
                cname = c.get("name", "")
                if cname not in seen_cards:
                    recognized_cards.append({
                        "name": cname,
                        "price": 65,  # default estimated price
                    })
                    seen_cards.add(cname)
                    continue

            # Check relics
            if norm in self.normalized_relics:
                r = self.normalized_relics[norm]
                rname = r.get("name", "")
                if rname not in seen_relics:
                    recognized_relics.append({
                        "name": rname,
                        "price": 160,  # default estimated price
                    })
                    seen_relics.add(rname)
                    continue

            # Fuzzy match cards
            for c_norm, c_info in self.normalized_cards.items():
                if abs(len(c_norm) - len(norm)) <= 3:
                    ratio = difflib.SequenceMatcher(None, norm, c_norm).ratio()
                    if ratio >= 0.85:
                        cname = c_info.get("name", "")
                        if cname not in seen_cards:
                            recognized_cards.append({"name": cname, "price": 65})
                            seen_cards.add(cname)
                            break

            # Fuzzy match relics
            for r_norm, r_info in self.normalized_relics.items():
                if abs(len(r_norm) - len(norm)) <= 3:
                    ratio = difflib.SequenceMatcher(None, norm, r_norm).ratio()
                    if ratio >= 0.85:
                        rname = r_info.get("name", "")
                        if rname not in seen_relics:
                            recognized_relics.append({"name": rname, "price": 160})
                            seen_relics.add(rname)
                            break

        return {
            "cards": recognized_cards[:7],
            "relics": recognized_relics[:3],
        }

    def grab_and_detect_shop(self, character_hint: Optional[str] = None) -> Dict[str, Any]:
        """Captures screen and recognizes shop items."""
        img, source = self.capture()
        if img is None:
            return {"success": False, "error": source, "cards": [], "relics": []}

        try:
            detected = asyncio.run(self.detect_shop(img, character_hint=character_hint))
            return {
                "success": True,
                "source": source,
                "cards": detected.get("cards", []),
                "relics": detected.get("relics", []),
            }
        except Exception as e:
            logger.error(f"Error in grab_and_detect_shop: {e}")
            return {"success": False, "error": str(e), "cards": [], "relics": []}

    async def detect_boss_relics(self, img: Image.Image) -> List[Dict[str, Any]]:
        """Runs OCR on boss relic selection screen and matches the 3 offered relics."""
        if not HAS_WINOCR:
            return []

        try:
            ocr_result = await winocr.recognize_pil(img, "en")
        except Exception as e:
            logger.error(f"Boss relic OCR error: {e}")
            return []

        candidates = []
        for line in ocr_result.lines:
            text = line.text.strip()
            norm = self._normalize(text)
            if len(norm) < 3:
                continue

            matched_relic = None
            if norm in self.normalized_relics:
                matched_relic = self.normalized_relics[norm]
            else:
                for r_norm, r_info in self.normalized_relics.items():
                    if abs(len(r_norm) - len(norm)) <= 3:
                        ratio = difflib.SequenceMatcher(None, norm, r_norm).ratio()
                        if ratio >= 0.85:
                            matched_relic = r_info
                            break

            if matched_relic:
                # Find bounding box center
                xs = [w.bounding_rect.x for w in line.words]
                center_x = sum(xs) / len(xs) if xs else 0
                candidates.append({
                    "name": matched_relic.get("name", ""),
                    "id": matched_relic.get("id", ""),
                    "center_x": center_x,
                })

        # Deduplicate and sort by horizontal position
        candidates.sort(key=lambda c: c["center_x"])
        unique_relics = []
        seen = set()
        for c in candidates:
            if c["name"] not in seen:
                unique_relics.append({"name": c["name"], "id": c["id"]})
                seen.add(c["name"])

        return unique_relics[:3]

    def grab_and_detect_boss_relics(self) -> Dict[str, Any]:
        """Captures screen and recognizes the 3 offered Boss Relics."""
        img, source = self.capture()
        if img is None:
            return {"success": False, "error": source, "relics": []}

        try:
            relics = asyncio.run(self.detect_boss_relics(img))
            return {
                "success": True,
                "source": source,
                "relics": relics,
            }
        except Exception as e:
            logger.error(f"Error in grab_and_detect_boss_relics: {e}")
            return {"success": False, "error": str(e), "relics": []}


_screen_reader_instance: Optional[ScreenReader] = None

def get_screen_reader() -> ScreenReader:
    global _screen_reader_instance
    if _screen_reader_instance is None:
        _screen_reader_instance = ScreenReader()
    return _screen_reader_instance

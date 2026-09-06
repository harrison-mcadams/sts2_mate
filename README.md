# Slay the Spire 2 Companion App (`sts2_mate`)

A dedicated, real-time companion application built specifically for **Slay the Spire 2** on PC.

---

## Key Features

1. **Follows Along As You Play (Live Watcher)**
   - Monitors `C:\Users\<user>\AppData\Roaming\SlayTheSpire2\steam\...\profile1\saves\current_run.save` in real time.
   - Shows active Hero, Ascension, Floor, Act, live HP bar, Gold, equipped Relics, and categorized Deck list.
   - Automatically falls back to displaying your latest completed run when not actively in a run.

2. **In-House STS2 Database (No STS1 Hallucinations)**
   - Built directly from your game install at `C:\Program Files (x86)\Steam\steamapps\common\Slay the Spire 2\SlayTheSpire2.pck`.
   - Contains **606 cards**, **304 relics**, **290 powers**, and **65 potions** authentic to Slay the Spire 2 (including Ironclad, Silent, Defect, Necrobinder, Regent, Colorless, and Curses).
   - Re-syncs directly from game files in less than a second whenever an Early Access patch or balance update drops (`python run.py --sync-game` or the "Re-sync DB" button in the UI).

3. **Card Reward Decision Advisor**
   - Evaluates card reward choices against:
     - **Act & Threat Context:** Early Act 1 Elite survival (Nob/Sentinels) vs Act 2 AOE vs Act 3 Boss scaling.
     - **Deck Balance:** Attack-to-defense ratio, card draw density, energy curve.
     - **Relic Synergy:** Synergies with *Akabeko*, *Bronze Scales*, *Lantern*, etc.
     - **Personal Historical Win Rates:** Incorporates your win rates and pick rates from your past runs.
     - **Skip Threshold:** Explicitly recommends **SKIP** if candidate cards dilute your deck.

4. **Player History & Analytics (Mined from 233 Runs)**
   - Analyzes your 233 historical `.run` files to show win rates per character (Ironclad, Silent, Defect, Necrobinder, Regent), personal card pick rates, and top lethal STS2 encounters.

5. **STS2 Compendium**
   - Full searchable encyclopedia of all cards and relics extracted straight from game files.

---

## Quick Start (PC)

```powershell
# From the project folder:
python run.py
```

Open your browser to:
**`http://localhost:5050`**

Keep the companion window open on a second monitor or side-by-side with Slay the Spire 2!

---

## Playing on Steam Deck

`sts2_mate` is built with first-class **Steam Deck & SteamOS** support:

### How it works on Steam Deck:
- Slay the Spire 2's Steam AppID is **`2868840`**. The app automatically detects Proton prefix save locations at:
  `~/.local/share/Steam/steamapps/compatdata/2868840/pfx/drive_c/users/steamuser/AppData/Roaming/SlayTheSpire2/`
- The entire extracted database (`606` cards, `304` relics) is already pre-bundled in `data/`, so no Godot extraction is even needed on the Deck!

### Recommended Setup: Phone / Tablet Companion (Zero Screen Clutter)
1. Copy the `sts2_mate` folder to your Steam Deck (via SSH, Warpinator, or flash drive).
2. In Steam Deck Desktop mode (or via terminal / background service), run:
   ```bash
   bash steamdeck_setup.sh
   # Or directly:
   python3 run.py --network
   ```
3. It will display your local network address (e.g. `http://192.168.1.50:5050`).
4. **Open that address on your smartphone or iPad/tablet** on the same Wi-Fi.
5. As you play on your Steam Deck in handheld mode, your phone sits right in front of you updating your deck, relics, and analyzing card rewards in real time!

### Alternative: In-Game Steam Deck Overlay
1. Run `python3 run.py` on your Steam Deck.
2. In Game Mode while playing STS2, press the **STEAM** button -> Web Browser -> Navigate to `http://localhost:5050`.

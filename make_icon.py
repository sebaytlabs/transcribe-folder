"""Renders icon.svg (the app's hand-drawn icon) to icon.png, which the window, the menu entry and the downloads use.
  pip install cairosvg && python3 make_icon.py
Shared by the Sebayt Labs tools: edit it in learning-kit, then run tools/sync_shared.sh there."""
from pathlib import Path

import cairosvg

HERE = Path(__file__).resolve().parent

if __name__ == "__main__":
    cairosvg.svg2png(url=str(HERE / "icon.svg"), write_to=str(HERE / "icon.png"), output_width=512, output_height=512)
    print("wrote", HERE / "icon.png")

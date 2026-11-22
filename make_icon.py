"""Draws a simple app icon: a rounded square in the app's color with a symbol. Used by the Sebayt Labs tools.
  python3 make_icon.py OUT.png "#3b5bdb" "Lk" """
import sys
from PIL import Image, ImageDraw, ImageFont


def icon(out, color, text, size=256):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([8, 8, size - 8, size - 8], radius=56, fill=color)
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "DejaVuSans-Bold.ttf", "Arial Bold.ttf"):
        try:
            font = ImageFont.truetype(path, int(size * 0.42))
            break
        except OSError:
            font = ImageFont.load_default()
    box = d.textbbox((0, 0), text, font=font)
    d.text(((size - box[2] - box[0]) / 2, (size - box[3] - box[1]) / 2), text, font=font, fill="white")
    img.save(out)


if __name__ == "__main__":
    icon(sys.argv[1], sys.argv[2], sys.argv[3])

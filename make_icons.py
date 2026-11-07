"""Render the Tonal toolbar icons. Usage: uv run --with pillow python make_icons.py"""
from pathlib import Path
from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent/'extension/icons'
S = 1024


def draw():
    image = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(image)
    d.rounded_rectangle((40, 40, S-40, S-40), radius=230, fill=(17, 17, 17, 255))
    cx, cy = 330, S//2
    d.ellipse((cx-70, cy-70, cx+70, cy+70), fill=(255, 255, 255, 255))
    for radius, width, color in ((210, 64, (255, 255, 255, 255)), (360, 64, (142, 227, 208, 255))):
        d.arc((cx-radius, cy-radius, cx+radius, cy+radius), start=-48, end=48, fill=color, width=width)
    return image


if __name__ == '__main__':
    OUT.mkdir(exist_ok=True)
    art = draw()
    for size in (16, 32, 48, 128):
        art.resize((size, size), Image.LANCZOS).save(OUT/f'icon-{size}.png')
    print('wrote', sorted(p.name for p in OUT.iterdir()))

"""Non-destructive, opt-in cleanup presets for user-supplied vector logos.

'segmented': remove only uniform empty canvas rows outside the artwork,
without destroying black or white blocks that are part of the brand mark.
'light-text': remove a dark uniform backdrop while preserving anti-aliased
light lettering. Neither preset is applied unless the user selects it.
"""
from __future__ import annotations

from PIL import Image


PRESETS = {"original", "segmented", "light-text"}


def crop_segmented_canvas(image: Image.Image, tolerance: int = 18) -> Image.Image:
    im = image.convert("RGBA")
    if im.getchannel("A").getextrema()[0] < 255:
        return im  # Already transparent: keep all original segments.
    w, h = im.size
    if w < 8 or h < 8:
        return im
    rgb = im.convert("RGB")
    background = rgb.getpixel((0, h - 1))
    px = rgb.load()
    # Check full rows. Never trim left/right: black tiles may be intended.
    visible = []
    step = max(1, w // 450)
    for y in range(h):
        for x in range(0, w, step):
            color = px[x, y]
            if max(abs(color[i] - background[i]) for i in range(3)) > tolerance:
                visible.append(y)
                break
    if not visible:
        return im
    top, bottom = visible[0], visible[-1] + 1
    # Require substantial padding to avoid removing thin intentional borders.
    min_padding = max(8, int(0.08 * h))
    if top >= min_padding or h - bottom >= min_padding:
        top = max(0, top - max(1, int(0.015 * h))) if top >= min_padding else 0
        bottom = min(h, bottom + max(1, int(0.015 * h))) if h - bottom >= min_padding else h
        return im.crop((0, top, w, bottom))
    return im


def transparent_dark_backdrop(image: Image.Image, tolerance: int = 28) -> Image.Image:
    im = image.convert("RGBA")
    if im.getchannel("A").getextrema()[0] < 255:
        return im
    w, h = im.size
    if not w or not h:
        return im
    corners = [im.getpixel((x, y))[:3] for x, y in
               [(0, 0), (w-1, 0), (0, h-1), (w-1, h-1)]]
    if any(max(pixel) > 50 for pixel in corners):
        return im  # Not a dark uniform canvas; do not erase content.
    if any(max(abs(pixel[i] - corners[0][i]) for i in range(3)) > 18
           for pixel in corners[1:]):
        return im
    bg = corners[0]
    pixels = []
    for r, g, b, a in im.getdata():
        distance = max(abs(r-bg[0]), abs(g-bg[1]), abs(b-bg[2]))
        # Soft alpha transition preserves antialiased edges of thin letters.
        if distance <= tolerance:
            pixels.append((r, g, b, 0))
        elif distance < tolerance + 45:
            pixels.append((r, g, b, round(a*(distance-tolerance)/45)))
        else:
            pixels.append((r, g, b, a))
    out = Image.new("RGBA", im.size)
    out.putdata(pixels)
    return out


def apply_preset(image: Image.Image, preset: str) -> Image.Image:
    if preset not in PRESETS:
        raise ValueError("Neznáma predvoľba spracovania loga.")
    if preset == "segmented":
        return crop_segmented_canvas(image)
    if preset == "light-text":
        return transparent_dark_backdrop(image)
    return image.convert("RGBA")

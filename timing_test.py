#!/usr/bin/env python3
import time
import numpy as np
from PIL import Image

FB_WIDTH = 240
FB_HEIGHT = 320

base_img = Image.open("uploads/vynil.png").convert('RGBA')
size = min(FB_WIDTH, FB_HEIGHT)
base_img = base_img.resize((size, size))

t0 = time.time()
rotated = base_img.rotate(45, resample=Image.BICUBIC, expand=False)
t1 = time.time()
rgb = np.asarray(rotated.convert('RGB'))
alpha = np.asarray(rotated.split()[-1])
t2 = time.time()
canvas = np.zeros((FB_HEIGHT, FB_WIDTH, 3), dtype=np.uint8)
mask = alpha > 0
paste_x = (FB_WIDTH - size) // 2
paste_y = (FB_HEIGHT - size) // 2
canvas[paste_y:paste_y+size, paste_x:paste_x+size][mask] = rgb[mask]
t3 = time.time()
r = canvas[:, :, 0].astype(np.uint16)
g = canvas[:, :, 1].astype(np.uint16)
b = canvas[:, :, 2].astype(np.uint16)
rgb565 = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
raw = rgb565.astype('<u2').tobytes()
t4 = time.time()

fb = open("/dev/fb1", "r+b")
fb.seek(0)
fb.write(raw)
fb.flush()
fb.close()
t5 = time.time()

print(f"rotate:      {(t1-t0)*1000:.1f} ms")
print(f"to numpy:    {(t2-t1)*1000:.1f} ms")
print(f"composite:   {(t3-t2)*1000:.1f} ms")
print(f"to rgb565:   {(t4-t3)*1000:.1f} ms")
print(f"fb write:    {(t5-t4)*1000:.1f} ms")
print(f"TOTAL:       {(t5-t0)*1000:.1f} ms  ({1/(t5-t0):.1f} fps max)")

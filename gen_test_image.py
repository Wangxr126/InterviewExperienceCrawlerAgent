#!/usr/bin/env python3
"""生成测试用 OCR 图片"""
from PIL import Image, ImageDraw

img = Image.new('RGB', (800, 400), color=(255, 255, 255))
draw = ImageDraw.Draw(img)

draw.rectangle([20, 20, 780, 380], outline=(0, 0, 0), width=3)
draw.text((40, 50),  'OCR Test Image',                                   fill=(0, 0, 0))
draw.text((40, 100), 'Q: What is the time complexity of quicksort?',      fill=(0, 0, 0))
draw.text((40, 150), 'A: Average O(n log n), Worst O(n^2)',               fill=(0, 0, 0))
draw.text((40, 200), 'Chinese: \u6d4b\u8bd5\u4e2d\u6587\u6587\u5b57\u8bc6\u522b',                         fill=(0, 0, 0))
draw.text((40, 250), 'Number: 1234567890',                                fill=(0, 0, 0))

out = 'test_ocr_image.png'
img.save(out)
print(f'Saved: {out}')

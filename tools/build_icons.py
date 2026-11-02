# 손글씨 아이콘 그림(흰 바탕) → 마고 타종 아이콘 전부
#   tools/icons/desktop.png(주황 '마고 타종') → app/assets/ui/app.ico (창·트레이·왼쪽 메뉴 로고·exe·설치 파일)
#   tools/icons/android.png(보라 '마고 타종') → 안드로이드 런처 아이콘(mipmap-*), 왼쪽 메뉴 로고(drawable-nodpi/app_icon.png)
#   tools/icons/cloud.png(초록 '클라우드' = 마고에듀 통합 클라우드) → 안드로이드 화면 속 클라우드 아이콘(drawable-nodpi/cloud_mark.png)
# 작은 크기에서는 선을 굵게 다시 그려서 글자가 사라지지 않게 한다.
# 사용: python tools/build_icons.py   (Pillow, numpy, scipy 필요)
from pathlib import Path

import io
import struct

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import distance_transform_edt


class Drawing:
    """흰 바탕에 한 가지 색으로 그린 그림 → 잉크 양(0~1)과 선 색."""

    def __init__(self, path):
        rgb = np.asarray(Image.open(path).convert('RGB')).astype(np.float32)
        d = 255.0 - rgb
        far = np.sqrt((d ** 2).sum(axis=2))
        self.ink = tuple(int(v) for v in np.median(rgb[far > far.max() * 0.8], axis=0))
        v = 255.0 - np.array(self.ink, np.float32)
        a = np.clip((d * v).sum(axis=2) / (v * v).sum(), 0, 1)  # 흰색→선 색 사이 어디쯤인지 = 잉크 양
        a[a < 0.06] = 0
        ys, xs = np.nonzero(a)
        self.mask = a[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        b = self.mask > 0.5
        p = np.pad(b, 1)
        edge = b & ~(p[2:, 1:-1] & p[:-2, 1:-1] & p[1:-1, 2:] & p[1:-1, :-2])
        self.stroke = 2.0 * b.sum() / edge.sum()  # 선 굵기(원본 픽셀) ≈ 2 × 넓이 / 둘레
        h, w = self.mask.shape
        yy, xx = np.nonzero(b)
        self.reach = np.sqrt((yy - h / 2) ** 2 + (xx - w / 2) ** 2).max()  # 가운데에서 가장 먼 잉크까지

    def ink_alpha(self, scale, stroke):
        """scale 배로 키운 잉크. 선이 stroke(같은 픽셀 단위)보다 가늘면 그만큼 굵게."""
        h, w = self.mask.shape
        W, H = max(1, round(w * scale)), max(1, round(h * scale))
        a = np.asarray(Image.fromarray((self.mask * 255).astype(np.uint8)).resize((W, H), Image.BICUBIC)).astype(np.float32) / 255
        grow = (stroke - self.stroke * scale) / 2 if stroke else 0
        if grow > 0:
            a = np.pad(a, int(grow) + 2)
            dist = distance_transform_edt(a <= 0.5)
            a = np.maximum(a, np.clip(grow + 0.5 - dist, 0, 1))
        return a


def render(dr, size, *, bg='tile', fill=0.78, reach=None, stroke=None, radius=0.22, color=None):
    """size×size RGBA. 크게 그린 뒤 줄여서 경계를 부드럽게.
    bg: 'tile'(흰 둥근 사각형) | 'square'(흰 정사각형) | 'circle'(흰 원) | None(투명)
    fill: 글자 상자의 긴 변 / size,  reach: 가운데에서 가장 먼 잉크까지 / size (fill 대신)
    stroke: 이 크기에서의 최소 선 굵기(px),  color: 선 색 (기본: 그림의 색)"""
    ss = max(2, -(-1024 // size))
    S = size * ss
    h, w = dr.mask.shape
    scale = (reach * S / dr.reach) if reach else (fill * S / max(h, w))
    a = dr.ink_alpha(scale, stroke * ss if stroke else None)
    im = Image.new('RGBA', (S, S), (255, 255, 255, 0))
    g = ImageDraw.Draw(im)
    if bg == 'tile':
        g.rounded_rectangle((0, 0, S - 1, S - 1), radius=round(S * radius), fill=(255, 255, 255, 255))
    elif bg == 'square':
        g.rectangle((0, 0, S, S), fill=(255, 255, 255, 255))
    elif bg == 'circle':
        g.ellipse((0, 0, S - 1, S - 1), fill=(255, 255, 255, 255))
    ink = Image.new('RGBA', (a.shape[1], a.shape[0]), (color or dr.ink) + (255,))
    ink.putalpha(Image.fromarray((a * 255).astype(np.uint8)))
    im.alpha_composite(ink, ((S - a.shape[1]) // 2, (S - a.shape[0]) // 2))
    return im.resize((size, size), Image.LANCZOS)


def tile_stroke(size):
    """창·작업 표시줄·설치 파일 아이콘의 크기별 최소 선 굵기(px)."""
    table = {16: 1.5, 20: 1.7, 24: 1.9, 32: 2.3, 40: 2.6, 48: 2.9, 64: 3.4, 100: 4.4, 128: 5.2, 256: 8.5, 512: 15}
    ks = sorted(table)
    if size >= ks[-1]:
        return table[ks[-1]] * size / ks[-1]
    lo = max(k for k in ks if k <= size)
    hi = min(k for k in ks if k >= size)
    return table[lo] if lo == hi else table[lo] + (table[hi] - table[lo]) * (size - lo) / (hi - lo)


def tile(dr, size):
    # 작을수록 여백을 줄여 글자를 크게
    fill = 0.86 if size <= 24 else 0.82 if size <= 48 else 0.78
    return render(dr, size, bg='tile', fill=fill, stroke=tile_stroke(size), radius=0.18 if size <= 24 else 0.22)


def save_ico(path, frames, bmp_upto=0):
    """크기별 그림을 그대로 담은 ICO. bmp_upto 이하 크기는 BMP(예전 프로그램도 읽음), 나머지는 PNG(작은 파일)."""
    frames = sorted(frames, key=lambda f: f.width)
    blobs = []
    for f in frames:
        w, h = f.size
        if w <= bmp_upto:
            px = np.asarray(f.convert('RGBA'))[::-1]  # 아래 줄부터
            xor = px[..., [2, 1, 0, 3]].tobytes()
            row = (w + 31) // 32 * 4
            mask = np.packbits(px[..., 3] == 0, axis=1)
            andm = b''.join(r.tobytes().ljust(row, b'\0') for r in mask)
            blobs.append(struct.pack('<IiiHHIIiiII', 40, w, h * 2, 1, 32, 0, len(xor) + len(andm), 0, 0, 0, 0) + xor + andm)
        else:
            b = io.BytesIO()
            f.save(b, 'PNG', optimize=True)
            blobs.append(b.getvalue())
    out = struct.pack('<HHH', 0, 1, len(frames))
    offset = 6 + 16 * len(frames)
    for f, b in zip(frames, blobs):
        w, h = f.size
        out += struct.pack('<BBBBHHII', w % 256, h % 256, 0, 0, 1, 32, len(b), offset)
        offset += len(b)
    with open(path, 'wb') as fp:
        fp.write(out + b''.join(blobs))

DENSITY = {'mdpi': 1, 'hdpi': 1.5, 'xhdpi': 2, 'xxhdpi': 3, 'xxxhdpi': 4}


if __name__ == '__main__':
    root = Path(__file__).resolve().parent.parent
    src = root / 'tools' / 'icons'
    desktop, android, cloud = Drawing(src / 'desktop.png'), Drawing(src / 'android.png'), Drawing(src / 'cloud.png')

    # PC: Qt 가 크기별 그림을 골라 쓰고, tools/build.py 는 그대로 exe 아이콘으로 쓴다
    save_ico(root / 'app' / 'assets' / 'ui' / 'app.ico', [tile(desktop, s) for s in (16, 20, 24, 32, 40, 48, 64, 128, 256)], bmp_upto=48)

    res = root / 'android' / 'app' / 'src' / 'main' / 'res'
    for name, d in DENSITY.items():
        out = res / f'mipmap-{name}'
        S, L = round(108 * d), round(48 * d)
        # 적응형 아이콘: 흰 바탕 + 글자는 가운데 지름 66dp 안전 원 안 (어떤 모양으로 잘려도 안 잘림)
        fg = render(android, S, bg=None, reach=33 / 108, stroke=2.0 * d)
        bg = Image.new('RGB', (S, S), (255, 255, 255))
        # 예전 방식 아이콘: 둥근 사각형·원
        legacy = render(android, L, bg='tile', fill=0.80, stroke=1.4 * d)
        legacy_round = render(android, L, bg='circle', reach=0.42, stroke=1.4 * d)
        for prefix in ('ic_launcher', 'icon'):  # icon* 은 안 쓰지만 같은 그림으로 맞춰 둠
            fg.save(out / f'{prefix}_foreground.webp', 'WEBP', lossless=True)
            bg.save(out / f'{prefix}_background.webp', 'WEBP', lossless=True)
            legacy.save(out / f'{prefix}.webp', 'WEBP', lossless=True)
            legacy_round.save(out / f'{prefix}_round.webp', 'WEBP', lossless=True)
    nodpi = res / 'drawable-nodpi'
    # 왼쪽 메뉴 로고: 32dp 로 보이니 그 크기에 맞춘 굵기 (둥근 모서리는 앱에서 자름)
    render(android, 512, bg='square', fill=0.80, stroke=22).save(nodpi / 'app_icon.png')
    # 화면 속 클라우드 아이콘: 흰 잉크만, 앱에서 색을 입힘 (24dp)
    render(cloud, 96, bg=None, fill=0.92, stroke=7.6, color=(255, 255, 255)).save(nodpi / 'cloud_mark.png')
    print('app.ico, 안드로이드 mipmap-*, app_icon.png, cloud_mark.png 생성')

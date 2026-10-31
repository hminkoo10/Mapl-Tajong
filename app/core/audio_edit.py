"""종소리 음원 편집: 구간 자르기, 페이드, 음량, 소리 크기 맞춤."""
from dataclasses import dataclass

from app.core import ffmpeg


@dataclass
class EditParams:
    start: float = 0.0
    end: float = 0.0          # 0 이하이면 끝까지
    fade_in: float = 0.0
    fade_out: float = 0.0
    gain_db: float = 0.0
    normalize: bool = False

    def length(self, duration):
        end = self.end if self.end > 0 else duration
        end = min(end, duration) if duration else end
        return max(0.0, end - self.start)


def build_filter(p: EditParams, duration: float) -> str:
    end = p.end if p.end > 0 else duration
    if duration:
        end = min(end, duration)
    start = max(0.0, min(p.start, end))
    length = max(0.01, end - start)

    f = [f"atrim=start={start:.3f}:end={end:.3f}", "asetpts=PTS-STARTPTS"]
    if p.normalize:
        f.append("loudnorm=I=-14:TP=-1.0:LRA=11")
    if abs(p.gain_db) >= 0.05:
        f.append(f"volume={p.gain_db:.2f}dB")
    if p.fade_in > 0:
        d = min(p.fade_in, length)
        f.append(f"afade=t=in:st=0:d={d:.3f}")
    if p.fade_out > 0:
        d = min(p.fade_out, length)
        f.append(f"afade=t=out:st={max(0.0, length - d):.3f}:d={d:.3f}")
    return ",".join(f)


def render_edit(src, dst, params: EditParams, duration: float):
    return ffmpeg.render(src, dst, build_filter(params, duration))


def compute_peaks(samples, start_idx, end_idx, buckets):
    """[start_idx, end_idx) 구간을 buckets 개로 나눠 (min, max)를 -1..1로 반환."""
    n = len(samples)
    start_idx = max(0, min(n, int(start_idx)))
    end_idx = max(start_idx, min(n, int(end_idx)))
    span = end_idx - start_idx
    out = []
    if buckets <= 0 or span <= 0:
        return out
    step = span / buckets
    for b in range(buckets):
        a = start_idx + int(b * step)
        z = start_idx + int((b + 1) * step)
        if z <= a:
            z = min(end_idx, a + 1)
        chunk = samples[a:z]
        if not chunk:
            out.append((0.0, 0.0))
            continue
        out.append((min(chunk) / 32768.0, max(chunk) / 32768.0))
    return out


def suggest_trim(samples, rate, threshold=0.02):
    """앞뒤 무음을 제외한 구간(초)을 추정."""
    if not samples:
        return 0.0, 0.0
    lim = int(threshold * 32768)
    n = len(samples)
    first = 0
    while first < n and abs(samples[first]) < lim:
        first += 1
    last = n - 1
    while last > first and abs(samples[last]) < lim:
        last -= 1
    if first >= n:
        return 0.0, n / rate
    pad = int(0.05 * rate)
    return max(0, first - pad) / rate, min(n, last + pad) / rate

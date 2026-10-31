WEEKDAYS = [("월", 1), ("화", 2), ("수", 4), ("목", 8), ("금", 16), ("토", 32), ("일", 64)]
ALL_DAYS = 127
WEEKDAYS_MASK = 31
WEEKEND_MASK = 96


def mask_to_days(mask):
    """요일 마스크를 사람이 읽기 쉬운 글로. 예) 매일, 평일, 월–목, 월·수·금"""
    m = int(mask)
    if m == ALL_DAYS:
        return "매일"
    if m == WEEKDAYS_MASK:
        return "평일"
    if m == WEEKEND_MASK:
        return "주말"
    on = [i for i, (_, bit) in enumerate(WEEKDAYS) if m & bit]
    if not on:
        return "-"
    if len(on) >= 3 and on == list(range(on[0], on[-1] + 1)):
        return f"{WEEKDAYS[on[0]][0]}–{WEEKDAYS[on[-1]][0]}"
    return "·".join(WEEKDAYS[i][0] for i in on)


def rotate_mask(mask, days):
    """요일 마스크를 days일 만큼 이동 (양수: 다음 요일)."""
    m = int(mask) & ALL_DAYS
    d = int(days) % 7
    for _ in range(d):
        m = ((m << 1) | (m >> 6)) & ALL_DAYS
    return m


def shift_time(hhmm, mask, minutes):
    """시간을 minutes 만큼 이동. 자정을 넘으면 요일도 함께 이동."""
    h, m = str(hhmm).split(":")
    total = int(h) * 60 + int(m) + int(minutes)
    day_shift, rem = divmod(total, 1440)
    return f"{rem // 60:02d}:{rem % 60:02d}", rotate_mask(mask, day_shift)


def to_minutes(hhmm):
    h, m = str(hhmm).split(":")
    return int(h) * 60 + int(m)


def format_remaining(seconds, short=False):
    seconds = max(0, int(seconds))
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, secs = divmod(seconds, 60)
    if days > 0:
        return f"{days}일 {hours:02d}:{minutes:02d}" if short else f"{days}일 {hours:02d}:{minutes:02d}:{secs:02d}"
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def ampm(hhmm):
    """'14:05' → '오후 2:05', '00:30' → '오전 12:30'. datetime/time 도 받는다."""
    if hasattr(hhmm, "hour"):
        h, m = hhmm.hour, hhmm.minute
    else:
        hs, ms = str(hhmm).split(":")[:2]
        h, m = int(hs), int(ms)
    part = "오전" if h < 12 else "오후"
    h12 = h % 12 or 12
    return f"{part} {h12}:{m:02d}"


def ampm_parts(hhmm):
    """('오후', '2:05')"""
    a, b = ampm(hhmm).split(" ", 1)
    return a, b

import time
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.data import repo
from app.core.paths import sound_file_path


def weekday_bit(dt):
    return 1 << dt.weekday()


def next_dt(base, hhmm):
    h, m = hhmm.split(":")
    return base.replace(hour=int(h), minute=int(m), second=0, microsecond=0)


@dataclass
class NextEvent:
    schedule_id: int
    name: str
    run_at: datetime
    sound_name: str
    sound_file_name: str
    volume: float


def _volume_of(s):
    v = s["volume_override"] if s["volume_override"] is not None else s["sound_volume"]
    return float(v)


class Scheduler:
    def __init__(self, conn, player):
        self.conn = conn
        self.player = player
        self.running = False
        self.paused = False
        self.next_event = None
        self._last_second = None
        self._pause_cache = None      # (날짜, 오늘 쉼 여부)
        self._last_recompute = 0.0
        # UI 알림용 콜백: on_ring(event, forced), on_event(kind, event)
        self.on_ring = None
        self.on_event = None

    def start(self):
        self.running = True
        self.paused = False
        self.recompute_next()

    def invalidate(self):
        """시간표·설정이 바뀌면 캐시를 비운다."""
        self._pause_cache = None

    def is_paused_today(self, today=None):
        today = today or datetime.now().strftime("%Y-%m-%d")
        if self._pause_cache is None or self._pause_cache[0] != today:
            self._pause_cache = (today, repo.is_pause_today(self.conn, today))
        return self._pause_cache[1]

    def undo(self, schedule_id, date_str, action):
        """건너뛰기(SKIP_ONCE)나 미리 울림(FIRED_ONCE)을 취소한다."""
        n = repo.remove_override(self.conn, date_str, schedule_id, action)
        self.recompute_next()
        return n > 0

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def stop(self):
        self.running = False
        self.next_event = None

    @staticmethod
    def _date_of(ev):
        return ev.run_at.strftime("%Y-%m-%d")

    def skip_next_once(self):
        ev = self.next_event
        if not ev:
            return None
        repo.add_override(self.conn, self._date_of(ev), ev.schedule_id, "SKIP_ONCE", "admin")
        self.recompute_next()
        return ev

    def ring_next_now(self):
        ev = self.next_event
        if not ev:
            return None
        self._ring(ev, forced=True)
        repo.add_override(self.conn, self._date_of(ev), ev.schedule_id, "FIRED_ONCE", "forced")
        self.recompute_next()
        return ev

    def _emit(self, kind, ev):
        if self.on_event:
            try:
                self.on_event(kind, ev)
            except Exception:
                pass

    def tick(self):
        if not self.running or self.paused:
            return

        now = datetime.now()
        if self._last_second == now.second:
            return
        self._last_second = now.second

        today = now.strftime("%Y-%m-%d")
        if self.is_paused_today(today):
            return

        if not self.next_event:
            # 예정된 종이 없으면 매초가 아니라 30초마다만 다시 계산
            if time.monotonic() - self._last_recompute >= 30:
                self.recompute_next()
            return

        if now < self.next_event.run_at:
            return

        ev = self.next_event
        late = int((now - ev.run_at).total_seconds())
        if late >= 5:
            repo.insert_log(self.conn, now.strftime("%Y-%m-%d %H:%M:%S"), ev.schedule_id, ev.name,
                            ev.sound_name, "MISSED", f"late={late}s")
            self._emit("missed", ev)
            self.recompute_next()
            return

        if repo.has_override(self.conn, self._date_of(ev), ev.schedule_id, "SKIP_ONCE"):
            repo.insert_log(self.conn, now.strftime("%Y-%m-%d %H:%M:%S"), ev.schedule_id, ev.name,
                            ev.sound_name, "SKIPPED", "")
            self._emit("skipped", ev)
            self.recompute_next()
            return

        self._ring(ev, forced=False)
        repo.add_override(self.conn, self._date_of(ev), ev.schedule_id, "FIRED_ONCE", "auto")
        self.recompute_next()

    def recompute_next(self):
        now = datetime.now()
        self._last_recompute = time.monotonic()
        repo.purge_stale_overrides(self.conn, now.strftime("%Y-%m-%d"))
        set_id = repo.active_set_id(self.conn)
        schedules = repo.list_schedules(self.conn, set_id)
        ov = repo.overrides_between(self.conn, now.strftime("%Y-%m-%d"),
                                    (now + timedelta(days=8)).strftime("%Y-%m-%d"))
        best = None

        for day_offset in range(0, 8):
            base = (now + timedelta(days=day_offset)).replace(hour=0, minute=0, second=0, microsecond=0)
            date_str = base.strftime("%Y-%m-%d")
            day_bit = weekday_bit(base)

            for s in schedules:
                if int(s["enabled"]) != 1:
                    continue
                if (int(s["weekday_mask"]) & day_bit) == 0:
                    continue

                run_at = next_dt(base, str(s["time_hhmm"]))
                if day_offset == 0 and run_at <= now:
                    continue

                sid = int(s["id"])
                acts = ov.get((date_str, sid))
                if acts and ("SKIP_ONCE" in acts or "FIRED_ONCE" in acts):
                    continue

                ev = NextEvent(sid, str(s["name"]), run_at, str(s["sound_name"]),
                               str(s["sound_file_name"]), _volume_of(s))
                if best is None or ev.run_at < best.run_at:
                    best = ev

            if best is not None:
                break

        self.next_event = best

    def today_events(self):
        """대시보드 타임라인용: 오늘 울릴(울린) 일정과 상태."""
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        base = now.replace(hour=0, minute=0, second=0, microsecond=0)
        bit = weekday_bit(now)
        set_id = repo.active_set_id(self.conn)
        results = repo.today_results(self.conn, today)
        overrides = repo.overrides_for_date(self.conn, today)
        paused_day = self.is_paused_today(today)
        nxt = self.next_event

        out = []
        for s in repo.list_schedules(self.conn, set_id):
            if int(s["enabled"]) != 1 or (int(s["weekday_mask"]) & bit) == 0:
                continue
            sid = int(s["id"])
            run_at = next_dt(base, str(s["time_hhmm"]))
            acts = overrides.get(sid, set())
            if run_at <= now:
                status = {"PLAYED": "played", "SKIPPED": "skipped", "FAILED": "failed",
                          "MISSED": "missed"}.get(results.get(sid), "passed")
                if status == "passed" and "SKIP_ONCE" in acts:
                    status = "skipped"
            else:
                if "SKIP_ONCE" in acts:
                    status = "will_skip"
                elif "FIRED_ONCE" in acts:
                    status = "rang_early"   # 미리 울림 → 되돌리면 정해진 시간에 다시 울림
                elif paused_day:
                    status = "paused"
                elif nxt and nxt.schedule_id == sid and nxt.run_at == run_at:
                    status = "next"
                else:
                    status = "upcoming"
            out.append({
                "id": sid, "date": today, "time": str(s["time_hhmm"]), "run_at": run_at, "name": str(s["name"]),
                "sound": str(s["sound_name"]), "status": status,
            })
        return out

    def _ring(self, ev, forced):
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            p = sound_file_path(ev.sound_file_name)
            self.player.play(str(p), ev.volume, ev.sound_name)
            repo.insert_log(self.conn, now_str, ev.schedule_id, ev.name, ev.sound_name, "PLAYED",
                            "forced" if forced else "")
            if self.on_ring:
                try:
                    self.on_ring(ev, forced)
                except Exception:
                    pass
        except Exception as e:
            repo.insert_log(self.conn, now_str, ev.schedule_id, ev.name, ev.sound_name, "FAILED", str(e))
            self._emit("failed", ev)

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

class Scheduler:
    def __init__(self, conn, player):
        self.conn = conn
        self.player = player
        self.running = False
        self.paused = False
        self.next_event = None
        self._last_second = None

    def start(self):
        self.running = True
        self.paused = False
        self.recompute_next()

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def stop(self):
        self.running = False
        self.next_event = None

    def skip_next_once(self):
        ev = self.next_event
        if not ev:
            return
        today = datetime.now().strftime("%Y-%m-%d")
        repo.add_override(self.conn, today, ev.schedule_id, "SKIP_ONCE", "admin")
        self.recompute_next()


    def ring_next_now(self):
        ev = self.next_event
        if not ev:
            return
        self._ring(ev, forced=True)
        today = datetime.now().strftime("%Y-%m-%d")
        repo.add_override(self.conn, today, ev.schedule_id, "FIRED_ONCE", "forced")
        self.recompute_next()

    def tick(self):
        if not self.running or self.paused:
            return

        today = datetime.now().strftime("%Y-%m-%d")
        if repo.is_pause_today(self.conn, today):
            return

        now = datetime.now()
        if self._last_second == now.second:
            return
        self._last_second = now.second

        if not self.next_event:
            self.recompute_next()
            return

        if now < self.next_event.run_at:
            return
        
        late = int((now - self.next_event.run_at).total_seconds())
        if late >= 5:
            repo.insert_log(
                self.conn,
                now.strftime("%Y-%m-%d %H:%M:%S"),
                self.next_event.schedule_id,
                self.next_event.name,
                self.next_event.sound_name,
                "MISSED",
                f"late={late}s"
            )
            self.recompute_next()
            return

        sid = self.next_event.schedule_id

        if repo.has_override(self.conn, today, sid, "SKIP_ONCE"):
            repo.insert_log(
                self.conn,
                now.strftime("%Y-%m-%d %H:%M:%S"),
                sid,
                self.next_event.name,
                self.next_event.sound_name,
                "SKIPPED",
                ""
            )
            self.recompute_next()
            return

        self._ring(self.next_event, forced=False)
        repo.add_override(self.conn, today, sid, "FIRED_ONCE", "auto")
        self.recompute_next()


    def recompute_next(self):
        now = datetime.now()
        today = datetime.now().strftime("%Y-%m-%d")
        repo.clear_transient_overrides(self.conn, today)
        set_id = repo.active_set_id(self.conn)
        schedules = repo.list_schedules(self.conn, set_id)
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

                if repo.has_override(self.conn, date_str, sid, "SKIP_ONCE"):
                    continue
                if repo.has_override(self.conn, date_str, sid, "FIRED_ONCE"):
                    continue

                v = s["volume_override"] if s["volume_override"] is not None else s["sound_volume"]
                ev = NextEvent(
                    schedule_id=sid,
                    name=str(s["name"]),
                    run_at=run_at,
                    sound_name=str(s["sound_name"]),
                    sound_file_name=str(s["sound_file_name"]),
                    volume=float(v),
                )

                if best is None or ev.run_at < best.run_at:
                    best = ev

            if best is not None:
                break

        self.next_event = best

    def _first_event_from(self, base):
        set_id = repo.active_set_id(self.conn)
        schedules = repo.list_schedules(self.conn, set_id)
        best = None
        today = base.strftime("%Y-%m-%d")
        for s in schedules:
            if int(s["enabled"]) != 1:
                continue
            if (int(s["weekday_mask"]) & weekday_bit(base)) == 0:
                continue

            run_at = next_dt(base, str(s["time_hhmm"]))
            sid = int(s["id"])
            if repo.has_skip_once(self.conn, today, sid):
                continue

            v = s["volume_override"] if s["volume_override"] is not None else s["sound_volume"]
            ev = NextEvent(
                schedule_id=sid,
                name=str(s["name"]),
                run_at=run_at,
                sound_name=str(s["sound_name"]),
                sound_file_name=str(s["sound_file_name"]),
                volume=float(v),
            )
            if best is None or ev.run_at < best.run_at:
                best = ev
        return best

    def _ring(self, ev, forced):
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            p = sound_file_path(ev.sound_file_name)
            self.player.play(str(p), ev.volume)
            repo.insert_log(
                self.conn,
                now_str,
                ev.schedule_id,
                ev.name,
                ev.sound_name,
                "PLAYED",
                "forced" if forced else ""
            )
        except Exception as e:
            repo.insert_log(
                self.conn,
                now_str,
                ev.schedule_id,
                ev.name,
                ev.sound_name,
                "FAILED",
                str(e)
            )

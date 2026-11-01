from app.core.timeutil import shift_time


# ---------------- sounds ----------------
def list_sounds(conn):
    return conn.execute("SELECT * FROM sounds ORDER BY id DESC").fetchall()


def get_sound(conn, sound_id):
    return conn.execute("SELECT * FROM sounds WHERE id=?", (int(sound_id),)).fetchone()


def insert_sound(conn, name, file_name, volume):
    cur = conn.execute("INSERT INTO sounds(name, file_name, volume) VALUES(?,?,?)", (name, file_name, float(volume)))
    conn.commit()
    return cur.lastrowid


def update_sound(conn, sound_id, name, volume):
    conn.execute("UPDATE sounds SET name=?, volume=? WHERE id=?", (name, float(volume), int(sound_id)))
    conn.commit()


def update_sound_file(conn, sound_id, file_name):
    conn.execute("UPDATE sounds SET file_name=? WHERE id=?", (file_name, int(sound_id)))
    conn.commit()


def file_name_in_use(conn, file_name):
    return conn.execute("SELECT 1 FROM sounds WHERE file_name=? LIMIT 1", (file_name,)).fetchone() is not None


def sound_usage_counts(conn):
    rows = conn.execute("SELECT sound_id, COUNT(*) AS n FROM schedules GROUP BY sound_id").fetchall()
    return {int(r["sound_id"]): int(r["n"]) for r in rows}


def delete_sound(conn, sound_id):
    conn.execute("DELETE FROM sounds WHERE id=?", (int(sound_id),))
    conn.commit()


# ---------------- schedules ----------------
_SCHEDULE_SELECT = """
    SELECT s.*, so.name AS sound_name, so.file_name AS sound_file_name, so.volume AS sound_volume
    FROM schedules s
    JOIN sounds so ON so.id = s.sound_id
"""


def list_schedules(conn, set_id):
    return conn.execute(_SCHEDULE_SELECT + " WHERE s.set_id = ? ORDER BY s.time_hhmm ASC, s.id ASC",
                        (int(set_id),)).fetchall()


def get_schedules(conn, ids):
    ids = [int(i) for i in ids]
    if not ids:
        return []
    q = ",".join("?" for _ in ids)
    return conn.execute(_SCHEDULE_SELECT + f" WHERE s.id IN ({q}) ORDER BY s.time_hhmm, s.id", ids).fetchall()


def insert_schedule(conn, set_id, name, weekday_mask, time_hhmm, sound_id, volume_override, enabled, commit=True):
    cur = conn.execute("""
        INSERT INTO schedules(set_id, name, weekday_mask, time_hhmm, sound_id, volume_override, enabled)
        VALUES(?,?,?,?,?,?,?)
    """, (int(set_id), name, int(weekday_mask), time_hhmm, int(sound_id),
          None if volume_override is None else float(volume_override), int(enabled)))
    if commit:
        conn.commit()
    return cur.lastrowid


def update_schedule(conn, schedule_id, name, weekday_mask, time_hhmm, sound_id, volume_override, enabled):
    conn.execute("""
        UPDATE schedules
        SET name=?, weekday_mask=?, time_hhmm=?, sound_id=?, volume_override=?, enabled=?, updated_at=datetime('now')
        WHERE id=?
    """, (name, int(weekday_mask), time_hhmm, int(sound_id),
          None if volume_override is None else float(volume_override), int(enabled), int(schedule_id)))
    _reset_one_time(conn, [schedule_id])
    conn.commit()


def _reset_one_time(conn, ids):
    """일정을 고치면 그 일정의 1회성 기록(패스/수동 타종)은 초기화한다."""
    ids = [int(i) for i in ids]
    if ids:
        q = ",".join("?" for _ in ids)
        conn.execute(f"DELETE FROM overrides WHERE schedule_id IN ({q}) AND action IN ('SKIP_ONCE','FIRED_ONCE')", ids)


def delete_schedule(conn, schedule_id):
    delete_schedules(conn, [schedule_id])


def delete_schedules(conn, ids):
    ids = [int(i) for i in ids]
    if not ids:
        return 0
    q = ",".join("?" for _ in ids)
    conn.execute(f"DELETE FROM schedules WHERE id IN ({q})", ids)
    conn.execute(f"DELETE FROM overrides WHERE schedule_id IN ({q}) AND action IN ('SKIP_ONCE','FIRED_ONCE')", ids)
    conn.commit()
    return len(ids)


def set_enabled_many(conn, ids, enabled):
    ids = [int(i) for i in ids]
    if not ids:
        return 0
    q = ",".join("?" for _ in ids)
    conn.execute(f"UPDATE schedules SET enabled=?, updated_at=datetime('now') WHERE id IN ({q})",
                 [int(enabled), *ids])
    conn.commit()
    return len(ids)


def batch_update_schedules(conn, ids, changes):
    """선택한 일정 여러 개를 한 번에 수정.

    changes 키 (모두 선택 사항):
      enabled: 0/1
      days_mode: 'set'|'add'|'remove', days_mask: int
      shift_minutes: int
      time_hhmm: 'HH:MM'
      sound_id: int
      volume: float 또는 None(기본값 사용) -> 'volume' 키가 있을 때만 적용
      name_find, name_replace: str
      set_id: int (다른 세트로 이동)
    """
    rows = get_schedules(conn, ids)
    changed = 0
    for r in rows:
        name = str(r["name"])
        mask = int(r["weekday_mask"])
        t = str(r["time_hhmm"])
        sound_id = int(r["sound_id"])
        vol = r["volume_override"]
        enabled = int(r["enabled"])
        set_id = int(r["set_id"])

        if "enabled" in changes:
            enabled = int(changes["enabled"])
        if "days_mask" in changes:
            dm = int(changes["days_mask"])
            mode = changes.get("days_mode", "set")
            if mode == "add":
                mask |= dm
            elif mode == "remove":
                mask &= ~dm
            else:
                mask = dm
        if "time_hhmm" in changes:
            t = changes["time_hhmm"]
        if changes.get("shift_minutes"):
            t, mask = shift_time(t, mask, int(changes["shift_minutes"]))
        if "sound_id" in changes:
            sound_id = int(changes["sound_id"])
        if "volume" in changes:
            vol = changes["volume"]
        if changes.get("name_find"):
            name = name.replace(changes["name_find"], changes.get("name_replace", ""))
            name = name.strip() or str(r["name"])
        if "set_id" in changes:
            set_id = int(changes["set_id"])

        if mask == 0:  # 요일을 전부 뺀 경우 원래 요일 유지
            mask = int(r["weekday_mask"])

        conn.execute("""
            UPDATE schedules
            SET name=?, weekday_mask=?, time_hhmm=?, sound_id=?, volume_override=?, enabled=?, set_id=?,
                updated_at=datetime('now')
            WHERE id=?
        """, (name, mask, t, sound_id, None if vol is None else float(vol), enabled, set_id, int(r["id"])))
        changed += 1
    _reset_one_time(conn, [r["id"] for r in rows])
    conn.commit()
    return changed


def duplicate_schedules(conn, ids, target_set_id, shift_minutes=0, name_suffix=""):
    new_ids = []
    for r in get_schedules(conn, ids):
        t, mask = str(r["time_hhmm"]), int(r["weekday_mask"])
        if shift_minutes:
            t, mask = shift_time(t, mask, shift_minutes)
        new_ids.append(insert_schedule(conn, target_set_id, str(r["name"]) + name_suffix, mask, t,
                                       int(r["sound_id"]), r["volume_override"], int(r["enabled"]), commit=False))
    conn.commit()
    return new_ids


# ---------------- logs ----------------
def insert_log(conn, occurred_at, schedule_id, schedule_name, sound_name, result, detail):
    conn.execute("""
        INSERT INTO logs(occurred_at, schedule_id, schedule_name, sound_name, result, detail)
        VALUES(?,?,?,?,?,?)
    """, (occurred_at, schedule_id, schedule_name, sound_name, result, detail))
    conn.commit()


def list_logs(conn, start_date, end_date, result_value, keyword, limit_count):
    where = []
    params = []

    if start_date:
        where.append("occurred_at >= ?")
        params.append(start_date + " 00:00:00")
    if end_date:
        where.append("occurred_at <= ?")
        params.append(end_date + " 23:59:59")
    if result_value and result_value != "ALL":
        where.append("result = ?")
        params.append(result_value)
    if keyword:
        where.append("(schedule_name LIKE ? OR sound_name LIKE ? OR detail LIKE ?)")
        k = "%" + keyword + "%"
        params.extend([k, k, k])

    sql = "SELECT * FROM logs"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(int(limit_count))
    return conn.execute(sql, tuple(params)).fetchall()


def today_results(conn, date_yyyymmdd):
    """오늘 각 일정의 마지막 로그 결과 {schedule_id: result}."""
    rows = conn.execute("""
        SELECT schedule_id, result FROM logs
        WHERE occurred_at >= ? AND occurred_at <= ? AND schedule_id IS NOT NULL
        ORDER BY id ASC
    """, (date_yyyymmdd + " 00:00:00", date_yyyymmdd + " 23:59:59")).fetchall()
    out = {}
    for r in rows:
        out[int(r["schedule_id"])] = str(r["result"])
    return out


def logs_on(conn, date_yyyymmdd):
    """그날의 기록 (오래된 것부터)."""
    return conn.execute("""
        SELECT * FROM logs WHERE occurred_at >= ? AND occurred_at <= ? ORDER BY id ASC
    """, (date_yyyymmdd + " 00:00:00", date_yyyymmdd + " 23:59:59")).fetchall()


def count_played_on(conn, date_yyyymmdd):
    r = conn.execute("SELECT COUNT(*) FROM logs WHERE result='PLAYED' AND occurred_at >= ? AND occurred_at <= ?",
                     (date_yyyymmdd + " 00:00:00", date_yyyymmdd + " 23:59:59")).fetchone()
    return int(r[0]) if r else 0


# ---------------- overrides ----------------
def add_override(conn, date_yyyymmdd, schedule_id, action, note):
    conn.execute(
        "INSERT INTO overrides(date_yyyymmdd, schedule_id, action, note) VALUES(?,?,?,?)",
        (date_yyyymmdd, int(schedule_id), action, note or "")
    )
    conn.commit()


def has_override(conn, date_yyyymmdd, schedule_id, action):
    row = conn.execute(
        "SELECT 1 FROM overrides WHERE date_yyyymmdd=? AND schedule_id=? AND action=? LIMIT 1",
        (date_yyyymmdd, int(schedule_id), action)
    ).fetchone()
    return row is not None


def remove_override(conn, date_yyyymmdd, schedule_id, action):
    cur = conn.execute("DELETE FROM overrides WHERE date_yyyymmdd=? AND schedule_id=? AND action=?",
                       (date_yyyymmdd, int(schedule_id), action))
    conn.commit()
    return cur.rowcount


def overrides_between(conn, start_yyyymmdd, end_yyyymmdd):
    """{(날짜, 일정 id): {동작, ...}} — 여러 날의 1회성 기록을 한 번에 읽는다."""
    rows = conn.execute(
        "SELECT date_yyyymmdd, schedule_id, action FROM overrides WHERE date_yyyymmdd BETWEEN ? AND ?",
        (start_yyyymmdd, end_yyyymmdd)).fetchall()
    out = {}
    for r in rows:
        out.setdefault((str(r[0]), int(r[1])), set()).add(str(r[2]))
    return out


def has_skip_once(conn, date_yyyymmdd, schedule_id):
    return has_override(conn, date_yyyymmdd, schedule_id, "SKIP_ONCE")


def overrides_for_date(conn, date_yyyymmdd):
    rows = conn.execute("SELECT schedule_id, action FROM overrides WHERE date_yyyymmdd=?",
                        (date_yyyymmdd,)).fetchall()
    out = {}
    for r in rows:
        out.setdefault(int(r["schedule_id"]), set()).add(str(r["action"]))
    return out


def purge_stale_overrides(conn, today_yyyymmdd):
    """지난 날짜의 1회성 기록(패스/수동 타종)만 정리. 오늘 이후 기록은 유지해야 패스가 동작한다."""
    cur = conn.execute(
        "DELETE FROM overrides WHERE date_yyyymmdd < ? AND action IN ('SKIP_ONCE','FIRED_ONCE')",
        (today_yyyymmdd,)
    )
    if cur.rowcount:
        conn.commit()


def clear_transient_overrides(conn, date_yyyymmdd):
    conn.execute(
        "DELETE FROM overrides WHERE date_yyyymmdd=? AND action IN ('SKIP_ONCE','FIRED_ONCE')",
        (date_yyyymmdd,)
    )
    conn.commit()


def set_pause_today(conn, date_yyyymmdd, paused):
    conn.execute("DELETE FROM overrides WHERE date_yyyymmdd=? AND action='PAUSE_DAY'", (date_yyyymmdd,))
    if paused:
        conn.execute(
            "INSERT INTO overrides(date_yyyymmdd, schedule_id, action, note) VALUES(?,?,?,?)",
            (date_yyyymmdd, 0, "PAUSE_DAY", "admin")
        )
    conn.commit()


def is_pause_today(conn, date_yyyymmdd):
    row = conn.execute(
        "SELECT 1 FROM overrides WHERE date_yyyymmdd=? AND action='PAUSE_DAY' LIMIT 1",
        (date_yyyymmdd,)
    ).fetchone()
    return row is not None


# ---------------- schedule sets ----------------
def list_schedule_sets(conn):
    return conn.execute("SELECT * FROM schedule_sets ORDER BY id ASC").fetchall()


def schedule_counts_by_set(conn):
    rows = conn.execute("SELECT set_id, COUNT(*) AS n FROM schedules GROUP BY set_id").fetchall()
    return {int(r["set_id"]): int(r["n"]) for r in rows if r["set_id"] is not None}


def insert_schedule_set(conn, name):
    cur = conn.execute("INSERT INTO schedule_sets(name) VALUES(?)", (name,))
    conn.commit()
    return cur.lastrowid


def rename_schedule_set(conn, set_id, name):
    conn.execute("UPDATE schedule_sets SET name=? WHERE id=?", (name, int(set_id)))
    conn.commit()


def duplicate_schedule_set(conn, set_id, new_name):
    cur = conn.execute("INSERT INTO schedule_sets(name) VALUES(?)", (new_name,))
    new_id = cur.lastrowid
    conn.execute("""
        INSERT INTO schedules(set_id, name, weekday_mask, time_hhmm, sound_id, volume_override, enabled, sort_order)
        SELECT ?, name, weekday_mask, time_hhmm, sound_id, volume_override, enabled, sort_order
        FROM schedules WHERE set_id=? ORDER BY time_hhmm, id
    """, (new_id, int(set_id)))
    conn.commit()
    return new_id


def unique_set_name(conn, base):
    names = {str(r["name"]) for r in list_schedule_sets(conn)}
    if base not in names:
        return base
    n = 2
    while f"{base} {n}" in names:
        n += 1
    return f"{base} {n}"


def delete_schedule_set(conn, set_id):
    conn.execute("DELETE FROM schedules WHERE set_id=?", (int(set_id),))
    conn.execute("DELETE FROM schedule_sets WHERE id=?", (int(set_id),))
    conn.commit()


# ---------------- settings ----------------
def get_setting(conn, key, default_value=""):
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row[0] if row else default_value


def set_setting(conn, key, value):
    conn.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (key, str(value)))
    conn.commit()


def active_set_id(conn):
    row = conn.execute("SELECT value FROM settings WHERE key='active_set_id'").fetchone()
    if not row:
        return 0
    try:
        return int(row[0])
    except (TypeError, ValueError):
        return 0


def active_set_name(conn):
    row = conn.execute("SELECT name FROM schedule_sets WHERE id=?", (active_set_id(conn),)).fetchone()
    return str(row[0]) if row else "-"


def set_active_set(conn, set_id):
    set_setting(conn, "active_set_id", int(set_id))

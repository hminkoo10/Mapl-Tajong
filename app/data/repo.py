def list_sounds(conn):
    return conn.execute("SELECT * FROM sounds ORDER BY id DESC").fetchall()

def insert_sound(conn, name, file_name, volume):
    conn.execute("INSERT INTO sounds(name, file_name, volume) VALUES(?,?,?)", (name, file_name, float(volume)))
    conn.commit()
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]

def update_sound(conn, sound_id, name, volume):
    conn.execute("UPDATE sounds SET name=?, volume=? WHERE id=?", (name, float(volume), int(sound_id)))
    conn.commit()

def delete_sound(conn, sound_id):
    conn.execute("DELETE FROM sounds WHERE id=?", (int(sound_id),))
    conn.commit()

def list_schedules(conn):
    return conn.execute("""
        SELECT s.*, so.name AS sound_name, so.file_name AS sound_file_name, so.volume AS sound_volume
        FROM schedules s
        JOIN sounds so ON so.id = s.sound_id
        ORDER BY s.sort_order, s.time_hhmm
    """).fetchall()

def insert_schedule(conn, name, weekday_mask, time_hhmm, sound_id, volume_override, enabled, sort_order):
    conn.execute("""
        INSERT INTO schedules(name, weekday_mask, time_hhmm, sound_id, volume_override, enabled, sort_order)
        VALUES(?,?,?,?,?,?,?)
    """, (name, int(weekday_mask), time_hhmm, int(sound_id),
          None if volume_override is None else float(volume_override),
          int(enabled), int(sort_order)))
    conn.commit()
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]

def update_schedule(conn, schedule_id, name, weekday_mask, time_hhmm, sound_id, volume_override, enabled, sort_order):
    conn.execute("""
        UPDATE schedules
        SET name=?, weekday_mask=?, time_hhmm=?, sound_id=?, volume_override=?, enabled=?, sort_order=?, updated_at=datetime('now')
        WHERE id=?
    """, (name, int(weekday_mask), time_hhmm, int(sound_id),
          None if volume_override is None else float(volume_override),
          int(enabled), int(sort_order), int(schedule_id)))
    conn.commit()

def delete_schedule(conn, schedule_id):
    conn.execute("DELETE FROM schedules WHERE id=?", (int(schedule_id),))
    conn.commit()

def insert_log(conn, occurred_at, schedule_id, schedule_name, sound_name, result, detail):
    conn.execute("""
        INSERT INTO logs(occurred_at, schedule_id, schedule_name, sound_name, result, detail)
        VALUES(?,?,?,?,?,?)
    """, (occurred_at, schedule_id, schedule_name, sound_name, result, detail))
    conn.commit()

def add_override(conn, date_yyyymmdd, schedule_id, action, note):
    conn.execute(
        "INSERT INTO overrides(date_yyyymmdd, schedule_id, action, note) VALUES(?,?,?,?)",
        (date_yyyymmdd, int(schedule_id), action, note or "")
    )
    conn.commit()

def has_skip_once(conn, date_yyyymmdd, schedule_id):
    row = conn.execute(
        "SELECT 1 FROM overrides WHERE date_yyyymmdd=? AND schedule_id=? AND action='SKIP_ONCE' LIMIT 1",
        (date_yyyymmdd, int(schedule_id))
    ).fetchone()
    return row is not None

def set_pause_today(conn, date_yyyymmdd, paused):
    if paused:
        conn.execute(
            "INSERT INTO overrides(date_yyyymmdd, schedule_id, action, note) VALUES(?,?,?,?)",
            (date_yyyymmdd, 0, "PAUSE_DAY", "admin")
        )
    else:
        conn.execute(
            "DELETE FROM overrides WHERE date_yyyymmdd=? AND action='PAUSE_DAY'",
            (date_yyyymmdd,)
        )
    conn.commit()

def is_pause_today(conn, date_yyyymmdd):
    row = conn.execute(
        "SELECT 1 FROM overrides WHERE date_yyyymmdd=? AND action='PAUSE_DAY' LIMIT 1",
        (date_yyyymmdd,)
    ).fetchone()
    return row is not None

def list_logs(conn, limit_count):
    return conn.execute(
        "SELECT * FROM logs ORDER BY id DESC LIMIT ?",
        (int(limit_count),)
    ).fetchall()

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

def clear_transient_overrides(conn, date_yyyymmdd):
    conn.execute(
        "DELETE FROM overrides WHERE date_yyyymmdd=? AND action IN ('SKIP_ONCE','FIRED_ONCE')",
        (date_yyyymmdd,)
    )
    conn.commit()

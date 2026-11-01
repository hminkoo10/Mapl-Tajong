package com.milky.mataf.core

import android.content.Context
import com.milky.mataf.data.DATE
import com.milky.mataf.data.Repo
import com.milky.mataf.data.TimeUtil
import java.time.LocalDate
import java.time.LocalDateTime

data class NextEvent(
    val scheduleId: Long,
    val name: String,
    val runAt: LocalDateTime,
    val soundId: Long,
    val soundName: String,
    val soundFile: String,
    val volume: Double,
)

/** 오늘 목록의 한 줄. status: played/skipped/failed/missed/passed/will_skip/rang_early/paused/next/upcoming */
data class TodayEvent(
    val scheduleId: Long,
    val date: LocalDate,
    val hhmm: String,
    val runAt: LocalDateTime,
    val name: String,
    val sound: String,
    val status: String,
    /** 결과를 남긴 다른 기기 이름 (이 기기면 "") */
    val device: String = "",
)

/** 종 시간 계산 (데스크톱 app/core/scheduler.py 와 같은 규칙) */
object Scheduler {
    const val SKIP = "SKIP_ONCE"
    const val FIRED = "FIRED_ONCE"

    fun isPaused(repo: Repo): Boolean = repo.setting("paused", "0") == "1"

    fun setPaused(ctx: Context, on: Boolean) {
        Repo(ctx).setSetting("paused", if (on) "1" else "0")
        Alarms.reschedule(ctx)
    }

    fun next(repo: Repo, now: LocalDateTime = LocalDateTime.now()): NextEvent? {
        repo.purgeOldOverrides(now.toLocalDate())
        val schedules = repo.schedules(repo.activeSetId()).filter { it.enabled }
        if (schedules.isEmpty()) return null
        val ov = repo.overridesBetween(now.toLocalDate(), now.toLocalDate().plusDays(8))
        for (offset in 0L..7L) {
            val day = now.toLocalDate().plusDays(offset)
            if (repo.isPauseDay(day)) continue
            val bit = TimeUtil.bit(day)
            val best = schedules.asSequence()
                .filter { it.mask and bit != 0 }
                .map { it to TimeUtil.at(day, it.hhmm) }
                .filter { (_, at) -> offset > 0 || at.isAfter(now) }
                .filter { (s, _) ->
                    val acts = ov[day.format(DATE) to s.id]
                    acts == null || (SKIP !in acts && FIRED !in acts)
                }
                .minByOrNull { it.second }
            if (best != null) {
                val (s, at) = best
                return NextEvent(s.id, s.name, at, s.soundId, s.soundName, s.soundFile, s.volume)
            }
        }
        return null
    }

    fun today(repo: Repo, now: LocalDateTime = LocalDateTime.now()): List<TodayEvent> {
        val today = now.toLocalDate()
        val bit = TimeUtil.bit(today)
        val results = repo.todayResults(today)
        val ov = repo.overridesBetween(today, today)
        val pausedDay = repo.isPauseDay(today)
        val nxt = next(repo, now)
        return repo.schedules(repo.activeSetId())
            .filter { it.enabled && it.mask and bit != 0 }
            .map { s ->
                val at = TimeUtil.at(today, s.hhmm)
                val acts = ov[today.format(DATE) to s.id] ?: emptySet()
                val status = if (!at.isAfter(now)) {
                    when (results[s.id]?.first) {
                        "PLAYED" -> "played"
                        "SKIPPED" -> "skipped"
                        "FAILED" -> "failed"
                        "MISSED" -> "missed"
                        else -> if (SKIP in acts) "skipped" else "passed"
                    }
                } else when {
                    SKIP in acts -> "will_skip"
                    FIRED in acts -> "rang_early"
                    pausedDay -> "paused"
                    nxt != null && nxt.scheduleId == s.id && nxt.runAt == at -> "next"
                    else -> "upcoming"
                }
                TodayEvent(s.id, today, s.hhmm, at, s.name, s.soundName, status,
                    if (!at.isAfter(now)) results[s.id]?.second.orEmpty() else "")
            }
            .sortedBy { it.runAt }
    }

    /** 다음 종 한 번 건너뛰기 */
    fun skipNext(ctx: Context): NextEvent? {
        val repo = Repo(ctx)
        val ev = next(repo) ?: return null
        repo.addOverride(ev.runAt.toLocalDate(), ev.scheduleId, SKIP, "admin")
        Alarms.reschedule(ctx)
        return ev
    }

    /** 다음 종을 지금 울리고, 정해진 시각에는 울리지 않게 표시 */
    fun ringNextNow(ctx: Context): NextEvent? {
        val repo = Repo(ctx)
        val ev = next(repo) ?: return null
        BellService.ring(ctx, ev.scheduleId, forced = true)
        repo.addOverride(ev.runAt.toLocalDate(), ev.scheduleId, FIRED, "forced")
        Alarms.reschedule(ctx)
        return ev
    }

    /**
     * 종을 울리지 않는 기기의 '다음 종 지금 울리기': 종을 울리는 기기에 요청을 보내고,
     * 이 기기 화면에서도 다음 종으로 넘어가게 미리 울림으로 표시한다. 클라우드에 로그인하지 않았으면 null.
     */
    fun requestNext(ctx: Context): NextEvent? {
        val repo = Repo(ctx)
        val ev = next(repo) ?: return null
        if (!Cloud.requestRing(ev.scheduleId, null)) return null
        repo.addOverride(ev.runAt.toLocalDate(), ev.scheduleId, FIRED, "forced")
        Alarms.reschedule(ctx)
        return ev
    }

    /** 그 일정이 다음에 울릴 날짜 (쉬는 날·건너뛰기·이미 울림은 넘긴다) */
    fun nextDateOf(repo: Repo, s: com.milky.mataf.data.Schedule, now: LocalDateTime = LocalDateTime.now()): LocalDate? =
        CloudModel.nextOccurrence(s.mask, s.hhmm, now) { day ->
            repo.isPauseDay(day) || repo.hasOverride(day, s.id, SKIP) || repo.hasOverride(day, s.id, FIRED)
        }

    /** 건너뛰기·미리 울림 되돌리기 */
    fun undo(ctx: Context, scheduleId: Long, date: LocalDate, action: String): Boolean {
        val n = Repo(ctx).removeOverride(date, scheduleId, action)
        Alarms.reschedule(ctx)
        return n > 0
    }
}

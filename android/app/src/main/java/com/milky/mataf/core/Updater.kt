package com.milky.mataf.core

import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageInstaller
import android.net.Uri
import android.os.Build
import android.provider.Settings
import com.milky.mataf.BuildConfig
import com.milky.mataf.FullscreenActivity
import com.milky.mataf.data.Repo
import com.milky.mataf.ui.components.Toasts
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.Request
import org.json.JSONArray
import java.io.File
import java.io.IOException
import java.security.MessageDigest
import java.time.Duration
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter

class UpdateError(message: String) : Exception(message)

data class UpdateInfo(
    val version: String,
    val title: String,
    val notes: String,
    val pageUrl: String,
    val assetName: String,
    val assetUrl: String,
    val size: Long,
    val sha256: String?,
    val shaUrl: String?,
)

/**
 * 자동 업데이트 (데스크톱 app/core/updater.py 와 같은 흐름).
 * GitHub Releases 에서 `MaplTajong-x.y.z.apk` 를 찾아 받고(SHA-256 확인), 안드로이드 설치기로 설치한다.
 * 데스크톱 릴리스도 같은 저장소에 올라오므로 '최신 릴리스'가 아니라 APK 파일 이름으로 버전을 찾는다.
 */
object Updater {
    private const val REPO = "hminkoo10/Mapl-Tajong"
    private const val RELEASES_API = "https://api.github.com/repos/$REPO/releases?per_page=30"
    const val RELEASES_PAGE = "https://github.com/$REPO/releases"
    private val ASSET_RE = Regex("""^MaplTajong-(\d+(?:\.\d+){1,3})\.apk$""", RegexOption.IGNORE_CASE)
    private val ALLOWED_HOSTS = listOf("github.com", "githubusercontent.com")
    private val UA = "MaplTajong-Android/${BuildConfig.VERSION_NAME}"

    fun parseVersion(s: String): List<Int> {
        val nums = Regex("\\d+").findAll(s).take(4).map { it.value.toInt() }.toMutableList()
        while (nums.size < 3) nums += 0
        return nums
    }

    fun isNewer(a: String, b: String): Boolean {
        val x = parseVersion(a)
        val y = parseVersion(b)
        for (i in 0 until maxOf(x.size, y.size)) {
            val d = x.getOrElse(i) { 0 } - y.getOrElse(i) { 0 }
            if (d != 0) return d > 0
        }
        return false
    }

    fun dir(ctx: Context): File = File(ctx.filesDir, "updates").apply { mkdirs() }

    private fun friendly(e: Exception): String = when {
        e is UpdateError -> e.message ?: ""
        e is HttpError && e.code in setOf(403, 429) -> "업데이트 서버가 잠시 바빠요. 나중에 다시 확인할게요."
        e is HttpError -> "업데이트 정보를 가져오지 못했어요. (HTTP ${e.code})"
        e is IOException -> "인터넷에 연결되어 있지 않아 업데이트를 확인하지 못했어요."
        else -> "업데이트를 확인하지 못했어요. ($e)"
    }

    private class HttpError(val code: Int) : IOException("HTTP $code")

    private fun checkHost(url: String) {
        val host = url.toHttpUrlOrNull()?.host?.lowercase() ?: ""
        if (ALLOWED_HOSTS.none { host == it || host.endsWith(".$it") }) throw UpdateError("알 수 없는 주소라서 받지 않았어요.")
    }

    private fun open(url: String, accept: String = "*/*") =
        Online.http.newCall(Request.Builder().url(url).header("User-Agent", UA).header("Accept", accept).build()).execute().also {
            if (!it.isSuccessful) {
                it.close(); throw HttpError(it.code)
            }
        }

    /** 새 버전이 있으면 UpdateInfo, 없으면 null (작업 스레드에서) */
    fun check(current: String = BuildConfig.VERSION_NAME): UpdateInfo? {
        val data = try {
            open(RELEASES_API, "application/vnd.github+json").use { JSONArray(it.body?.string() ?: "[]") }
        } catch (e: Exception) {
            throw UpdateError(friendly(e))
        }
        var best: UpdateInfo? = null
        for (i in 0 until data.length()) {
            val rel = data.optJSONObject(i) ?: continue
            if (rel.optBoolean("draft") || rel.optBoolean("prerelease")) continue
            val assets = rel.optJSONArray("assets") ?: continue
            val list = List(assets.length()) { assets.getJSONObject(it) }
            val byName = list.associateBy { it.optString("name") }
            for (a in list) {
                val m = ASSET_RE.matchEntire(a.optString("name")) ?: continue
                val ver = m.groupValues[1]
                if (best != null && !isNewer(ver, best.version)) continue
                val digest = a.optString("digest")
                val side = byName[a.getString("name") + ".sha256"]
                best = UpdateInfo(
                    version = ver,
                    title = rel.optString("name").ifEmpty { ver },
                    notes = if (rel.isNull("body")) "" else rel.optString("body"),
                    pageUrl = rel.optString("html_url").ifEmpty { RELEASES_PAGE },
                    assetName = a.getString("name"),
                    assetUrl = a.optString("browser_download_url"),
                    size = a.optLong("size"),
                    sha256 = if (digest.startsWith("sha256:")) digest.substringAfter(":").lowercase() else null,
                    shaUrl = side?.optString("browser_download_url"),
                )
            }
        }
        return best?.takeIf { isNewer(it.version, current) }
    }

    private fun sha256(f: File): String {
        val md = MessageDigest.getInstance("SHA-256")
        f.inputStream().use { s ->
            val buf = ByteArray(1 shl 16)
            while (true) {
                val n = s.read(buf)
                if (n < 0) break
                md.update(buf, 0, n)
            }
        }
        return md.digest().joinToString("") { "%02x".format(it) }
    }

    /** APK 를 받아 SHA-256 을 확인한 뒤 파일을 돌려준다 */
    fun download(ctx: Context, info: UpdateInfo, progress: (Float) -> Unit = {}, cancelled: () -> Boolean = { false }): File {
        checkHost(info.assetUrl)
        var expected = info.sha256
        if (expected == null && info.shaUrl != null) {
            checkHost(info.shaUrl)
            expected = try {
                open(info.shaUrl).use { r -> Regex("\\b([0-9a-fA-F]{64})\\b").find(r.body?.string()?.take(4096) ?: "")?.groupValues?.get(1)?.lowercase() }
            } catch (e: Exception) {
                throw UpdateError(friendly(e))
            }
        }
        if (expected == null) throw UpdateError("설치 파일을 확인할 값(SHA-256)이 없어서 받지 않았어요.")

        val dst = File(dir(ctx), File(info.assetName).name)
        if (dst.exists() && sha256(dst) == expected) {
            progress(1f)
            return dst
        }
        val part = File(dst.path + ".part")
        val md = MessageDigest.getInstance("SHA-256")
        try {
            open(info.assetUrl).use { r ->
                val body = r.body ?: throw UpdateError("받은 파일이 비어 있어요.")
                val total = body.contentLength().takeIf { it > 0 } ?: info.size
                var done = 0L
                body.byteStream().use { input ->
                    part.outputStream().use { out ->
                        val buf = ByteArray(1 shl 18)
                        while (true) {
                            if (cancelled()) throw UpdateError("취소했어요.")
                            val n = input.read(buf)
                            if (n < 0) break
                            out.write(buf, 0, n)
                            md.update(buf, 0, n)
                            done += n
                            if (total > 0) progress(minOf(0.99f, done.toFloat() / total))
                        }
                    }
                }
            }
        } catch (e: Exception) {
            part.delete()
            throw if (e is UpdateError) e else UpdateError(friendly(e))
        }
        if (md.digest().joinToString("") { "%02x".format(it) } != expected) {
            part.delete()
            throw UpdateError("받은 파일이 올바르지 않아요. 다음에 다시 받을게요.")
        }
        dst.delete()
        if (!part.renameTo(dst)) throw UpdateError("받은 파일을 저장하지 못했어요.")
        progress(1f)
        return dst
    }

    /** 지난 설치 파일 정리 */
    fun cleanup(ctx: Context, keep: File? = null) {
        dir(ctx).listFiles()?.forEach { if (it.name != keep?.name) it.delete() }
    }

    /** 이 앱이 APK 를 설치해도 되는지 ('출처를 알 수 없는 앱 설치' 허용) */
    fun canInstall(ctx: Context): Boolean = ctx.packageManager.canRequestPackageInstalls()

    fun openInstallPermission(ctx: Context) {
        ctx.startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:${ctx.packageName}"))
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    }

    /** 안드로이드 설치기로 설치한다. 묻지 않고 설치할 수 있으면 그대로, 아니면 설치 확인 창이 뜬다 (InstallReceiver) */
    fun install(ctx: Context, apk: File) {
        val pi = ctx.packageManager.packageInstaller
        val params = PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL).apply {
            setAppPackageName(ctx.packageName)
            if (Build.VERSION.SDK_INT >= 31) setRequireUserAction(PackageInstaller.SessionParams.USER_ACTION_NOT_REQUIRED)
        }
        val id = pi.createSession(params)
        pi.openSession(id).use { s ->
            s.openWrite("app.apk", 0, apk.length()).use { out ->
                apk.inputStream().use { it.copyTo(out) }
                s.fsync(out)
            }
            val cb = PendingIntent.getBroadcast(ctx, id, Intent(ctx, InstallReceiver::class.java),
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_MUTABLE)
            s.commit(cb.intentSender)
        }
    }

    /** 릴리스 노트(마크다운)를 창에 보여 줄 평문으로 */
    fun notesToText(md: String, maxLines: Int = 14): String {
        val out = md.lines().map { it.trim() }.filter { it.isNotEmpty() }.map {
            it.replace(Regex("^#+\\s*"), "").replace(Regex("^[-*]\\s+"), "· ").replace(Regex("\\*\\*(.+?)\\*\\*"), "$1")
                .replace(Regex("`([^`]+)`"), "$1").replace(Regex("\\[([^\\]]+)\\]\\([^)]+\\)"), "$1")
        }
        return (if (out.size > maxLines) out.take(maxLines) + "…" else out).joinToString("\n")
    }
}

/** 설치기 결과: 확인이 필요하면 확인 창을 띄우고, 실패하면 알린다 */
class InstallReceiver : BroadcastReceiver() {
    override fun onReceive(ctx: Context, intent: Intent) {
        when (val st = intent.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE)) {
            PackageInstaller.STATUS_PENDING_USER_ACTION -> {
                @Suppress("DEPRECATION")
                val confirm = intent.getParcelableExtra<Intent>(Intent.EXTRA_INTENT) ?: return
                try {
                    ctx.startActivity(confirm.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                } catch (_: Exception) {
                    Updates.installFailed("설치 확인 창을 열지 못했어요. 설정에서 ‘업데이트’를 다시 눌러 주세요.")
                }
            }
            PackageInstaller.STATUS_SUCCESS -> {}
            else -> Updates.installFailed(when (st) {
                PackageInstaller.STATUS_FAILURE_ABORTED -> "설치를 취소했어요."
                PackageInstaller.STATUS_FAILURE_CONFLICT, PackageInstaller.STATUS_FAILURE_INCOMPATIBLE ->
                    "지금 앱과 서명이 달라서 설치할 수 없어요. 앱을 지우고 새 버전을 설치해 주세요."
                PackageInstaller.STATUS_FAILURE_STORAGE -> "저장 공간이 부족해서 설치하지 못했어요."
                else -> "설치하지 못했어요. (${intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE) ?: st})"
            })
        }
    }
}

/** 지금 업데이트 상태 */
data class UpdState(
    val state: String = "idle",         // idle | checking | latest | available | downloading | ready | installing | error
    val info: UpdateInfo? = null,
    val progress: Float = 0f,
    val message: String = "",
    val lastCheck: LocalDateTime? = null,
)

/**
 * 업데이트 흐름 관리 (데스크톱 app/ui/update_manager.py): 확인 → 받기 → 종이 멀었을 때 설치.
 * 안드로이드는 앱이 떠 있을 때만 확인한다 (앱을 열 때, 6시간마다).
 */
object Updates {
    private const val CHECK_EVERY_MIN = 6 * 60L
    const val SAFE_GAP_MIN = 10  // 다음 종까지 이 시간 이상 남았을 때만 자동 설치

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private val _state = MutableStateFlow(UpdState())
    val state: StateFlow<UpdState> = _state
    private var path: File? = null
    private var manual = false
    private var installAfter = false
    private var dlJob: Job? = null
    private var safeJob: Job? = null
    private var nagged = false

    fun auto(repo: Repo): Boolean = repo.setting("update_auto", "1") == "1"

    fun setAuto(ctx: Context, on: Boolean) {
        val repo = Repo(ctx)
        repo.setSetting("update_auto", if (on) "1" else "0")
        val s = _state.value.state
        if (on && s == "available") download(ctx)
        else if (on && s == "ready") startSafeTimer(ctx)
        else if (!on) safeJob?.cancel()
        _state.value = _state.value.copy()
    }

    private fun set(state: String, message: String = "") {
        _state.value = _state.value.copy(state = state, message = message)
    }

    /** 앱 화면을 열 때: 자동 업데이트가 켜져 있으면 6시간마다 확인한다 */
    fun onAppVisible(ctx: Context) {
        val repo = Repo(ctx)
        val last = repo.setting("update_last_check", "").toLongOrNull() ?: 0L
        if (System.currentTimeMillis() - last >= CHECK_EVERY_MIN * 60_000) check(ctx, manual = false)
        else if (_state.value.state == "ready" && auto(repo)) tryAutoInstall(ctx)
    }

    // ---------- 확인 ----------
    fun check(ctx: Context, manual: Boolean = true) {
        if (_state.value.state in setOf("checking", "downloading", "installing")) return
        val app = ctx.applicationContext
        this.manual = manual
        set("checking")
        scope.launch {
            val repo = Repo(app)
            try {
                val info = withContext(Dispatchers.IO) { Updater.check() }
                repo.setSetting("update_last_check", System.currentTimeMillis().toString())
                _state.value = _state.value.copy(lastCheck = LocalDateTime.now())
                if (info == null) {
                    _state.value = _state.value.copy(info = null)
                    set("latest")
                    if (manual) Toasts.show("최신 버전을 쓰고 있어요", "success")
                    return@launch
                }
                _state.value = _state.value.copy(info = info)
                set("available")
                if (repo.setting("update_notified", "") != info.version || manual) {
                    repo.setSetting("update_notified", info.version)
                    if (!auto(repo)) Toasts.show("새 버전 ${info.version}이 나왔어요. 설정에서 업데이트할 수 있어요.")
                }
                if (auto(repo)) download(app)
            } catch (e: Exception) {
                _state.value = _state.value.copy(lastCheck = LocalDateTime.now())
                if (_state.value.info != null) {
                    set("available"); return@launch
                }
                val msg = e.message ?: "업데이트를 확인하지 못했어요."
                set(if (manual) "error" else "idle", msg)
                if (manual) Toasts.show(msg, "warning")
            }
        }
    }

    // ---------- 받기 ----------
    fun download(ctx: Context) {
        val info = _state.value.info ?: return
        if (dlJob?.isActive == true) return
        val app = ctx.applicationContext
        _state.value = _state.value.copy(progress = 0f)
        set("downloading")
        dlJob = scope.launch {
            try {
                val f = withContext(Dispatchers.IO) {
                    Updater.download(app, info, { p -> _state.value = _state.value.copy(progress = p) }, { !isActive })
                }
                path = f
                withContext(Dispatchers.IO) { Updater.cleanup(app, keep = f) }
                set("ready")
                if (installAfter) {
                    installAfter = false
                    installNow(app)
                } else if (auto(Repo(app))) {
                    startSafeTimer(app)
                }
            } catch (e: Exception) {
                installAfter = false
                val msg = e.message ?: "받지 못했어요."
                set("available", msg)
                if (manual) Toasts.show(msg, "warning")
            }
        }
    }

    // ---------- 설치 ----------
    /** 종을 울리는 중이 아니고, 교실 화면에 시계를 띄워 두지 않았고, 다음 종까지 충분히 남았는지 */
    fun isSafeNow(ctx: Context): Boolean {
        if (BellService.ringing.value != null || FullscreenActivity.showing) return false
        val next = Scheduler.next(Repo(ctx)) ?: return true
        return Duration.between(LocalDateTime.now(), next.runAt).toMinutes() >= SAFE_GAP_MIN
    }

    private fun startSafeTimer(ctx: Context) {
        safeJob?.cancel()
        safeJob = scope.launch {
            while (isActive && _state.value.state == "ready") {
                tryAutoInstall(ctx)
                delay(30_000)
            }
        }
    }

    private fun tryAutoInstall(ctx: Context) {
        val info = _state.value.info ?: return
        if (_state.value.state != "ready" || !auto(Repo(ctx)) || !isSafeNow(ctx)) return
        if (!Updater.canInstall(ctx)) {
            if (!nagged) {
                nagged = true
                Toasts.show("새 버전 ${info.version}이 준비됐어요. 설치하려면 허용이 필요해요.", "info", "지금 설치") { installNow(ctx) }
            }
            return
        }
        safeJob?.cancel()
        Toasts.show("${info.version} 버전으로 업데이트할게요. 잠깐 꺼졌다 다시 켜져요.")
        scope.launch {
            delay(5000)
            doInstall(ctx)
        }
    }

    /** 설정 화면의 '업데이트' 버튼 */
    fun installNow(ctx: Context) {
        when (_state.value.state) {
            "available" -> {
                installAfter = true
                manual = true
                download(ctx)
            }
            "ready" -> {
                if (!Updater.canInstall(ctx)) {
                    Toasts.show("‘이 출처 허용’을 켠 뒤 다시 눌러 주세요")
                    Updater.openInstallPermission(ctx)
                    return
                }
                doInstall(ctx)
            }
        }
    }

    private fun doInstall(ctx: Context) {
        val info = _state.value.info ?: return
        val apk = path ?: return
        val repo = Repo(ctx)
        repo.setSetting("update_pending_version", info.version)
        repo.setSetting("update_pending_notes", info.notes.take(4000))
        try {
            Updater.install(ctx.applicationContext, apk)
            set("installing")
        } catch (e: Exception) {
            set("ready", "설치를 시작하지 못했어요: ${e.message}")
            Toasts.show("설치를 시작하지 못했어요: ${e.message}", "error")
        }
    }

    fun installFailed(message: String) {
        scope.launch {
            set(if (path != null) "ready" else "available", message)
            Toasts.show(message, "warning")
        }
    }

    // ---------- 업데이트 직후 ----------
    /** 방금 업데이트됐다면 (버전, 노트)를 돌려주고 기록을 지운다 */
    fun takeWhatsNew(repo: Repo): Pair<String, String>? {
        val pending = repo.setting("update_pending_version", "")
        if (pending.isEmpty()) return null
        val notes = repo.setting("update_pending_notes", "")
        repo.setSetting("update_pending_version", "")
        repo.setSetting("update_pending_notes", "")
        return if (Updater.parseVersion(pending) == Updater.parseVersion(BuildConfig.VERSION_NAME)) pending to notes else null
    }

    fun statusText(s: UpdState, auto: Boolean): String = when (s.state) {
        "checking" -> "확인하고 있어요"
        "available" -> s.message.ifEmpty { "새 버전 ${s.info?.version}이 나왔어요" }
        "downloading" -> "${s.info?.version} 받는 중 ${(s.progress * 100).toInt()}%"
        "ready" -> s.message.ifEmpty {
            if (auto) "${s.info?.version} 설치 준비 완료 · 다음 종까지 ${SAFE_GAP_MIN}분 넘게 남으면 설치해요" else "${s.info?.version} 설치 준비 완료"
        }
        "installing" -> "설치를 시작했어요"
        "latest" -> "최신 버전이에요 · ${s.lastCheck?.format(DateTimeFormatter.ofPattern("HH:mm")) ?: ""}에 확인"
        "error" -> s.message
        else -> "아직 확인하지 않았어요"
    }
}

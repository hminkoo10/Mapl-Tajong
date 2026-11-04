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
import okhttp3.OkHttpClient
import okhttp3.Request
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
)

/**
 * 자동 업데이트 (데스크톱 app/core/updater.py 와 같은 흐름).
 * 로그인한 마고에듀 서버의 안드로이드 카탈로그에서 APK 를 찾아 받고(SHA-256 확인), 안드로이드 설치기로 설치한다.
 * GitHub 조회·비공개 저장소 인증은 서버가 맡는다.
 */
object Updater {
    private const val APP_ID = "tajong-android" // 동기화용 CloudModel.APP_ID(tajong)와 다름
    private val SHA_RE = Regex("[0-9a-fA-F]{64}")
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
        e is HttpError && e.code == 401 -> "클라우드 로그인이 끝났어요. 다시 로그인한 뒤 업데이트해 주세요."
        e is HttpError && e.code == 403 -> "이 계정에는 안드로이드 앱을 받을 권한이 없어요. 관리자에게 문의해 주세요."
        e is HttpError && e.code == 404 -> "서버에서 이 버전을 찾지 못했어요. 업데이트를 다시 확인해 주세요."
        e is HttpError && e.code in setOf(429, 503) -> "업데이트 서버가 잠시 바빠요. 나중에 다시 확인할게요."
        e is HttpError -> "새 버전을 받지 못했어요. 인터넷 연결을 확인하고 다시 해 주세요. (HTTP ${e.code})"
        e is IOException -> "마고에듀 서버에 연결하지 못했어요. 서버 주소와 인터넷 연결을 확인한 뒤 다시 시도해 주세요."
        else -> "서버의 업데이트 정보를 읽지 못했어요. 잠시 뒤 다시 확인해 주세요."
    }

    private class HttpError(val code: Int) : IOException("HTTP $code")

    private fun requireCredentials(value: Pair<String, String>?): Pair<String, String> {
        if (value == null || value.second.isBlank()) throw UpdateError("마고에듀 통합 클라우드에 로그인한 뒤 업데이트를 확인해 주세요.")
        return value.first.trimEnd('/') to value.second
    }

    private fun open(url: String, server: String, token: String, http: OkHttpClient, accept: String = "*/*"): okhttp3.Response {
        val base = server.toHttpUrlOrNull() ?: throw UpdateError("클라우드 서버 주소가 올바르지 않아요.")
        val target = url.toHttpUrlOrNull() ?: throw UpdateError("업데이트 주소가 올바르지 않아요.")
        if (target.scheme != base.scheme || target.host != base.host || target.port != base.port) {
            throw UpdateError("클라우드 서버가 바뀌었어요. 업데이트를 다시 확인해 주세요.")
        }
        // 공개 파일은 서버가 302로 보낼 수 있다. OkHttp는 다른 origin으로 넘어갈 때 Authorization을 제거한다.
        // HTTPS → HTTP 전환과 GitHub API 호출은 허용하지 않는다.
        val client = http.newBuilder().followRedirects(true).followSslRedirects(false).addNetworkInterceptor { chain ->
            if (chain.request().url.host == "api.github.com") throw IOException("GitHub API는 서버에서만 호출해요.")
            chain.proceed(chain.request())
        }.build()
        return client.newCall(Request.Builder().url(target).header("User-Agent", UA).header("Accept", accept)
            .header("Authorization", "Bearer $token").build()).execute().also {
            if (!it.isSuccessful) {
                it.close(); throw HttpError(it.code)
            }
        }
    }

    /** 새 버전이 있으면 UpdateInfo, 없으면 null (작업 스레드에서) */
    fun check(current: String = BuildConfig.VERSION_NAME): UpdateInfo? = check(current, Cloud.credentials(), CloudApi.http)

    internal fun check(current: String, credentials: Pair<String, String>?, http: OkHttpClient): UpdateInfo? {
        val (server, token) = requireCredentials(credentials)
        try {
            val data = open("$server/api/apps", server, token, http, "application/json").use {
                Json.parse(it.body?.string().orEmpty()).jObj()
            } ?: throw UpdateError("서버의 업데이트 정보를 읽지 못했어요.")
            val apps = data["apps"] as? List<*> ?: throw UpdateError("서버의 앱 목록을 읽지 못했어요.")
            val app = apps.mapNotNull { it.jObj() }.firstOrNull {
                it["id"] == APP_ID && it["platform"] == "android" && it["allowed"] != false
            } ?: throw UpdateError("서버에서 안드로이드 타종 앱을 찾지 못했어요. 앱 등록과 사용 권한을 확인해 주세요.")
            val rel = app["release"].jObj() ?: throw UpdateError("서버에 배포된 안드로이드 버전이 아직 없어요.")
            val version = rel["version"].jStr().orEmpty()
            val fileName = rel["fileName"].jStr().orEmpty()
            if (!Regex("""\d+(?:\.\d+){1,3}""").matches(version) ||
                !Regex("""[^/\\]+\.apk""", RegexOption.IGNORE_CASE).matches(fileName)) {
                throw UpdateError("서버의 안드로이드 업데이트 정보가 올바르지 않아요.")
            }
            if (!isNewer(version, current)) return null
            return UpdateInfo(
                version = version,
                title = version,
                notes = rel["notes"].jStr().orEmpty(),
                pageUrl = "$server/",
                assetName = fileName,
                assetUrl = "$server/api/apps/$APP_ID/download?version=${CloudApi.enc(version)}",
                size = (rel["size"].jLong() ?: 0L).coerceAtLeast(0),
                sha256 = rel["sha256"].jStr()?.takeIf { SHA_RE.matches(it) }?.lowercase(),
            )
        } catch (e: Exception) {
            throw UpdateError(friendly(e))
        }
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
    fun download(ctx: Context, info: UpdateInfo, progress: (Float) -> Unit = {}, cancelled: () -> Boolean = { false }): File =
        download(dir(ctx), info, Cloud.credentials(), CloudApi.http, progress, cancelled)

    internal fun download(directory: File, info: UpdateInfo, credentials: Pair<String, String>?, http: OkHttpClient,
                          progress: (Float) -> Unit = {}, cancelled: () -> Boolean = { false }): File {
        val (server, token) = requireCredentials(credentials)
        val expected = info.sha256?.takeIf { SHA_RE.matches(it) }?.lowercase()
            ?: throw UpdateError("새 버전을 안전하게 받을 수 있는지 확인하지 못했어요. 원장님이나 운영자에게 알려 주세요. (SHA-256 없음)")

        val dst = File(directory, File(info.assetName).name)
        if (dst.exists() && sha256(dst) == expected) {
            progress(1f)
            return dst
        }
        val part = File(dst.path + ".part")
        val md = MessageDigest.getInstance("SHA-256")
        try {
            open(info.assetUrl, server, token, http).use { r ->
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
                val msg = e.message ?: "업데이트를 확인하지 못했어요."
                if (_state.value.info != null) {
                    set("available", msg)
                } else {
                    set(if (manual) "error" else "idle", msg)
                }
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
        // 로그아웃했거나 이 기기에서 종을 울리지 않으면 기다릴 종이 없다
        val repo = Repo(ctx)
        if (!Cloud.ringsHere(repo)) return true
        val next = Scheduler.next(repo) ?: return true
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
        Toasts.show("${info.version} 버전으로 업데이트할게요. 앱이 닫혀도 종은 그대로 울려요.")
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

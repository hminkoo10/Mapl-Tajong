package com.milky.mataf.core

import android.net.Uri
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import okhttp3.OkHttpClient
import okhttp3.RequestBody.Companion.toRequestBody
import org.schabi.newpipe.extractor.MediaFormat
import org.schabi.newpipe.extractor.NewPipe
import org.schabi.newpipe.extractor.ServiceList
import org.schabi.newpipe.extractor.StreamingService
import org.schabi.newpipe.extractor.downloader.Downloader
import org.schabi.newpipe.extractor.downloader.Request
import org.schabi.newpipe.extractor.downloader.Response
import org.schabi.newpipe.extractor.exceptions.ReCaptchaException
import org.schabi.newpipe.extractor.localization.ContentCountry
import org.schabi.newpipe.extractor.localization.Localization
import org.schabi.newpipe.extractor.search.SearchInfo
import org.schabi.newpipe.extractor.stream.AudioStream
import org.schabi.newpipe.extractor.stream.DeliveryMethod
import org.schabi.newpipe.extractor.stream.StreamInfo
import org.schabi.newpipe.extractor.stream.StreamInfoItem
import java.io.File
import java.io.IOException
import java.util.concurrent.TimeUnit
import kotlin.math.abs

/** 검색 결과 한 줄 */
data class Found(
    val url: String,
    val title: String,
    val channel: String,
    val durationSec: Long,
    val thumb: String?,
)

/** 받을 소리의 실제 주소 */
data class AudioSource(
    val url: String,
    val ext: String,
    val hls: Boolean,
    val bitrate: Int,
    val title: String,
    val durationSec: Long,
    val length: Long,
)

class OnlineError(message: String) : Exception(message)

/**
 * YouTube·SoundCloud 검색과 소리 받기 (로그인 없이, NewPipe 앱이 쓰는 NewPipeExtractor 로).
 * 데스크톱(app/core/youtube.py)과 같은 흐름: 검색 → 앞부분 미리 듣기 → 받기.
 */
object Online {
    const val YOUTUBE = "youtube"
    const val SOUNDCLOUD = "soundcloud"
    val SOURCES = listOf(YOUTUBE, SOUNDCLOUD)
    private const val UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0"
    private const val CHUNK = 1L shl 20

    val http: OkHttpClient by lazy {
        OkHttpClient.Builder()
            .connectTimeout(15, TimeUnit.SECONDS)
            .readTimeout(30, TimeUnit.SECONDS)
            .followRedirects(true)
            .build()
    }

    @Volatile private var ready = false

    private fun init() {
        if (ready) return
        synchronized(this) {
            if (!ready) {
                NewPipe.init(Fetcher(http), Localization("ko", "KR"), ContentCountry("KR"))
                ready = true
            }
        }
    }

    private fun service(source: String): StreamingService =
        if (source == SOUNDCLOUD) ServiceList.SoundCloud else ServiceList.YouTube

    fun sourceOf(url: String): String = if ("soundcloud.com" in url) SOUNDCLOUD else YOUTUBE

    /** 검색어(또는 주소)로 찾기. 느리므로 IO 스레드에서 부른다. */
    fun search(query: String, source: String, limit: Int = 24): List<Found> = guard {
        init()
        val q = query.trim()
        if (q.startsWith("http://") || q.startsWith("https://")) {
            val svc = NewPipe.getServiceByUrl(q)
            val info = StreamInfo.getInfo(svc, q)
            return@guard listOf(Found(info.url, info.name, info.uploaderName ?: "", info.duration,
                pickThumb(info.thumbnails.map { it.url to it.height })))
        }
        val svc = service(source)
        val filter = if (source == SOUNDCLOUD) "tracks" else "videos"
        val handler = svc.searchQHFactory.fromQuery(q, listOf(filter), "")
        val info = SearchInfo.getInfo(svc, handler)
        info.relatedItems.filterIsInstance<StreamInfoItem>()
            .filter { it.url.isNotBlank() }
            .take(limit)
            .map { Found(it.url, it.name ?: "", it.uploaderName ?: "", it.duration, pickThumb(it.thumbnails.map { t -> t.url to t.height })) }
    }

    private fun pickThumb(list: List<Pair<String, Int>>): String? =
        list.filter { it.first.isNotBlank() }.minByOrNull { (_, h) -> if (h <= 0) 9999 else abs(h - 200) }?.first

    /** 영상/곡 주소 → 소리만 있는 스트림 주소 */
    fun resolve(url: String): AudioSource = guard {
        init()
        val svc = NewPipe.getServiceByUrl(url)
        val info = StreamInfo.getInfo(svc, url)
        val streams: List<AudioStream> = info.audioStreams.filter { it.isUrl && it.content.isNotBlank() }
        val prog = streams.filter { it.deliveryMethod == DeliveryMethod.PROGRESSIVE_HTTP }
            .sortedWith(compareByDescending<AudioStream> { it.format == MediaFormat.M4A }
                .thenByDescending { it.format == MediaFormat.MP3 }
                .thenByDescending { it.averageBitrate })
        val hls = streams.filter { it.deliveryMethod == DeliveryMethod.HLS }
            .sortedWith(compareByDescending<AudioStream> { it.format == MediaFormat.MP3 }
                .thenByDescending { it.format == MediaFormat.M4A }
                .thenByDescending { it.averageBitrate })
        val s = prog.firstOrNull() ?: hls.firstOrNull() ?: throw OnlineError("받을 수 있는 소리를 찾지 못했어요.")
        val isHls = s.deliveryMethod == DeliveryMethod.HLS
        val ext = s.format?.suffix?.lowercase()?.let { if (it == "webma") "webm" else it } ?: if (isHls) "mp3" else "m4a"
        val clen = Uri.parse(s.content).getQueryParameter("clen")?.toLongOrNull() ?: -1L
        AudioSource(s.content, ext, isHls, s.averageBitrate, info.name ?: "", info.duration, clen)
    }

    /**
     * 받기. maxSeconds 를 주면 앞부분만(미리 듣기용) 받는다.
     * progress(0..1) 는 받는 동안 여러 번 불린다.
     */
    suspend fun download(src: AudioSource, out: File, maxSeconds: Int? = null, progress: (Float) -> Unit = {}): File {
        out.parentFile?.mkdirs()
        try {
            if (src.hls) downloadHls(src, out, maxSeconds, progress) else downloadRanged(src, out, maxSeconds, progress)
        } catch (e: OnlineError) {
            out.delete(); throw e
        } catch (e: IOException) {
            out.delete(); throw OnlineError("인터넷 연결을 확인해 주세요.")
        } catch (e: Exception) {
            out.delete(); throw e
        }
        if (out.length() < 1024) {
            out.delete(); throw OnlineError("소리를 받지 못했어요.")
        }
        return out
    }

    private fun headersFor(url: String): Map<String, String> {
        val c = Uri.parse(url).getQueryParameter("c")?.uppercase() ?: ""
        return when {
            c.startsWith("ANDROID") -> mapOf("User-Agent" to "com.google.android.youtube/19.28.35 (Linux; U; Android 14; KR) gzip")
            c.startsWith("IOS") -> mapOf("User-Agent" to "com.google.ios.youtube/19.28.1 (iPhone16,2; U; CPU iOS 17_5_1 like Mac OS X; ko_KR)")
            "googlevideo.com" in url -> mapOf("User-Agent" to UA, "Origin" to "https://www.youtube.com", "Referer" to "https://www.youtube.com/")
            else -> mapOf("User-Agent" to UA)
        }
    }

    private suspend fun downloadRanged(src: AudioSource, out: File, maxSeconds: Int?, progress: (Float) -> Unit) {
        val headers = headersFor(src.url)
        val limit = if (maxSeconds != null) {
            val kbps = if (src.bitrate > 0) src.bitrate else 160_000
            // 비트레이트 단위가 bps/kbps 어느 쪽이든 넉넉하게
            val bps = if (kbps < 2000) kbps * 1000 else kbps
            (bps / 8L * (maxSeconds + 4)).coerceIn(256L * 1024, 4L * 1024 * 1024)
        } else Long.MAX_VALUE
        var total = src.length
        var pos = 0L
        out.outputStream().use { os ->
            while (true) {
                currentCoroutineContext().ensureActive()
                val end = minOf(pos + CHUNK, limit) - 1
                val rb = okhttp3.Request.Builder().url(src.url).header("Range", "bytes=$pos-$end")
                headers.forEach { (k, v) -> rb.header(k, v) }
                http.newCall(rb.build()).execute().use { r ->
                    if (r.code == 416) return
                    if (!r.isSuccessful) throw OnlineError(httpMessage(r.code))
                    r.header("Content-Range")?.substringAfter('/')?.toLongOrNull()?.let { total = it }
                    val body = r.body ?: throw OnlineError("소리를 받지 못했어요.")
                    var n = 0L
                    body.byteStream().use { input ->
                        val buf = ByteArray(64 * 1024)
                        while (true) {
                            val k = input.read(buf)
                            if (k < 0) break
                            os.write(buf, 0, k)
                            n += k
                        }
                    }
                    pos += n
                    if (r.code == 200) return   // 서버가 한 번에 다 준 경우
                    if (n == 0L) return
                }
                val goal = minOf(limit, if (total > 0) total else Long.MAX_VALUE)
                if (goal != Long.MAX_VALUE) progress((pos.toFloat() / goal).coerceIn(0f, 1f))
                if (pos >= limit || (total in 1..pos)) return
            }
        }
    }

    private suspend fun downloadHls(src: AudioSource, out: File, maxSeconds: Int?, progress: (Float) -> Unit) {
        val headers = headersFor(src.url)
        var listUrl = src.url
        var text = getText(listUrl, headers)
        // 마스터 목록이면 첫 번째(또는 가장 좋은) 하위 목록으로
        if ("#EXT-X-STREAM-INF" in text) {
            val sub = text.lines().map { it.trim() }.firstOrNull { it.isNotEmpty() && !it.startsWith("#") }
                ?: throw OnlineError("소리 목록을 읽지 못했어요.")
            listUrl = resolveUrl(listUrl, sub)
            text = getText(listUrl, headers)
        }
        val lines = text.lines().map { it.trim() }
        val init = lines.firstOrNull { it.startsWith("#EXT-X-MAP") }?.let {
            Regex("URI=\"([^\"]+)\"").find(it)?.groupValues?.get(1)
        }
        val segs = mutableListOf<Pair<String, Double>>()
        var dur = 0.0
        for (l in lines) {
            if (l.startsWith("#EXTINF:")) dur = l.removePrefix("#EXTINF:").substringBefore(',').toDoubleOrNull() ?: 0.0
            else if (l.isNotEmpty() && !l.startsWith("#")) {
                segs += resolveUrl(listUrl, l) to dur; dur = 0.0
            }
        }
        if (segs.isEmpty()) throw OnlineError("소리 목록이 비어 있어요.")
        val want = if (maxSeconds != null) {
            var acc = 0.0
            var n = 0
            for ((_, d) in segs) {
                n++; acc += d
                if (acc >= maxSeconds + 2) break
            }
            segs.take(maxOf(1, n))
        } else segs
        out.outputStream().use { os ->
            if (init != null) os.write(getBytes(resolveUrl(listUrl, init), headers))
            want.forEachIndexed { i, (u, _) ->
                currentCoroutineContext().ensureActive()
                os.write(getBytes(u, headers))
                progress((i + 1f) / want.size)
            }
        }
    }

    private fun resolveUrl(base: String, rel: String): String =
        if (rel.startsWith("http://") || rel.startsWith("https://")) rel else java.net.URI(base).resolve(rel).toString()

    private fun getText(url: String, headers: Map<String, String>): String = String(getBytes(url, headers), Charsets.UTF_8)

    private fun getBytes(url: String, headers: Map<String, String>): ByteArray {
        val rb = okhttp3.Request.Builder().url(url)
        headers.forEach { (k, v) -> rb.header(k, v) }
        http.newCall(rb.build()).execute().use { r ->
            if (!r.isSuccessful) throw OnlineError(httpMessage(r.code))
            return r.body?.bytes() ?: ByteArray(0)
        }
    }

    private fun httpMessage(code: Int): String = when (code) {
        403 -> "소리 서버가 받기를 거절했어요. 잠시 뒤 다시 해 보세요."
        404, 410 -> "소리 주소가 만료됐어요. 다시 찾아 주세요."
        429 -> "요청이 너무 많아 잠깐 막혔어요. 잠시 뒤 다시 해 보세요."
        else -> "소리를 받지 못했어요 (HTTP $code)."
    }

    /** 라이브러리 오류를 알아듣기 쉬운 말로 */
    private inline fun <T> guard(block: () -> T): T = try {
        block()
    } catch (e: OnlineError) {
        throw e
    } catch (e: IOException) {
        throw OnlineError("인터넷 연결을 확인해 주세요.")
    } catch (e: Exception) {
        throw OnlineError(explain(e))
    }

    fun explain(e: Throwable): String {
        if (e is OnlineError) return e.message ?: "실패했어요."
        val n = e::class.java.simpleName
        return when {
            e is ReCaptchaException || "NotBot" in n -> "YouTube가 잠깐 막았어요. 잠시 뒤 다시 하거나 SoundCloud에서 찾아 보세요."
            "AgeRestricted" in n -> "연령 제한이 있어 받을 수 없어요."
            "GeographicRestriction" in n -> "이 지역에서는 볼 수 없어요."
            "Private" in n -> "비공개라 받을 수 없어요."
            "Paid" in n || "SoundCloudGoPlus" in n -> "유료 콘텐츠라 받을 수 없어요."
            "ContentNotAvailable" in n || "ContentNotSupported" in n -> "볼 수 없는 영상(곡)이에요."
            "ParsingException" in n || "Extraction" in n -> "이 영상(곡)의 정보를 읽지 못했어요. 앱을 업데이트하면 고쳐질 수 있어요."
            e is IOException -> "인터넷 연결을 확인해 주세요."
            else -> "실패했어요: ${e.message ?: n}"
        }
    }

    /** NewPipeExtractor 가 인터넷에 접근할 때 쓰는 통로 */
    private class Fetcher(private val client: OkHttpClient) : Downloader() {
        override fun execute(request: Request): Response {
            val method = request.httpMethod()
            val data = request.dataToSend()
            val body = when {
                data != null -> data.toRequestBody()
                method in setOf("POST", "PUT", "PATCH") -> ByteArray(0).toRequestBody()
                else -> null
            }
            val rb = okhttp3.Request.Builder().url(request.url()).method(method, body).header("User-Agent", UA)
            request.headers().forEach { (k, vs) ->
                rb.removeHeader(k)
                vs.forEach { rb.addHeader(k, it) }
            }
            client.newCall(rb.build()).execute().use { r ->
                if (r.code == 429) throw ReCaptchaException("reCaptcha Challenge requested", request.url())
                return Response(r.code, r.message, r.headers.toMultimap(), r.body?.string(), r.request.url.toString())
            }
        }
    }
}

package com.milky.mataf.core

import android.content.Context
import androidx.javascriptengine.JavaScriptSandbox
import okhttp3.OkHttpClient
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.concurrent.TimeUnit

/**
 * YouTube 소리 주소의 n 값·서명 풀기.
 * yt-dlp 가 쓰는 풀이 스크립트(yt-dlp/ejs 0.8.0, Unlicense — assets/ejs, SHA3-512 를 yt-dlp 목록과 맞춰 둠)를
 * 휴대폰의 JavaScript 엔진(JavaScriptSandbox, 인터넷·화면과 떨어진 V8)에서 돌린다. 데스크톱은 같은 스크립트를 deno 로 돌린다.
 */
object JsChallenge {
    private const val UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0"

    class Result(val n: Map<String, String>, val sig: Map<String, String>)

    /** 지금 YouTube 플레이어 번호 (서명 시각 signatureTimestamp 와 같은 플레이어여야 한다) */
    fun playerId(http: OkHttpClient): String {
        val text = get(http, "https://www.youtube.com/iframe_api").replace("\\/", "/")
        return Regex("""/s/player/([A-Za-z0-9_-]+)/""").find(text)?.groupValues?.get(1)
            ?: throw OnlineError("YouTube 플레이어 정보를 찾지 못했어요.")
    }

    /** 플레이어 분석에 메모리를 많이 쓰므로 한 번에 하나씩 */
    @Synchronized
    fun solve(ctx: Context, http: OkHttpClient, n: List<String>, sig: List<String>): Result {
        val id = playerId(http)
        val dir = File(ctx.filesDir, "ejs").apply { mkdirs() }
        val cache = File(dir, "$id.js")   // 한 번 분석한 플레이어 (다음부터 빠르게)
        val requests = JSONArray()
        if (n.isNotEmpty()) requests.put(JSONObject().put("type", "n").put("challenges", JSONArray(n)))
        if (sig.isNotEmpty()) requests.put(JSONObject().put("type", "sig").put("challenges", JSONArray(sig)))
        val input = if (cache.exists()) {
            JSONObject().put("type", "preprocessed").put("preprocessed_player", cache.readText()).put("requests", requests)
        } else {
            val player = get(http, "https://www.youtube.com/s/player/$id/player_ias.vflset/en_US/base.js")
            JSONObject().put("type", "player").put("player", player).put("requests", requests).put("output_preprocessed", true)
        }
        val lib = ctx.assets.open("ejs/yt.solver.lib.min.js").bufferedReader().use { it.readText() }
        val core = ctx.assets.open("ejs/yt.solver.core.min.js").bufferedReader().use { it.readText() }
        val code = "$lib\nObject.assign(globalThis, lib);\n$core\nJSON.stringify(jsc($input));"

        val out = JSONObject(run(ctx, code))
        if (out.optString("type") == "error") throw OnlineError("소리 주소를 풀지 못했어요: ${out.optString("error")}")
        out.optString("preprocessed_player").takeIf { it.isNotEmpty() }?.let { p ->
            dir.listFiles()?.forEach { it.delete() }
            cache.writeText(p)
        }
        val responses = out.optJSONArray("responses") ?: JSONArray()
        val maps = (0 until responses.length()).map { i ->
            val r = responses.getJSONObject(i)
            if (r.optString("type") == "error") throw OnlineError("소리 주소를 풀지 못했어요: ${r.optString("error")}")
            val data = r.optJSONObject("data") ?: JSONObject()
            data.keys().asSequence().associateWith { data.getString(it) }
        }
        var k = 0
        val nMap = if (n.isNotEmpty()) maps[k++] else emptyMap()
        val sigMap = if (sig.isNotEmpty()) maps[k] else emptyMap()
        return Result(nMap, sigMap)
    }

    private fun run(ctx: Context, code: String): String {
        if (!JavaScriptSandbox.isSupported()) throw OnlineError("이 기기에서는 YouTube 주소를 풀 수 없어요. Android System WebView를 업데이트해 주세요.")
        JavaScriptSandbox.createConnectedInstanceAsync(ctx.applicationContext).get(10, TimeUnit.SECONDS).use { box ->
            if (!box.isFeatureSupported(JavaScriptSandbox.JS_FEATURE_EVALUATE_WITHOUT_TRANSACTION_LIMIT)) {
                throw OnlineError("이 기기에서는 YouTube 주소를 풀 수 없어요. Android System WebView를 업데이트해 주세요.")
            }
            box.createIsolate().use { iso ->
                return iso.evaluateJavaScriptAsync(code).get(60, TimeUnit.SECONDS)
            }
        }
    }

    private fun get(http: OkHttpClient, url: String): String =
        http.newCall(okhttp3.Request.Builder().url(url).header("User-Agent", UA).build()).execute().use { r ->
            if (!r.isSuccessful) throw OnlineError("YouTube 플레이어를 받지 못했어요 (HTTP ${r.code}).")
            r.body?.string().orEmpty()
        }
}

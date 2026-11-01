package com.milky.mataf.core

import com.milky.mataf.BuildConfig
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import java.io.File
import java.io.IOException
import java.net.SocketTimeoutException
import java.net.URLEncoder
import java.net.UnknownHostException
import java.net.UnknownServiceException
import java.security.MessageDigest
import java.util.concurrent.TimeUnit
import javax.net.ssl.SSLException

/** 서버가 알려 준 문제. status 0 = 서버에 닿지 못함. message 는 그대로 사용자에게 보여 준다. */
class CloudError(val status: Int, val code: String, message: String, val entry: CloudModel.Entry? = null) : Exception(message) {
    val offline: Boolean get() = status == 0
}

/**
 * 마고에듀 통합 클라우드 서버의 로그인·동기화 API (MagoEdu server/src/routes/auth.js, sync.js).
 * 네트워크를 쓰므로 IO 스레드에서 부른다.
 */
class CloudApi(val server: String, private val token: String?) {
    companion object {
        private val UA = "MaplTajong-Android/${BuildConfig.VERSION_NAME}"
        private val JSON_TYPE = "application/json; charset=utf-8".toMediaType()
        private val BIN_TYPE = "application/octet-stream".toMediaType()

        val http: OkHttpClient by lazy {
            Online.http.newBuilder().connectTimeout(15, TimeUnit.SECONDS).readTimeout(60, TimeUnit.SECONDS)
                .writeTimeout(60, TimeUnit.SECONDS).build()
        }

        fun enc(s: String): String = URLEncoder.encode(s, "UTF-8").replace("+", "%20")

        fun offline(e: Exception): CloudError = CloudError(0, "offline", when (e) {
            is UnknownServiceException -> "보안 연결(https://) 주소만 쓸 수 있어요."
            is SSLException -> "서버의 보안 연결을 확인하지 못했어요. 주소를 확인해 주세요."
            is UnknownHostException -> "서버를 찾지 못했어요. 주소와 인터넷 연결을 확인해 주세요."
            is SocketTimeoutException -> "서버가 응답하지 않아요. 잠시 뒤 다시 해 볼게요."
            else -> "서버에 연결하지 못했어요. 인터넷 연결을 확인해 주세요."
        })
    }

    private fun req(path: String): Request.Builder {
        val b = Request.Builder().url(server + path).header("User-Agent", UA)
        if (token != null) b.header("Authorization", "Bearer $token")
        return b
    }

    private fun <T> call(r: Request, client: OkHttpClient = http, block: (Response) -> T): T {
        val res = try {
            client.newCall(r).execute()
        } catch (e: IllegalArgumentException) {
            throw CloudError(0, "bad_url", "서버 주소가 올바르지 않아요.")
        } catch (e: IOException) {
            throw offline(e)
        }
        return res.use { resp ->
            if (!resp.isSuccessful) throw error(resp)
            try {
                block(resp)
            } catch (e: CloudError) {
                throw e
            } catch (e: IOException) {
                throw offline(e)
            }
        }
    }

    private fun error(r: Response): CloudError {
        val body = try { r.body?.string().orEmpty() } catch (e: IOException) { "" }
        val err = runCatching { Json.parse(body).jObj()?.get("error").jObj() }.getOrNull()
        val msg = err?.get("message").jStr()?.takeIf { it.isNotBlank() } ?: when (r.code) {
            401 -> "로그인이 끝났어요. 다시 로그인해 주세요."
            403 -> "이 계정으로는 쓸 수 없어요."
            404 -> "서버에서 찾지 못했어요. 서버 주소를 확인해 주세요."
            else -> "서버에서 문제가 생겼어요. (${r.code})"
        }
        return CloudError(r.code, err?.get("code").jStr() ?: "http_${r.code}", msg, CloudModel.Entry.from(err?.get("entry").jObj()))
    }

    private fun jsonOf(r: Response): Map<String, Any?> =
        Json.parse(r.body?.string().orEmpty()).jObj() ?: throw CloudError(r.code, "bad_response", "서버 응답을 읽지 못했어요.")

    // ---------------------------------------------------------------- 로그인
    fun login(username: String, password: String, device: Map<String, Any?>): Map<String, Any?> {
        val body = Json.write(mapOf("username" to username, "password" to password, "device" to device), 0).toRequestBody(JSON_TYPE)
        return call(req("/api/auth/login").post(body).build()) { jsonOf(it) }
    }

    fun logout() {
        call(req("/api/auth/logout").post("{}".toRequestBody(JSON_TYPE)).build()) { }
    }

    // ---------------------------------------------------------------- 동기화
    private fun fileQ(path: String) = "/api/sync/${CloudModel.APP_ID}/file?path=${enc(path)}"

    /** 바뀐 파일 목록: { seq, full, entries } */
    fun list(since: Long): Map<String, Any?> =
        call(req("/api/sync/${CloudModel.APP_ID}?since=$since").get().build()) { jsonOf(it) }

    /** 받은 내용의 SHA-256 이 맞는지 확인하며 받는다 */
    fun downloadBytes(path: String, expectSha: String?): ByteArray = call(req(fileQ(path)).get().build()) { r ->
        val bytes = r.body?.bytes() ?: ByteArray(0)
        val sha = CloudModel.sha256(bytes)
        if (expectSha != null && sha != expectSha.lowercase()) throw CloudError(0, "checksum", "받은 파일이 깨졌어요. 다시 받을게요.")
        bytes
    }

    /** 파일로 받는다: 임시 파일에 다 받고 확인한 뒤 바꿔 넣는다. 돌려주는 값: SHA-256 */
    fun downloadFile(path: String, dst: File, expectSha: String?): String = call(req(fileQ(path)).get().build()) { r ->
        val part = File(dst.parentFile, ".${dst.name}.cloud")
        val md = MessageDigest.getInstance("SHA-256")
        try {
            r.body!!.byteStream().use { input ->
                part.outputStream().use { out ->
                    val buf = ByteArray(64 * 1024)
                    while (true) {
                        val n = input.read(buf)
                        if (n < 0) break
                        md.update(buf, 0, n)
                        out.write(buf, 0, n)
                    }
                }
            }
            val sha = md.digest().joinToString("") { "%02x".format(it) }
            if (expectSha != null && sha != expectSha.lowercase()) throw CloudError(0, "checksum", "받은 파일이 깨졌어요. 다시 받을게요.")
            if (!part.renameTo(dst)) {
                dst.delete()
                if (!part.renameTo(dst)) throw IOException("파일을 저장하지 못했어요")
            }
            sha
        } finally {
            part.delete()
        }
    }

    fun upload(path: String, bytes: ByteArray, baseRev: Long): CloudModel.Entry =
        put(path, bytes.toRequestBody(BIN_TYPE), CloudModel.sha256(bytes), baseRev, null)

    fun uploadFile(path: String, file: File, sha: String, baseRev: Long): CloudModel.Entry =
        put(path, file.asRequestBody(BIN_TYPE), sha, baseRev, file.lastModified())

    private fun put(path: String, body: RequestBody, sha: String, baseRev: Long, mtime: Long?): CloudModel.Entry {
        val q = fileQ(path) + "&baseRev=$baseRev" + (if (mtime != null && mtime > 0) "&mtime=$mtime" else "")
        return call(req(q).header("x-sha256", sha).put(body).build()) { r ->
            CloudModel.Entry.from(jsonOf(r)["entry"].jObj()) ?: throw CloudError(r.code, "bad_response", "서버 응답을 읽지 못했어요.")
        }
    }

    fun delete(path: String, baseRev: Long): CloudModel.Entry? =
        call(req(fileQ(path) + "&baseRev=$baseRev").delete().build()) { r -> CloudModel.Entry.from(jsonOf(r)["entry"].jObj()) }
}

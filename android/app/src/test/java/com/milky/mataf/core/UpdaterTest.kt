package com.milky.mataf.core

import okhttp3.Dns
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.Dispatcher
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.RecordedRequest
import okio.Buffer
import org.junit.After
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File
import java.net.InetAddress
import java.util.concurrent.ConcurrentLinkedQueue
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.TimeUnit

class UpdaterTest {
    @get:Rule val temp = TemporaryFolder(File("build"))

    private data class Reply(val body: ByteArray, val status: Int = 200, val location: String? = null, val chunked: Boolean = false)
    private data class Seen(val path: String, val authorization: String?)

    private class Server {
        val replies = ConcurrentLinkedQueue<Reply>()
        val seen = CopyOnWriteArrayList<Seen>()
        val server = MockWebServer().apply {
            dispatcher = object : Dispatcher() {
                override fun dispatch(request: RecordedRequest): MockResponse {
                    seen += Seen(request.path.orEmpty(), request.getHeader("Authorization"))
                    val reply = replies.poll() ?: Reply("Unexpected request".toByteArray(), 500)
                    return MockResponse().setResponseCode(reply.status).apply {
                        reply.location?.let { addHeader("Location", it) }
                        val body = Buffer().write(reply.body)
                        if (reply.chunked) setChunkedBody(body, 8192) else setBody(body)
                    }
                }
            }
            start(InetAddress.getByName("127.0.0.1"), 0)
        }
        val url = server.url("/").toString().trimEnd('/')
        fun json(value: Any?) { replies += Reply(Json.write(value).toByteArray()) }
    }

    private val servers = mutableListOf<Server>()
    private fun server() = Server().also { servers += it }
    // 모든 테스트 요청은 로컬로만 보낸다. 회귀로 GitHub를 호출하면 서버 요청 검증이 실패한다.
    private val http = OkHttpClient.Builder().dns(object : Dns {
        override fun lookup(hostname: String) = listOf(InetAddress.getByName("127.0.0.1"))
    })
        .connectTimeout(2, TimeUnit.SECONDS).readTimeout(2, TimeUnit.SECONDS).build()
    private val apk = ByteArray(300_000) { (it % 251).toByte() }
    private val hash = CloudModel.sha256(apk)
    private val token = "cloud-test-token"
    private val downloadPath = "/api/apps/tajong-android/download?version=2.3.0"

    @After
    fun close() {
        servers.forEach { it.server.shutdown() }
        http.connectionPool.evictAll()
        http.dispatcher.executorService.shutdown()
    }

    private fun release() = mapOf<String, Any?>(
        "version" to "2.3.0", "fileName" to "MaplTajong-2.3.0.apk", "size" to apk.size,
        "sha256" to hash.uppercase(), "notes" to "# 새 버전\n- 클라우드 업데이트",
        "releaseUrl" to "https://github.com/private/repo/releases/tag/android-v2.3.0",
        "url" to "https://api.github.com/should-not-be-used",
    )
    private fun app(release: Map<String, Any?>? = release(), id: String = "tajong-android", platform: String = "android") =
        mapOf("id" to id, "name" to "마고 타종 (안드로이드)", "platform" to platform, "allowed" to true, "release" to release)
    private fun Server.catalog(vararg apps: Map<String, Any?>) = json(mapOf("apps" to apps.toList()))
    private fun check(server: Server, current: String = "2.2.9") = Updater.check(current, server.url to token, http)
    private fun info(server: Server): UpdateInfo {
        server.catalog(app())
        return check(server)!!
    }
    private fun download(server: Server, info: UpdateInfo) = Updater.download(temp.root, info, server.url to token, http)

    @Test
    fun checksAuthenticatedCatalogAndSelectsOnlyTajongAndroid() {
        val server = server()
        server.catalog(app(release() + ("version" to "99.0.0"), id = "tajong", platform = "windows"),
            app(release() + ("version" to "98.0.0"), id = "other-android"), app())
        val info = Updater.check("2.2.9", (server.url + "/") to token, http)!!
        assertEquals("2.3.0", info.version)
        assertEquals("# 새 버전\n- 클라우드 업데이트", info.notes)
        assertEquals("MaplTajong-2.3.0.apk", info.assetName)
        assertEquals(apk.size.toLong(), info.size)
        assertEquals(hash, info.sha256)
        assertEquals(server.url + downloadPath, info.assetUrl)
        assertEquals(server.url + "/", info.pageUrl)
        assertEquals(listOf(Seen("/api/apps", "Bearer $token")), server.seen.toList())
    }

    @Test
    fun currentOrOlderReleaseIsNotAnUpdate() {
        val server = server()
        for (current in listOf("2.3.0", "2.3", "2.4.0", "3.0.0")) {
            server.catalog(app())
            assertNull(check(server, current))
        }
    }

    @Test
    fun missingAppPermissionPlatformOrReleaseIsNotReportedAsLatest() {
        val server = server()
        for (entry in listOf(app(id = "tajong", platform = "windows"), app(platform = "windows"),
            app() + ("allowed" to false), app(release = null))) {
            server.catalog(entry)
            assertThrows(UpdateError::class.java) { check(server) }
        }
        server.catalog()
        assertThrows(UpdateError::class.java) { check(server) }
    }

    @Test
    fun absentOptionalMetadataDoesNotUseGithubFallback() {
        val server = server()
        for (sha in listOf(null, "", "not-a-sha256")) {
            server.catalog(app(release() + mapOf("notes" to null, "size" to null, "sha256" to sha)))
            val info = check(server)!!
            assertEquals("", info.notes)
            assertEquals(0L, info.size)
            assertNull(info.sha256)
            assertEquals(server.url + downloadPath, info.assetUrl)
        }
        assertEquals(3, server.seen.size)
    }

    @Test
    fun malformedCatalogAndUnsafeFileNamesAreRejected() {
        val server = server()
        for (body in listOf("not json", "{}", "{\"apps\":{}}")) {
            server.replies += Reply(body.toByteArray())
            assertThrows(UpdateError::class.java) { check(server) }
        }
        for (file in listOf("../bad.apk", "..\\bad.apk", "app.zip", "")) {
            server.catalog(app(release() + ("fileName" to file)))
            assertThrows(UpdateError::class.java) { check(server) }
        }
        server.catalog(app(release() + ("version" to "invalid")))
        assertThrows(UpdateError::class.java) { check(server) }
    }

    @Test
    fun loggedOutCheckAndDownloadMakeNoRequest() {
        val server = server()
        val info = info(server)
        for (credentials in listOf(null, server.url to " ")) {
            assertTrue(assertThrows(UpdateError::class.java) {
                Updater.check("2.2.9", credentials, http)
            }.message!!.contains("로그인"))
            assertTrue(assertThrows(UpdateError::class.java) {
                Updater.download(temp.root, info, credentials, http)
            }.message!!.contains("로그인"))
        }
        assertEquals(1, server.seen.size)
    }

    @Test
    fun authenticationPermissionAndServerErrorsHaveHelpfulMessages() {
        val server = server()
        for ((status, text) in listOf(401 to "다시 로그인", 403 to "권한", 503 to "잠시 바빠요")) {
            server.replies += Reply("error".toByteArray(), status)
            assertTrue(assertThrows(UpdateError::class.java) { check(server) }.message!!.contains(text))
        }
        assertEquals(3, server.seen.size)
    }

    @Test
    fun unreachableServerHasNoAlternateNetworkFallback() {
        val server = server()
        val info = info(server)
        server.server.shutdown()
        assertTrue(assertThrows(UpdateError::class.java) { check(server) }.message!!.contains("서버에 연결하지 못했어요"))
        assertTrue(assertThrows(UpdateError::class.java) { download(server, info) }.message!!.contains("서버에 연결하지 못했어요"))
        assertEquals(1, server.seen.size)
        assertFalse(File(temp.root, info.assetName + ".part").exists())
    }

    @Test
    fun downloadsAuthenticatedProxyWithProgressChecksumAndCacheReuse() {
        val server = server()
        val info = info(server)
        server.replies += Reply(apk, chunked = true) // 프록시가 Content-Length를 주지 않아도 카탈로그 크기를 쓴다.
        val progress = mutableListOf<Float>()
        val file = Updater.download(temp.root, info, server.url to token, http, { progress += it })
        assertArrayEquals(apk, file.readBytes())
        assertTrue(progress.any { it > 0f && it < 1f })
        assertEquals(1f, progress.last())
        assertFalse(File(file.path + ".part").exists())
        assertEquals(file, download(server, info))
        assertEquals(listOf(Seen("/api/apps", "Bearer $token"), Seen(downloadPath, "Bearer $token")), server.seen.toList())
    }

    @Test
    fun crossOriginRedirectDoesNotReceiveCloudToken() {
        val server = server()
        val cdn = server()
        val info = info(server)
        server.replies += Reply("redirect".toByteArray(), 302, cdn.url + "/signed.apk")
        cdn.replies += Reply(apk)
        assertArrayEquals(apk, download(server, info).readBytes())
        assertEquals(Seen(downloadPath, "Bearer $token"), server.seen.last())
        assertEquals(listOf(Seen("/signed.apk", null)), cdn.seen.toList())
    }

    @Test
    fun sameOriginRedirectRetainsCloudAuthentication() {
        val server = server()
        val info = info(server)
        server.replies += Reply("redirect".toByteArray(), 302, "/asset.apk")
        server.replies += Reply(apk)
        assertArrayEquals(apk, download(server, info).readBytes())
        assertEquals(Seen("/asset.apk", "Bearer $token"), server.seen.last())
    }

    @Test
    fun evenServerRedirectCannotCallGithubApi() {
        val server = server()
        val info = info(server)
        server.replies += Reply("redirect".toByteArray(), 302, "http://api.github.com:${server.server.port}/repos/private/releases")
        assertThrows(UpdateError::class.java) { download(server, info) }
        assertEquals(2, server.seen.size) // API 요청은 전송 전에 차단. DNS도 테스트 로컬 주소만 사용.
    }

    @Test
    fun changedCloudOriginCannotReceiveTokenOrDownload() {
        val original = server()
        val other = server()
        val info = info(original)
        assertTrue(assertThrows(UpdateError::class.java) { download(other, info) }.message!!.contains("서버가 바뀌었어요"))
        assertEquals(1, original.seen.size)
        assertTrue(other.seen.isEmpty())
    }

    @Test
    fun checksumMismatchRemovesPartialFileAndDoesNotInstall() {
        val server = server()
        val info = info(server)
        server.replies += Reply("damaged apk".toByteArray())
        assertTrue(assertThrows(UpdateError::class.java) { download(server, info) }.message!!.contains("파일이 올바르지 않아요"))
        assertFalse(File(temp.root, info.assetName).exists())
        assertFalse(File(temp.root, info.assetName + ".part").exists())
    }

    @Test
    fun missingOrInvalidChecksumBlocksDownload() {
        val server = server()
        val info = info(server)
        for (sha in listOf(null, "", "invalid")) {
            assertTrue(assertThrows(UpdateError::class.java) { download(server, info.copy(sha256 = sha)) }.message!!.contains("SHA-256"))
        }
        assertEquals(1, server.seen.size)
    }

    @Test
    fun cancelledDownloadRemovesPartialFile() {
        val server = server()
        val info = info(server)
        server.replies += Reply(apk)
        assertEquals("취소했어요.", assertThrows(UpdateError::class.java) {
            Updater.download(temp.root, info, server.url to token, http, cancelled = { true })
        }.message)
        assertFalse(File(temp.root, info.assetName).exists())
        assertFalse(File(temp.root, info.assetName + ".part").exists())
    }

    @Test
    fun expiredLoginOrReplacedReleaseDuringDownloadIsReported() {
        val server = server()
        val info = info(server)
        for ((status, text) in listOf(401 to "다시 로그인", 404 to "업데이트를 다시 확인")) {
            server.replies += Reply("error".toByteArray(), status)
            assertTrue(assertThrows(UpdateError::class.java) { download(server, info) }.message!!.contains(text))
            assertFalse(File(temp.root, info.assetName + ".part").exists())
        }
    }
}

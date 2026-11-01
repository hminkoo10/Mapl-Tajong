package com.milky.mataf.core

import android.content.Context
import android.webkit.CookieManager
import java.io.File
import java.security.MessageDigest

/**
 * YouTube 받기용 구글 로그인 (데스크톱 app/core/google_login.py 와 같은 역할).
 * 앱 안의 로그인 창에서 사용자가 직접 로그인하면, YouTube 로그인 정보(쿠키)만 이 기기의 앱 폴더에 저장한다.
 * 다른 곳으로 보내지 않고, YouTube 에 물을 때만 쓴다.
 */
object GoogleLogin {
    const val LOGIN_URL = "https://accounts.google.com/ServiceLogin?service=youtube&uilel=3&passive=true&hl=ko" +
        "&continue=https%3A%2F%2Fwww.youtube.com%2Fsignin%3Faction_handle_signin%3Dtrue%26app%3Ddesktop" +
        "%26hl%3Dko%26next%3Dhttps%253A%252F%252Fwww.youtube.com%252F"
    const val YOUTUBE = "https://www.youtube.com"
    private val LOGIN_COOKIES = setOf("LOGIN_INFO", "SAPISID", "__Secure-3PAPISID")

    private fun file(ctx: Context) = File(ctx.filesDir, "youtube_cookies.txt")

    /** 저장한 쿠키 ("이름=값; 이름=값" 한 줄). 로그인하지 않았으면 null */
    fun cookies(ctx: Context): String? =
        runCatching { file(ctx).readText().trim() }.getOrNull()?.takeIf { hasLogin(it) }

    fun isLoggedIn(ctx: Context): Boolean = cookies(ctx) != null

    fun loggedInAt(ctx: Context): Long? = file(ctx).takeIf { it.exists() }?.lastModified()

    fun parse(header: String): Map<String, String> =
        header.split(';').mapNotNull {
            val i = it.indexOf('=')
            if (i <= 0) null else it.substring(0, i).trim() to it.substring(i + 1).trim()
        }.toMap()

    fun hasLogin(header: String?): Boolean = header != null && parse(header).keys.any { it in LOGIN_COOKIES }

    fun save(ctx: Context, header: String) {
        val f = file(ctx)
        val tmp = File(f.path + ".tmp")
        tmp.writeText(header.trim())
        if (!tmp.renameTo(f)) {
            f.writeText(header.trim()); tmp.delete()
        }
    }

    fun logout(ctx: Context) {
        file(ctx).delete()
        CookieManager.getInstance().apply { removeAllCookies(null); flush() }
    }

    /**
     * 로그인한 채로 YouTube(InnerTube)에 물을 때 붙이는 헤더 (yt-dlp 와 같은 SAPISIDHASH 방식).
     * userSessionId 는 YouTube 페이지 설정의 DATASYNC_ID 에서 얻는 값.
     */
    fun authHeaders(cookieHeader: String, origin: String = YOUTUBE, userSessionId: String? = null,
                    sessionIndex: String = "0"): Map<String, String> {
        val c = parse(cookieHeader)
        val ts = (System.currentTimeMillis() / 1000).toString()
        val pre = if (userSessionId != null) "$userSessionId " else ""
        val post = if (userSessionId != null) "_u" else ""
        fun hash(scheme: String, sid: String?): String? = sid?.let {
            val d = MessageDigest.getInstance("SHA-1").digest("$pre$ts $it $origin".toByteArray())
            "$scheme ${ts}_${d.joinToString("") { b -> "%02x".format(b) }}$post"
        }
        val auth = listOfNotNull(
            hash("SAPISIDHASH", c["SAPISID"] ?: c["__Secure-3PAPISID"]),
            hash("SAPISID1PHASH", c["__Secure-1PAPISID"]),
            hash("SAPISID3PHASH", c["__Secure-3PAPISID"]),
        )
        val h = mutableMapOf("Cookie" to cookieHeader, "X-Goog-AuthUser" to sessionIndex)
        if (auth.isNotEmpty()) {
            h["Authorization"] = auth.joinToString(" ")
            h["X-Origin"] = origin
        }
        return h
    }
}

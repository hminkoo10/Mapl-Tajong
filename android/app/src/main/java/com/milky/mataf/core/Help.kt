package com.milky.mataf.core

import okhttp3.HttpUrl.Companion.toHttpUrlOrNull

/** 로그인 여부와 관계없이 입력한 서버의 휴대폰 설명서 주소를 만든다. */
fun helpUrl(server: String?): String {
    val base = server?.trim()?.takeIf {
        it.startsWith("http://", ignoreCase = true) || it.startsWith("https://", ignoreCase = true)
    }?.toHttpUrlOrNull()?.takeIf { it.encodedQuery == null && it.fragment == null }
        ?.toString()?.trimEnd('/') ?: Cloud.DEFAULT_SERVER
    return "$base/help/tajong.html#phone"
}

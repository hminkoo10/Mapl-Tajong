package com.milky.mataf.core

import org.junit.Assert.assertEquals
import org.junit.Test

class HelpTest {
    @Test
    fun usesHttpOrHttpsServerIncludingPortAndBasePath() {
        for (server in listOf("https://school.example", "http://192.168.1.10:8080", "https://school.example/cloud",
            "http://[::1]:8080")) {
            assertEquals("$server/help/tajong.html#phone", helpUrl(server))
        }
    }

    @Test
    fun removesSurroundingWhitespaceAndTrailingSlashes() {
        assertEquals("https://school.example/help/tajong.html#phone", helpUrl("  https://school.example/// \n"))
        assertEquals("https://school.example/cloud/help/tajong.html#phone", helpUrl("https://school.example/cloud/"))
        assertEquals("https://school.example/help/tajong.html#phone", helpUrl("HTTPS://school.example/"))
    }

    @Test
    fun missingOrNonWebServerUsesDefault() {
        for (server in listOf(null, "", " \n\t ", "school.example", "ftp://school.example", "file:///tmp/help",
            "javascript:alert(1)", "//school.example")) {
            assertEquals("${Cloud.DEFAULT_SERVER}/help/tajong.html#phone", helpUrl(server))
        }
    }

    @Test
    fun malformedOrNonBaseWebAddressUsesDefault() {
        for (server in listOf("http://", "https:///", "https:/school.example", "https://bad host",
            "https://school.example?next=elsewhere", "https://school.example#section")) {
            assertEquals("${Cloud.DEFAULT_SERVER}/help/tajong.html#phone", helpUrl(server))
        }
    }
}

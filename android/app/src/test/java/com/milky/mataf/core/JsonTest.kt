package com.milky.mataf.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class JsonTest {
    @Test
    fun parsesValuesAndKeepsKeyOrder() {
        val v = Json.parse("""{"b": 1, "a": [true, false, null, -2.5, "x\"y\\z\né"], "c": {"k": 10000000000}}""").jObj()!!
        assertEquals(listOf("b", "a", "c"), v.keys.toList())
        assertEquals(1L, v["b"])
        val a = v["a"].jList()
        assertEquals(true, a[0]); assertEquals(false, a[1]); assertNull(a[2]); assertEquals(-2.5, a[3])
        assertEquals("x\"y\\z\né", a[4])
        assertEquals(10000000000L, v["c"].jObj()!!["k"])
    }

    @Test
    fun writeRoundTripsAndKeepsKorean() {
        val src = linkedMapOf("name" to "1교시", "volume" to 1.0, "id" to 3L, "none" to null, "list" to listOf(1L, 0.85))
        val text = Json.write(src)
        assertTrue(text.contains("\"1교시\""))
        assertTrue("정수 값 실수는 1.0 으로 써요", text.contains("\"volume\": 1.0"))
        assertEquals(src, Json.parse(text))
        assertEquals(src, Json.parse(Json.write(src, 0)))
    }

    @Test
    fun canonicalIgnoresKeyOrderAndNumberForm() {
        val a = Json.parse("""{"x": 1, "y": {"b": 2.0, "a": "가"}}""")
        val b = Json.parse("""{"y": {"a": "가", "b": 2}, "x": 1.0}""")
        assertEquals(Json.canonical(a), Json.canonical(b))
        assertNotEquals(Json.canonical(a), Json.canonical(Json.parse("""{"x": 1, "y": {"a": "가", "b": 3}}""")))
        // 1 과 true 는 다르다
        assertNotEquals(Json.canonical(mapOf("e" to 1L)), Json.canonical(mapOf("e" to true)))
    }

    @Test
    fun bomAndWhitespaceAreFine() {
        assertEquals(mapOf("a" to 1L), Json.parse("﻿  {\"a\" :1 }\r\n"))
    }

    @Test(expected = Json.ParseError::class)
    fun brokenJsonThrows() {
        Json.parse("""{"a": 1""")
    }
}

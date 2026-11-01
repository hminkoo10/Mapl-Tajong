package com.milky.mataf.core

import java.math.BigDecimal

/**
 * 클라우드 동기화 파일용 아주 작은 JSON 읽기/쓰기 (안드로이드 org.json 없이도 시험할 수 있게).
 * 값: Map<String, Any?>(순서 유지) · List<Any?> · String · Long · Double · Boolean · null
 */
object Json {
    class ParseError(message: String) : IllegalArgumentException(message)

    fun parse(text: String): Any? {
        val p = Parser(text)
        p.ws()
        val v = p.value()
        p.ws()
        if (!p.end()) throw ParseError("JSON 뒤에 남은 글자가 있어요")
        return v
    }

    /** 사람이 읽기 좋게 (들여쓰기 2칸, 한글은 그대로) */
    fun write(v: Any?, indent: Int = 2): String = StringBuilder().also { out(it, v, indent, 0, sortKeys = false) }.toString()

    /**
     * 내용 비교용: 키를 정렬하고 공백 없이, 숫자는 값이 같으면 같은 글자로 (1 과 1.0 은 같다).
     */
    fun canonical(v: Any?): String = StringBuilder().also { out(it, v, 0, 0, sortKeys = true, canon = true) }.toString()

    private fun out(sb: StringBuilder, v: Any?, indent: Int, level: Int, sortKeys: Boolean, canon: Boolean = false) {
        when (v) {
            null -> sb.append("null")
            is String -> str(sb, v)
            is Boolean -> sb.append(if (v) "true" else "false")
            is Int, is Long, is Short, is Byte -> sb.append(v.toString())
            is Double, is Float -> sb.append(if (canon) canonNumber(v as Number) else double(v.toDouble()))
            is Number -> sb.append(if (canon) canonNumber(v) else v.toString())
            is Map<*, *> -> {
                if (v.isEmpty()) { sb.append("{}"); return }
                val keys = v.keys.map { it.toString() }.let { if (sortKeys) it.sorted() else it }
                sb.append('{')
                keys.forEachIndexed { i, k ->
                    if (i > 0) sb.append(',')
                    nl(sb, indent, level + 1)
                    str(sb, k)
                    sb.append(if (indent > 0) ": " else ":")
                    out(sb, v[k], indent, level + 1, sortKeys, canon)
                }
                nl(sb, indent, level)
                sb.append('}')
            }
            is Iterable<*> -> {
                val items = v.toList()
                if (items.isEmpty()) { sb.append("[]"); return }
                sb.append('[')
                items.forEachIndexed { i, x ->
                    if (i > 0) sb.append(',')
                    nl(sb, indent, level + 1)
                    out(sb, x, indent, level + 1, sortKeys, canon)
                }
                nl(sb, indent, level)
                sb.append(']')
            }
            else -> str(sb, v.toString())
        }
    }

    private fun nl(sb: StringBuilder, indent: Int, level: Int) {
        if (indent <= 0) return
        sb.append('\n')
        repeat(indent * level) { sb.append(' ') }
    }

    /** 파이썬 json 처럼 정수 값 실수는 1.0 으로 */
    private fun double(d: Double): String {
        if (d.isNaN() || d.isInfinite()) return "null"
        return if (d == Math.floor(d) && Math.abs(d) < 1e15) "%.1f".format(java.util.Locale.ROOT, d) else d.toString()
    }

    private fun canonNumber(n: Number): String = try {
        val d = n.toDouble()
        if (d.isNaN() || d.isInfinite()) "null" else BigDecimal(n.toString()).stripTrailingZeros().toPlainString()
    } catch (e: NumberFormatException) {
        n.toString()
    }

    private fun str(sb: StringBuilder, s: String) {
        sb.append('"')
        for (c in s) {
            when (c) {
                '"' -> sb.append("\\\"")
                '\\' -> sb.append("\\\\")
                '\n' -> sb.append("\\n")
                '\r' -> sb.append("\\r")
                '\t' -> sb.append("\\t")
                '\b' -> sb.append("\\b")
                '\u000c' -> sb.append("\\f")
                else -> if (c < ' ' || c == ' ' || c == ' ') sb.append("\\u%04x".format(c.code)) else sb.append(c)
            }
        }
        sb.append('"')
    }

    private class Parser(val s: String) {
        var i = 0

        fun end() = i >= s.length

        fun ws() {
            while (i < s.length && (s[i] == ' ' || s[i] == '\n' || s[i] == '\r' || s[i] == '\t' || s[i] == '﻿')) i++
        }

        fun fail(msg: String): Nothing = throw ParseError("$msg (위치 $i)")

        fun value(): Any? {
            if (end()) fail("값이 없어요")
            return when (val c = s[i]) {
                '{' -> obj()
                '[' -> arr()
                '"' -> string()
                't' -> word("true", true)
                'f' -> word("false", false)
                'n' -> word("null", null)
                else -> if (c == '-' || c in '0'..'9') number() else fail("알 수 없는 글자 '$c'")
            }
        }

        fun word(w: String, v: Any?): Any? {
            if (!s.startsWith(w, i)) fail("알 수 없는 값")
            i += w.length
            return v
        }

        fun obj(): Map<String, Any?> {
            val m = LinkedHashMap<String, Any?>()
            i++
            ws()
            if (i < s.length && s[i] == '}') { i++; return m }
            while (true) {
                ws()
                if (end() || s[i] != '"') fail("키가 없어요")
                val k = string()
                ws()
                if (end() || s[i] != ':') fail("':' 가 없어요")
                i++
                ws()
                m[k] = value()
                ws()
                if (end()) fail("'}' 가 없어요")
                when (s[i]) {
                    ',' -> i++
                    '}' -> { i++; return m }
                    else -> fail("',' 나 '}' 가 없어요")
                }
            }
        }

        fun arr(): List<Any?> {
            val l = ArrayList<Any?>()
            i++
            ws()
            if (i < s.length && s[i] == ']') { i++; return l }
            while (true) {
                ws()
                l += value()
                ws()
                if (end()) fail("']' 가 없어요")
                when (s[i]) {
                    ',' -> i++
                    ']' -> { i++; return l }
                    else -> fail("',' 나 ']' 가 없어요")
                }
            }
        }

        fun string(): String {
            i++
            val sb = StringBuilder()
            while (true) {
                if (end()) fail("글자가 끝나지 않았어요")
                val c = s[i++]
                when (c) {
                    '"' -> return sb.toString()
                    '\\' -> {
                        if (end()) fail("잘못된 이스케이프")
                        when (val e = s[i++]) {
                            '"' -> sb.append('"'); '\\' -> sb.append('\\'); '/' -> sb.append('/')
                            'b' -> sb.append('\b'); 'f' -> sb.append('\u000c'); 'n' -> sb.append('\n')
                            'r' -> sb.append('\r'); 't' -> sb.append('\t')
                            'u' -> {
                                if (i + 4 > s.length) fail("잘못된 \\u")
                                sb.append(s.substring(i, i + 4).toIntOrNull(16)?.toChar() ?: fail("잘못된 \\u"))
                                i += 4
                            }
                            else -> fail("잘못된 이스케이프 '$e'")
                        }
                    }
                    else -> sb.append(c)
                }
            }
        }

        fun number(): Any {
            val start = i
            if (s[i] == '-') i++
            while (i < s.length && s[i] in '0'..'9') i++
            var real = false
            if (i < s.length && s[i] == '.') {
                real = true; i++
                while (i < s.length && s[i] in '0'..'9') i++
            }
            if (i < s.length && (s[i] == 'e' || s[i] == 'E')) {
                real = true; i++
                if (i < s.length && (s[i] == '+' || s[i] == '-')) i++
                while (i < s.length && s[i] in '0'..'9') i++
            }
            val t = s.substring(start, i)
            if (t == "-" || t.isEmpty()) fail("잘못된 숫자")
            return if (real) t.toDouble() else t.toLongOrNull() ?: t.toDouble()
        }
    }
}

// 읽은 JSON 값에서 꺼내기
@Suppress("UNCHECKED_CAST")
fun Any?.jObj(): Map<String, Any?>? = this as? Map<String, Any?>

fun Any?.jList(): List<Any?> = (this as? List<Any?>) ?: emptyList()

fun Any?.jLong(): Long? = when (this) {
    is Number -> if (this is Double || this is Float) this.toDouble().takeIf { it == Math.floor(it) }?.toLong() else this.toLong()
    is String -> this.trim().toLongOrNull()
    is Boolean -> if (this) 1L else 0L
    else -> null
}

fun Any?.jStr(): String? = when (this) {
    null -> null
    is String -> this
    else -> this.toString()
}

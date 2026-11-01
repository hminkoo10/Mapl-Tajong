package com.milky.mataf.core

import android.content.Context
import android.os.SystemClock
import com.milky.mataf.BuildConfig
import com.milky.mataf.data.Repo
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.Request
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.time.LocalDateTime
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale
import java.util.concurrent.TimeUnit
import kotlin.math.round

data class Place(val name: String, val lat: Double, val lon: Double)

/** 지역 검색 결과 한 줄. exact: 건물 번호까지 맞음, approx: 줄여서 찾은 검색어 */
data class FoundPlace(val name: String, val label: String, val lat: Double, val lon: Double,
                      val exact: Boolean = false, val approx: String? = null)

data class WxNow(val temp: Double?, val kind: String, val text: String, val night: Boolean)
data class WxHour(val time: LocalDateTime, val temp: Double, val kind: String, val night: Boolean)
data class WxData(val city: String, val now: WxNow, val todayMax: Double?, val todayMin: Double?, val hours: List<WxHour>)

/**
 * 날씨 예보 (노르웨이 기상청 MET Norway Locationforecast 2.0, 키 없이 무료, CC BY 4.0)와
 * 지역 검색 (OpenStreetMap Nominatim). 데스크톱 app/core/weather.py 와 같은 규칙.
 * - 요청 간격과 캐시는 서버가 알려 주는 Expires / Last-Modified 를 따른다 (MET 이용 규칙).
 * - 받은 내용은 파일로 보관해 인터넷이 잠깐 끊겨도 마지막 예보를 보여 준다.
 */
object Weather {
    private const val API = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
    private val USER_AGENT = "MaplTajong-Android/${BuildConfig.VERSION_NAME} (+https://github.com/hminkoo10/Mapl-Tajong)"
    const val CREDIT = "날씨 정보: 노르웨이 기상청(MET Norway)"
    private const val MIN_INTERVAL = 15 * 60L

    // 학원·학교가 많은 곳 위주
    val CITIES = listOf(
        Place("서울", 37.5665, 126.9780), Place("인천", 37.4563, 126.7052), Place("수원", 37.2636, 127.0286),
        Place("성남", 37.4200, 127.1267), Place("고양", 37.6584, 126.8320), Place("용인", 37.2411, 127.1776),
        Place("부천", 37.5034, 126.7660), Place("안산", 37.3219, 126.8309), Place("안양", 37.3943, 126.9568),
        Place("남양주", 37.6360, 127.2165), Place("화성", 37.1995, 126.8312), Place("평택", 36.9921, 127.1129),
        Place("의정부", 37.7381, 127.0337), Place("파주", 37.7600, 126.7800), Place("김포", 37.6153, 126.7156),
        Place("광명", 37.4786, 126.8646), Place("하남", 37.5393, 127.2149), Place("시흥", 37.3800, 126.8029),
        Place("춘천", 37.8813, 127.7298), Place("원주", 37.3422, 127.9202), Place("강릉", 37.7519, 128.8761),
        Place("청주", 36.6424, 127.4890), Place("천안", 36.8151, 127.1139), Place("세종", 36.4800, 127.2890),
        Place("대전", 36.3504, 127.3845), Place("전주", 35.8242, 127.1480), Place("군산", 35.9676, 126.7366),
        Place("광주", 35.1595, 126.8526), Place("목포", 34.8118, 126.3922), Place("여수", 34.7604, 127.6622),
        Place("순천", 34.9506, 127.4872), Place("대구", 35.8714, 128.6014), Place("포항", 36.0190, 129.3435),
        Place("구미", 36.1195, 128.3446), Place("안동", 36.5684, 128.7294), Place("경주", 35.8562, 129.2247),
        Place("부산", 35.1796, 129.0756), Place("울산", 35.5384, 129.3114), Place("창원", 35.2280, 128.6811),
        Place("김해", 35.2285, 128.8894), Place("진주", 35.1800, 128.1076), Place("제주", 33.4996, 126.5312),
        Place("서귀포", 33.2541, 126.5600),
    )
    const val DEFAULT_CITY = "서울"

    // MET 기호 → (그림 종류, 한국어)
    private val SYMBOLS = mapOf(
        "clearsky" to ("clear" to "맑음"), "fair" to ("fair" to "대체로 맑음"), "partlycloudy" to ("partly" to "구름 조금"),
        "cloudy" to ("cloudy" to "흐림"), "fog" to ("fog" to "안개"),
        "lightrainshowers" to ("rain" to "약한 소나기"), "rainshowers" to ("rain" to "소나기"),
        "heavyrainshowers" to ("rain" to "강한 소나기"), "lightrain" to ("rain" to "약한 비"), "rain" to ("rain" to "비"),
        "heavyrain" to ("rain" to "강한 비"),
        "lightsleetshowers" to ("sleet" to "진눈깨비"), "sleetshowers" to ("sleet" to "진눈깨비"),
        "heavysleetshowers" to ("sleet" to "진눈깨비"), "lightsleet" to ("sleet" to "진눈깨비"), "sleet" to ("sleet" to "진눈깨비"),
        "heavysleet" to ("sleet" to "진눈깨비"),
        "lightsnowshowers" to ("snow" to "약한 눈"), "snowshowers" to ("snow" to "눈"), "heavysnowshowers" to ("snow" to "많은 눈"),
        "lightsnow" to ("snow" to "약한 눈"), "snow" to ("snow" to "눈"), "heavysnow" to ("snow" to "많은 눈"),
    )

    private val http by lazy { Online.http.newBuilder().callTimeout(12, TimeUnit.SECONDS).build() }

    fun city(name: String): Place = CITIES.firstOrNull { it.name == name } ?: CITIES[0]

    /** 설정값(도시 이름 또는 {"name","lat","lon"} JSON)을 지역으로 */
    fun placeOf(value: String): Place {
        val t = value.trim()
        if (t.startsWith("{")) {
            return try {
                JSONObject(t).let { Place(it.getString("name"), it.getDouble("lat"), it.getDouble("lon")) }
            } catch (_: Exception) {
                city(DEFAULT_CITY)
            }
        }
        return city(t.ifEmpty { DEFAULT_CITY })
    }

    /** 설정에서 지역 값을 읽는다 (예전 'weather_city' 도 그대로 쓴다) */
    fun settingValue(repo: Repo): String = repo.setting("weather_place", "").ifEmpty { repo.setting("weather_city", DEFAULT_CITY) }

    fun place(repo: Repo): Place = placeOf(settingValue(repo))

    fun savePlace(repo: Repo, p: FoundPlace) {
        fun r4(v: Double) = round(v * 10000) / 10000
        repo.setSetting("weather_place", JSONObject().put("name", p.name).put("lat", r4(p.lat)).put("lon", r4(p.lon)).toString())
    }

    private fun log(ctx: Context, kind: String, detail: String) {
        try {
            val f = File(ctx.filesDir, "weather.log")
            val lines = (if (f.exists()) f.readLines().takeLast(200) else emptyList()) +
                "[${LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss"))}] $kind: ${detail.take(500)}"
            f.writeText(lines.joinToString("\n") + "\n")
        } catch (_: Exception) {
        }
    }

    // ---------------- 지역 검색 (OpenStreetMap Nominatim) ----------------
    private const val GEO_URL = "https://nominatim.openstreetmap.org/search"
    const val GEO_CREDIT = "지역 검색: © OpenStreetMap 기여자"
    private val geoLock = Any()
    private var geoLast = 0L

    private val COORD = Regex("""^\s*(-?\d{1,3}(?:\.\d+)?)\s*[, ]\s*(-?\d{1,3}(?:\.\d+)?)\s*$""")
    // 주소 끝에 붙는 번지·건물·층 같은 말 (지도 데이터에 없을 때가 많아 줄여 가며 다시 찾는다)
    private val DETAIL = Regex("""(\d+(?:-\d+)?(?:번지|번길|호|층|동)?|\(.*?\)|[A-Za-z]?\d+층|지하\d*층?)""")
    private val ROAD = Regex("""^.+(?:대로|로|길)$""")       // 도로명: 테헤란로, 동성로2길, 강남대로
    private val LOT = Regex("""^.+(?:동|리|가)\d*$""")         // 지번 주소의 동·리: 역삼동, 종로1가
    private val NUM = Regex("""^(?:산)?\d+(?:-\d+)?(?:번지)?$""")

    /** '37.4993, 127.0632' 같은 좌표면 (위도, 경도), 아니면 null */
    fun parseCoords(text: String): Pair<Double, Double>? {
        val m = COORD.matchEntire(text) ?: return null
        val a = m.groupValues[1].toDouble()
        val b = m.groupValues[2].toDouble()
        return when {
            a in 33.0..39.0 && b in 124.0..132.0 -> a to b     // 한국 범위 (위도, 경도)
            b in 33.0..39.0 && a in 124.0..132.0 -> b to a     // (경도, 위도)로 넣은 경우
            a in -90.0..90.0 && b in -180.0..180.0 -> a to b
            else -> null
        }
    }

    private fun nominatim(q: String?, limit: Int, structured: Map<String, String>? = null): JSONArray {
        synchronized(geoLock) {
            val wait = 1100 - (SystemClock.elapsedRealtime() - geoLast)
            if (wait > 0) Thread.sleep(wait)
            geoLast = SystemClock.elapsedRealtime()
        }
        val url = GEO_URL.toHttpUrl().newBuilder()
            .addQueryParameter("format", "jsonv2").addQueryParameter("addressdetails", "1")
            .addQueryParameter("limit", limit.toString()).addQueryParameter("countrycodes", "kr")
            .addQueryParameter("accept-language", "ko")
            .apply { if (structured != null) structured.forEach { (k, v) -> addQueryParameter(k, v) } else addQueryParameter("q", q) }
            .build()
        val req = Request.Builder().url(url).header("User-Agent", USER_AGENT).header("Accept", "application/json").build()
        http.newCall(req).execute().use { r ->
            if (!r.isSuccessful) throw IOException("HTTP ${r.code}")
            return JSONArray(r.body?.string() ?: "[]")
        }
    }

    private class Address(val region: List<String>, val road: String, val num: String, val lot: Boolean)

    /** '서울 강남구 테헤란로 152 3층' → 지역 [서울, 강남구], 도로 테헤란로, 번호 152 (도로명/지번이 아니면 null) */
    private fun parseAddress(text: String): Address? {
        val parts = text.replace(",", " ").split(Regex("\\s+")).filter { it.isNotEmpty() }
        for (i in 0 until parts.size - 1) {
            if ((ROAD.matches(parts[i]) || LOT.matches(parts[i])) && NUM.matches(parts[i + 1])) {
                return Address(parts.subList(0, i), parts[i], parts[i + 1].replace("번지", ""), !ROAD.matches(parts[i]))
            }
        }
        return null
    }

    /** 정확한 건물을 찾을 가능성이 큰 순서대로 검색 방법을 만든다. (검색어, structured) */
    private fun queries(q: String): List<Pair<String?, Map<String, String>?>> {
        val a = parseAddress(q) ?: return listOf(q to null)
        val out = mutableListOf<Pair<String?, Map<String, String>?>>()
        if (!a.lot) {
            val st = mutableMapOf("street" to "${a.num} ${a.road}")
            if (a.region.isNotEmpty()) {
                st["city"] = a.region.last()
                if (a.region.size >= 2) st["state"] = a.region.first()
            }
            out += null to st
        }
        out += (if (a.region.isNotEmpty()) "${a.num} ${a.road}, " + a.region.reversed().joinToString(", ") else "${a.num} ${a.road}") to null
        out += (a.region + listOf(a.road, a.num)).joinToString(" ") to null
        return out
    }

    /** 주소 뒷부분(번지·층·괄호)을 하나씩 떼어 낸 다음 검색어 */
    private fun shorter(q0: String): String? {
        val parts = q0.trim().trimEnd(',').split(Regex("\\s+")).filter { it.isNotEmpty() }
        if (parts.size <= 1) return null
        val last = parts.last()
        if (DETAIL.matches(last) || last.any { it.isDigit() }) return parts.dropLast(1).joinToString(" ")
        return if (parts.size > 2) parts.dropLast(1).joinToString(" ") else null
    }

    private fun JSONObject.str(key: String): String? = optString(key, "").takeIf { it.isNotEmpty() && !isNull(key) }

    private fun house(x: JSONObject): String = x.optJSONObject("address")?.str("house_number") ?: ""

    /**
     * 동네·도시 이름, 도로명/지번 주소, 또는 좌표로 위치를 찾는다 (작업 스레드에서 부른다).
     * 도로명주소는 건물 번호까지 맞는 곳을 먼저 찾고, 없으면 번지 등 뒷부분을 줄여 가며 다시 찾는다.
     * (Nominatim 이용 규칙: 1초에 한 번 이하, 입력할 때마다가 아니라 검색을 누를 때만)
     */
    fun searchPlaces(ctx: Context, query: String, limit: Int = 8): List<FoundPlace> {
        val q = query.trim()
        if (q.isEmpty()) return emptyList()
        parseCoords(q)?.let { (lat, lon) ->
            val n = "좌표 %.4f, %.4f".format(Locale.US, lat, lon)
            return listOf(FoundPlace(n, n, lat, lon))
        }
        val addr = parseAddress(q)
        val want = addr?.num
        var data = emptyList<JSONObject>()
        var used: String? = q
        try {
            for ((text, st) in queries(q)) {
                val got = nominatim(text, limit, st).let { arr -> List(arr.length()) { arr.getJSONObject(it) } }
                if (got.isNotEmpty() && (want == null || got.any { house(it) == want })) {
                    data = got; used = q
                    break
                }
                if (got.isNotEmpty() && data.isEmpty()) {
                    data = got; used = q
                }
            }
            if (data.isEmpty()) {
                used = shorter(q)
                var tries = 0
                while (used != null && tries < 3) {
                    data = nominatim(used, limit).let { arr -> List(arr.length()) { arr.getJSONObject(it) } }
                    tries++
                    if (data.isNotEmpty()) break
                    used = shorter(used)
                }
            }
        } catch (e: Exception) {
            log(ctx, "지역 검색 실패", "$q: $e")
            throw e
        }
        if (want != null) data = data.sortedBy { house(it) != want }
        val out = mutableListOf<FoundPlace>()
        val seen = mutableSetOf<Pair<Long, Long>>()
        for (x in data) {
            val a = x.optJSONObject("address") ?: JSONObject()
            val road = a.str("road")
            val hn = a.str("house_number")
            val xName = x.str("name")
            val name: String
            var bld = ""
            if (road != null && hn != null) {
                name = "$road $hn"
                if (xName != null && xName != road && xName != hn) bld = xName
            } else {
                name = xName ?: road ?: a.str("suburb") ?: a.str("city") ?: used ?: q
            }
            var area = listOf("state", "city", "county", "borough", "city_district", "town", "suburb", "quarter").mapNotNull { a.str(it) }
            area = area.filterIndexed { i, v -> v != name && v !in area.subList(0, i) }.take(3)
            if (bld.isNotEmpty()) area = listOf(bld) + area
            val label = if (area.isNotEmpty()) "$name (${area.joinToString(" ")})" else name
            val lat = x.optString("lat").toDoubleOrNull() ?: continue
            val lon = x.optString("lon").toDoubleOrNull() ?: continue
            if (!seen.add(Math.round(lat * 10000) to Math.round(lon * 10000))) continue
            out += when {
                want != null && hn == want -> FoundPlace(name, label, lat, lon, exact = true)
                used != q || want != null -> FoundPlace(name, label, lat, lon, approx = if (used != q) used else addr?.road ?: used)
                else -> FoundPlace(name, label, lat, lon)
            }
        }
        return out
    }

    // ---------------- 예보 ----------------
    /** 'partlycloudy_night' → (partly, 구름 조금, true) */
    fun describe(symbol: String?): Triple<String, String, Boolean> {
        val code = symbol ?: ""
        val night = code.endsWith("_night") || code.endsWith("_polartwilight")
        val base = code.substringBefore("_")
        if ("thunder" in base) return Triple("thunder", "천둥번개", night)
        val (kind, text) = SYMBOLS[base] ?: ("cloudy" to "흐림")
        return Triple(kind, text, night)
    }

    private fun cacheFile(ctx: Context) = File(ctx.filesDir, "weather.json")

    private fun readCache(ctx: Context): JSONObject = try {
        JSONObject(cacheFile(ctx).readText())
    } catch (_: Exception) {
        JSONObject()
    }

    private fun writeCache(ctx: Context, c: JSONObject) {
        try {
            cacheFile(ctx).writeText(c.toString())
        } catch (_: Exception) {
        }
    }

    private class Row(val t: LocalDateTime, val temp: Double?, val sym: String?)

    /** MET 응답(JSON)을 화면에 쓰기 좋은 모양으로 */
    fun parse(doc: JSONObject, city: String, now: LocalDateTime = LocalDateTime.now()): WxData? {
        val series = doc.optJSONObject("properties")?.optJSONArray("timeseries") ?: return null
        val zone = ZoneId.systemDefault()
        val rows = mutableListOf<Row>()
        for (i in 0 until series.length()) {
            val ts = series.optJSONObject(i) ?: continue
            val t = try {
                OffsetDateTime.parse(ts.getString("time")).atZoneSameInstant(zone).toLocalDateTime()
            } catch (_: Exception) {
                continue
            }
            val data = ts.optJSONObject("data") ?: JSONObject()
            val det = data.optJSONObject("instant")?.optJSONObject("details")
            val temp = if (det != null && det.has("air_temperature") && !det.isNull("air_temperature")) det.getDouble("air_temperature") else null
            val nxt = data.optJSONObject("next_1_hours") ?: data.optJSONObject("next_6_hours") ?: data.optJSONObject("next_12_hours")
            rows += Row(t, temp, nxt?.optJSONObject("summary")?.str("symbol_code"))
        }
        if (rows.isEmpty()) return null
        var cur: Row? = null
        for (r in rows) {
            if (!r.t.isAfter(now.plusMinutes(30))) cur = r else break
        }
        val c = cur ?: rows[0]
        val hours = rows.filter { it.t.isAfter(now) && it.temp != null && it.sym != null }.take(12).map {
            val (k, _, n) = describe(it.sym)
            WxHour(it.t, it.temp!!, k, n)
        }
        val today = rows.filter { it.t.toLocalDate() == now.toLocalDate() }.mapNotNull { it.temp }
        val (kind, text, night) = describe(c.sym)
        return WxData(city, WxNow(c.temp, kind, text, night), today.maxOrNull(), today.minOrNull(), hours)
    }

    /** 예보를 돌려준다 (작업 스레드에서 부른다). 실패하면 보관해 둔 마지막 예보, 그것도 없으면 null */
    fun get(ctx: Context, place: Place, force: Boolean = false): WxData? {
        var cache = readCache(ctx)
        val key = "%s|%.3f|%.3f".format(Locale.US, place.name, place.lat, place.lon)
        val same = cache.optString("key") == key
        val now = System.currentTimeMillis() / 1000.0
        if (same && !force && cache.has("doc") &&
            now < maxOf(cache.optDouble("expires", 0.0), cache.optDouble("fetched", 0.0) + MIN_INTERVAL)) return result(ctx, cache)
        val req = Request.Builder().url("$API?lat=%.4f&lon=%.4f".format(Locale.US, place.lat, place.lon))
            .header("User-Agent", USER_AGENT).header("Accept", "application/json")
        val lastModified = cache.optString("last_modified")
        if (same && lastModified.isNotEmpty() && cache.has("doc")) req.header("If-Modified-Since", lastModified)
        try {
            http.newCall(req.build()).execute().use { r ->
                val expires = r.headers.getDate("Expires")?.time?.div(1000.0) ?: (now + 1800)
                when {
                    r.code == 304 && same -> {
                        cache.put("fetched", now).put("expires", expires)
                        writeCache(ctx, cache)
                    }
                    r.isSuccessful -> {
                        val doc = JSONObject(r.body?.string() ?: "{}")
                        cache = JSONObject().put("key", key).put("city", place.name).put("doc", doc).put("fetched", now)
                            .put("expires", expires).put("last_modified", r.header("Last-Modified") ?: "")
                        writeCache(ctx, cache)
                    }
                    else -> {
                        log(ctx, "예보 받기 실패", "${place.name}: HTTP ${r.code}")
                        if (!same) return null
                    }
                }
            }
        } catch (e: Exception) {
            log(ctx, "예보 받기 실패", "${place.name}: $e")
            if (!same) return null
        }
        return if (cache.has("doc")) result(ctx, cache) else null
    }

    private fun result(ctx: Context, cache: JSONObject): WxData? = try {
        parse(cache.getJSONObject("doc"), cache.optString("city"))
    } catch (e: Exception) {
        log(ctx, "예보 읽기 실패", e.toString())
        null
    }
}

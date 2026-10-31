package com.milky.mataf.ui.components

import android.graphics.BitmapFactory
import android.util.LruCache
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.produceState
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import com.milky.mataf.core.Online
import com.milky.mataf.ui.theme.C
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit
import kotlinx.coroutines.withContext

/** 작은 썸네일 불러오기 (메모리에 몇십 장만 기억) */
object Thumbs {
    private val cache = LruCache<String, ImageBitmap>(80)
    private val gate = Semaphore(4)

    fun cached(url: String): ImageBitmap? = cache.get(url)

    suspend fun load(url: String): ImageBitmap? {
        cache.get(url)?.let { return it }
        return gate.withPermit {
            withContext(Dispatchers.IO) {
                try {
                    val bytes = Online.http.newCall(okhttp3.Request.Builder().url(url).build()).execute().use { r ->
                        if (!r.isSuccessful) null else r.body?.bytes()
                    } ?: return@withContext null
                    val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
                    BitmapFactory.decodeByteArray(bytes, 0, bytes.size, bounds)
                    var sample = 1
                    while (bounds.outWidth / (sample * 2) >= 240) sample *= 2
                    val bmp = BitmapFactory.decodeByteArray(bytes, 0, bytes.size, BitmapFactory.Options().apply { inSampleSize = sample })
                        ?: return@withContext null
                    bmp.asImageBitmap().also { cache.put(url, it) }
                } catch (e: Exception) {
                    null
                }
            }
        }
    }
}

@Composable
fun NetImage(url: String?, modifier: Modifier = Modifier) {
    val img by produceState(url?.let { Thumbs.cached(it) }, url) {
        if (url != null && value == null) value = Thumbs.load(url)
    }
    Box(modifier.background(C.grey100)) {
        img?.let { Image(it, null, Modifier.matchParentSize(), contentScale = ContentScale.Crop) }
    }
}

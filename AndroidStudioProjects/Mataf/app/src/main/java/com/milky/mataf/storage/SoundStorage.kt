package com.milky.mataf.storage

import android.content.Context
import android.net.Uri
import java.io.File
import java.io.FileOutputStream
import java.security.MessageDigest

object SoundStorage {

    fun soundsDir(context: Context): File {
        val d = File(context.filesDir, "sounds")
        if (!d.exists()) d.mkdirs()
        return d
    }

    fun safeFileName(original: String): String {
        val base = original.trim().ifBlank { "sound" }
        val cleaned = base.replace(Regex("""[^\w\-.]+"""), "_")
        return cleaned.take(80)
    }

    fun uniqueName(dir: File, fileName: String): String {
        val f = File(dir, fileName)
        if (!f.exists()) return fileName

        val dot = fileName.lastIndexOf('.')
        val stem = if (dot > 0) fileName.substring(0, dot) else fileName
        val ext = if (dot > 0) fileName.substring(dot) else ""

        var n = 2
        while (true) {
            val cand = "${stem}_$n$ext"
            if (!File(dir, cand).exists()) return cand
            n++
        }
    }

    fun copyAssetIfMissing(context: Context, assetPath: String, targetFileName: String): File {
        val dir = soundsDir(context)
        val out = File(dir, targetFileName)
        if (out.exists()) return out

        context.assets.open(assetPath).use { input ->
            FileOutputStream(out).use { output ->
                input.copyTo(output)
            }
        }
        return out
    }

    fun copyUriToInternal(context: Context, uri: Uri, displayName: String): File {
        val dir = soundsDir(context)
        val safe = safeFileName(displayName)
        val finalName = uniqueName(dir, safe)
        val out = File(dir, finalName)

        context.contentResolver.openInputStream(uri).use { input ->
            requireNotNull(input)
            FileOutputStream(out).use { output ->
                input.copyTo(output)
            }
        }
        return out
    }

    fun sha1(file: File): String {
        val md = MessageDigest.getInstance("SHA-1")
        file.inputStream().use { input ->
            val buf = ByteArray(8192)
            while (true) {
                val r = input.read(buf)
                if (r <= 0) break
                md.update(buf, 0, r)
            }
        }
        return md.digest().joinToString("") { "%02x".format(it) }
    }

    fun resolveExisting(context: Context, fileName: String): File? {
        val clean = File(fileName).name

        val f1 = File(soundsDir(context), clean)
        if (f1.exists()) return f1

        val f2 = File(context.filesDir, clean)
        if (f2.exists()) return f2

        return null
    }

}

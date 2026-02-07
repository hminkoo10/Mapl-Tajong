package com.milky.mataf.alarm

import android.content.Context

object StatusStore {

    private const val PREF = "tajong_status"

    private const val K_NEXT_AT = "next_at"
    private const val K_NEXT_TITLE = "next_title"
    private const val K_NEXT_SOUND = "next_sound"

    private const val K_NOW_NAME = "now_name"
    private const val K_NOW_PLAYING = "now_playing"

    fun setNext(ctx: Context, atMillis: Long, title: String, soundName: String) {
        ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE)
            .edit()
            .putLong(K_NEXT_AT, atMillis)
            .putString(K_NEXT_TITLE, title)
            .putString(K_NEXT_SOUND, soundName)
            .apply()
    }

    fun clear(ctx: Context) {
        ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE)
            .edit()
            .remove(K_NEXT_AT)
            .remove(K_NEXT_TITLE)
            .remove(K_NEXT_SOUND)
            .apply()
    }

    fun getNext(ctx: Context): Triple<Long, String, String> {
        val p = ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE)
        val at = p.getLong(K_NEXT_AT, 0L)
        val title = p.getString(K_NEXT_TITLE, "") ?: ""
        val sound = p.getString(K_NEXT_SOUND, "") ?: ""
        return Triple(at, title, sound)
    }

    fun setNow(ctx: Context, name: String, playing: Boolean) {
        ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE)
            .edit()
            .putString(K_NOW_NAME, name)
            .putBoolean(K_NOW_PLAYING, playing)
            .apply()
    }

    fun getNow(ctx: Context): Pair<String, Boolean> {
        val p = ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE)
        val name = p.getString(K_NOW_NAME, "") ?: ""
        val playing = p.getBoolean(K_NOW_PLAYING, false)
        return name to playing
    }

    fun clearNow(ctx: Context) {
        ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE)
            .edit()
            .remove(K_NOW_NAME)
            .remove(K_NOW_PLAYING)
            .apply()
    }
}

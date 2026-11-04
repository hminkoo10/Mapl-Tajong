package com.milky.mataf.core

/** 늦게 도착한 이전 창의 결과가 새 선택을 덮어쓰지 않도록 요청 번호를 확인한다. */
data class SoundPickerState(
    val requestId: Long = 0,
    val pending: Boolean = false,
    val uri: String? = null,
    val importing: Boolean = false,
) {
    val idle: Boolean get() = !pending && uri == null && !importing
    fun begin(): SoundPickerState = if (idle) copy(requestId = requestId + 1, pending = true) else this
    fun accepts(id: Long): Boolean = pending && requestId == id
    fun result(id: Long, selected: String?): SoundPickerState =
        if (accepts(id)) copy(pending = false, uri = selected) else this
    fun cancel(): SoundPickerState = if (importing) this else copy(pending = false, uri = null)
    fun beginImport(): SoundPickerState = if (uri != null) copy(importing = true) else this
    fun imported(id: Long): SoundPickerState =
        if (requestId == id && importing) copy(uri = null, importing = false) else this
}

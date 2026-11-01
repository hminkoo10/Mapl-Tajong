package com.milky.mataf.ui.screens

import android.annotation.SuppressLint
import android.net.Uri
import android.webkit.CookieManager
import android.webkit.WebChromeClient
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.webkit.WebSettingsCompat
import androidx.webkit.WebViewFeature
import com.milky.mataf.core.GoogleLogin
import com.milky.mataf.ui.components.IconBtn
import com.milky.mataf.ui.theme.C
import com.milky.mataf.ui.theme.text

/**
 * 구글 로그인 창 (데스크톱 '구글 로그인'과 같은 역할).
 * 사용자가 구글 페이지에서 직접 로그인하면 YouTube 로그인 정보만 저장하고 닫는다.
 */
@SuppressLint("SetJavaScriptEnabled")
@Composable
fun GoogleLoginScreen(onDone: (Boolean) -> Unit) {
    val ctx = LocalContext.current
    var progress by remember { mutableIntStateOf(0) }
    var done by remember { mutableStateOf(false) }
    var web by remember { mutableStateOf<WebView?>(null) }

    fun check(url: String?) {
        if (done || Uri.parse(url ?: return).host?.endsWith("youtube.com") != true) return
        val cookies = CookieManager.getInstance().getCookie(GoogleLogin.YOUTUBE)
        if (GoogleLogin.hasLogin(cookies)) {
            done = true
            GoogleLogin.save(ctx, cookies)
            CookieManager.getInstance().flush()
            onDone(true)
        }
    }

    Dialog(onDismissRequest = { onDone(false) },
        properties = DialogProperties(usePlatformDefaultWidth = false, dismissOnBackPress = false)) {
        BackHandler {
            val w = web
            if (w != null && w.canGoBack()) w.goBack() else onDone(false)
        }
        Column(Modifier.fillMaxSize().background(Color.White).systemBarsPadding().imePadding()) {
            Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 12.dp), verticalAlignment = Alignment.CenterVertically) {
                IconBtn(Icons.AutoMirrored.Rounded.ArrowBack, { onDone(false) })
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text("구글 로그인", style = text(20, FontWeight.Bold))
                    Text("YouTube에서 종소리를 받을 때 쓸 구글 계정으로 로그인해요. 자주 쓰지 않는 계정이어도 괜찮아요.",
                        style = text(13, color = C.grey600))
                    Text("로그인 정보는 이 기기에만 저장하고 다른 곳으로 보내지 않아요.", style = text(12, color = C.grey400))
                }
            }
            if (progress in 1..99) {
                LinearProgressIndicator({ progress / 100f }, Modifier.fillMaxWidth().height(2.dp), color = C.accent, trackColor = C.grey100)
            } else {
                Spacer(Modifier.fillMaxWidth().height(2.dp).background(C.grey100))
            }
            AndroidView(
                factory = { c ->
                    WebView(c).apply {
                        settings.javaScriptEnabled = true
                        settings.domStorageEnabled = true
                        // 앱 안의 창이라고 알리는 표시를 빼서, 일반 휴대폰 브라우저처럼 로그인 화면을 받는다
                        settings.userAgentString = settings.userAgentString.replace("; wv", "").replace(Regex("""Version/[\d.]+ """), "")
                        if (WebViewFeature.isFeatureSupported(WebViewFeature.REQUESTED_WITH_HEADER_ALLOW_LIST)) {
                            WebSettingsCompat.setRequestedWithHeaderOriginAllowList(settings, emptySet())
                        }
                        CookieManager.getInstance().setAcceptCookie(true)
                        CookieManager.getInstance().setAcceptThirdPartyCookies(this, true)
                        webChromeClient = object : WebChromeClient() {
                            override fun onProgressChanged(view: WebView, newProgress: Int) {
                                progress = newProgress
                            }
                        }
                        webViewClient = object : WebViewClient() {
                            override fun onPageFinished(view: WebView, url: String?) = check(url)
                            override fun doUpdateVisitedHistory(view: WebView, url: String?, isReload: Boolean) = check(url)
                        }
                        web = this
                        // 데스크톱의 '전용 프로필'처럼 매번 새로 로그인한다
                        CookieManager.getInstance().removeAllCookies { loadUrl(GoogleLogin.LOGIN_URL) }
                    }
                },
                modifier = Modifier.weight(1f).fillMaxWidth(),
                onRelease = { it.stopLoading(); it.destroy(); web = null },
            )
        }
    }
}

# 안드로이드 앱 진행 기록

마지막 정리: 2026-11-01

데스크톱(2.1.5)과 똑같이 쓰도록 안드로이드 앱을 `android/` 폴더에 **새로** 만들고 있어요.
예전 앱 `AndroidStudioProjects/Mataf/`는 참고만 했고 빌드에는 쓰지 않아요. 아이콘만 예전 앱 것을 그대로 써요.

## 지금 상태 한눈에

| 항목 | 상태 | 비고 |
|---|---|---|
| 앱 뼈대·자동 빌드(CI) | 완료 | `.github/workflows/android.yml` |
| 종 울리기 핵심 | 완료 | 정확 알람, 부팅 뒤 다시 걸기, 앞에서 도는 서비스 |
| 홈 / 시간표 / 종소리 / 기록 / 설정 화면 | 완료 | 휴대폰은 아래 탭, 태블릿(가로 840dp 이상)은 왼쪽 메뉴 |
| 전체화면 시계 | 완료 | 어둡게/밝게, 다음 종 원, 남은 종 카드, 날씨 |
| YouTube·SoundCloud 찾아서 받기 | 완료 | YouTube가 막는 네트워크에서는 구글 로그인이 필요해요. 아래 "YouTube 봇 확인과 구글 로그인" |
| YouTube 구글 로그인 | 완료 (2.1.6) | 에뮬레이터에서 로그인 → 받기·미리 듣기·다듬기 확인 |
| 종소리 다듬기(편집기) | 완료 | CI·로컬 빌드 통과 |
| 날씨·지역 검색 | 완료 | 에뮬레이터에서 확인 |
| 백업/불러오기·시간표 CSV | 완료 | 데스크톱과 서로 주고받기 확인 |
| 앱 자동 업데이트 | 완료 | 2.1.5 → 2.1.6 앱 안에서 받아 설치까지 에뮬레이터에서 확인 |
| 업데이트 기록 보기 | 완료 | `android/CHANGELOG.md` |
| 예전 앱 데이터 옮기기 | 안 함(선택) | 아래 "남은 일" 4번 |
| 실제 기기 시험 | **아직** | 에뮬레이터(Android 15, Pixel 7)에서만 확인 |

## 2026-11-01에 에뮬레이터에서 확인한 것

- 설정: 날씨 지역 바꾸기, 백업·업데이트·정보 카드, 업데이트 확인(GitHub에 물어서 "최신 버전이에요"), 업데이트 기록 창
- 지역 검색: 영문 동네 이름 검색, 결과 고르기 → 설정에 저장. 물리 키보드 Enter = 검색
- 전체화면 시계: 세로·가로, 어둡게·밝게, 지금 날씨·시간별 예보·출처, 날씨를 누르면 지역 창
- 백업: 안드로이드 백업 → 데스크톱 코드로 불러오기, 데스크톱 백업(세트·일정·음량) → 안드로이드 불러오기
- 시간표 CSV: 데스크톱이 만드는 파일과 바이트까지 같음
- 업데이트 직후 '새로워진 점' 창 (설정값을 흉내 내서)
- 앱 안 업데이트: 2.1.5 릴리스 APK를 깔고 열면 2.1.6을 찾아 받고(SHA-256 확인) '설치 준비 완료'.
  '업데이트' → 처음 한 번 '이 출처 허용' → 안드로이드 설치 확인 창 → 2.1.6. 처음 설치 시각·데이터 그대로, 다시 열면 '새로워진 점' 창
- 확인 못 한 것: 한글 주소 검색(에뮬레이터 입력이 영문만 돼서), 실제 종 울림

## YouTube 봇 확인과 구글 로그인 (2026-11-01 조사)

- 이 PC가 있는 네트워크(IP)에서는 YouTube가 로그인 없는 요청을 모두 "로그인하여 봇이 아님을 확인하세요"로 막아요.
  클라이언트 7가지(tv_samsung, tv, visionos, android_vr, ios, web, web_embedded)를 직접 물어봤고, PO 토큰을 붙인 web/mweb도 막혔어요.
  **데스크톱도 같은 IP에서 똑같이 막히고**(`%APPDATA%\MaplTajong\youtube.log`), 구글 로그인 뒤에야 받아져요.
- NewPipeExtractor 릴리스 v0.26.5는 Android 클라이언트를 반드시 먼저 쓰는데, NewPipe가 dev에서 "고장 난 클라이언트"로 뺐어요.
  그래서 NewPipe 앱 dev가 쓰는 커밋 `e8f89145a`(visionOS만 씀)로 올렸어요 (`app/build.gradle.kts`). 막히지 않은 네트워크에서 확인 필요.
- 이 추출기로는 지금 YouTube 플레이어(11a45ffb)의 **서명·n 파라미터 풀기가 둘 다 실패**해요(JVM으로 시험).
  그래서 n·서명은 yt-dlp와 같은 풀이 스크립트로 직접 풀어요 (아래).
- 로그인한 채로 시험한 결과 (에뮬레이터, 같은 IP):
  - `tv_samsung`(TVHTML5 5.x) + 쿠키 + 세션 값 → **통과**. n만 풀면 받아져요 (n을 안 풀면 403).
  - visionOS + 쿠키 → HTTP 400 / tv(7.x) → "페이지를 새로고침해야 합니다" / web → 주소 없는(SABR) 형식만 / web_embedded → "볼 수 없습니다".
- 만든 것:
  - `core/GoogleLogin.kt`: 쿠키 저장(`filesDir/youtube_cookies.txt`), SAPISIDHASH 인증 헤더(yt-dlp와 같은 방식, `_u` 세션 포함)
  - `ui/screens/GoogleLoginScreen.kt`: 앱 안 WebView 로그인 창. 앱 표시(`; wv`, X-Requested-With)를 빼서 일반 브라우저처럼 보이게 함.
    에뮬레이터에서 실제 구글 계정 로그인까지 됐어요.
  - `core/Online.kt` `resolve(ctx, url)`: 로그인했으면 먼저 watch 페이지의 ytcfg(VISITOR_DATA, DATASYNC_ID, SESSION_INDEX)를 읽고
    `tv_samsung`으로 묻고, 안 되면 로그인 없이(NewPipe). 실패만 `filesDir/youtube.log`에 남겨요.
    막히면 데스크톱과 같은 문구("YouTube가 이 기기의 자동 다운로드를 막았어요. 구글 로그인을 하면 받을 수 있어요.").
  - `core/JsChallenge.kt`: yt-dlp의 풀이 스크립트(`assets/ejs`, yt-dlp/ejs **0.8.0**, Unlicense)를 JavaScriptSandbox(V8)에서 돌려 n·서명을 풀어요.
    플레이어는 iframe_api에서 번호를 찾아 `player_ias.vflset/en_US/base.js`를 받고, 분석 결과를 `filesDir/ejs/<번호>.js`에 보관(다음부터 빠름).
    Android System WebView가 너무 오래돼 JavaScriptSandbox가 없으면 "WebView를 업데이트해 주세요"라고 알려요.
  - 찾기 화면: 위쪽 "구글 로그인"/"구글 로그인됨", 막혔을 때 "구글 로그인" 버튼 → 로그인 뒤 하던 일 다시. 설정 → 정보 카드에 "YouTube 구글 로그인" 줄.
- 확인한 것 (에뮬레이터, 로그인): 바로 추가(1:05 영상 전체), 다른 영상 미리 듣기(약 7초), 받아서 다듬기(파형까지), SoundCloud 미리 듣기.
- **YouTube가 플레이어를 바꿔 n 풀기가 깨지면**: yt-dlp가 요구하는 ejs 버전(`pyproject.toml`의 `yt-dlp-ejs==`)을 보고,
  그 버전의 `yt.solver.lib.min.js`·`yt.solver.core.min.js`를 GitHub 릴리스(yt-dlp/ejs)에서 받아
  yt-dlp `jsc/_builtin/vendor/_info.py`의 SHA3-512와 맞춘 뒤 `assets/ejs`에 바꿔 넣어요. TV 클라이언트 버전 값도 yt-dlp `_base.py`를 따라가요.

## 로컬에서 빌드하기

- 이 PC에 준비해 둔 것: JDK 17(`C:\Program Files\Eclipse Adoptium\jdk-17...`), Android SDK `C:\Android\Sdk`, 에뮬레이터 `mago`(`C:\Android\.android\avd`).
- **사용자 폴더 이름에 한글이 있어서** 저장소를 영문 드라이브로 연결해서 빌드해요:
  `subst M: "%USERPROFILE%\Documents\Mago\Mapl-Tajong"` → `cd M:\android` → `gradlew assembleDebug`.
  환경 변수: `JAVA_HOME`(JDK 17), `ANDROID_HOME=C:\Android\Sdk`, `GRADLE_USER_HOME=C:\Android\gradle-home`.
  JDK 25로 돌리면 Gradle 8.11이 "25.0.3" 오류로 멈춰요.
- `android/local.properties`에 `sdk.dir=C\:\\Android\\Sdk` (git에는 안 올라가요).
- Android Studio를 쓸 때도 `M:\android`를 여는 게 안전해요.
- 버전은 `android/version.properties`(versionName, versionCode) 한 곳에서 바꿔요.
- 패키지 이름은 예전 앱과 같은 `com.milky.mataf`. 서명 키가 다르면 예전 앱을 지우고 설치해야 해요.

### 서명 키
- 2026-11-01에 배포용 키를 새로 만들었어요: `Documents\Mago\android-signing\mapltajong-release.jks` (별칭 `mapltajong`, 비밀번호는 같은 폴더 `password.txt`).
  인증서 SHA-256 `72:C4:EB:6B:E1:54:33:C8:CF:CD:3B:70:64:AE:04:90:34:24:A1:41:26:DD:06:1B:73:30:54:E7:77:5F:FC:DA`.
- 같은 값이 GitHub 저장소 비밀값 `ANDROID_KEYSTORE_BASE64`, `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS`, `ANDROID_KEY_PASSWORD`에 들어 있어요.
- **이 키를 잃어버리면 설치된 앱을 더는 자동 업데이트할 수 없어요.** 폴더를 다른 곳에도 따로 보관하고, 저장소에는 절대 넣지 않아요.
- 예전 앱은 다른 키(`CN=Hyunmin Koo`, 파일 못 찾음)로 서명돼 있어서, 예전 앱이 깔린 기기는 한 번 지우고 새로 설치해야 해요.
- 로컬에서도 환경 변수(`ANDROID_KEYSTORE_FILE`, `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS`, `ANDROID_KEY_PASSWORD`)를 주면 이 키로 서명해요. 없으면 시험용(디버그) 키예요.

### 배포
- `dev/**` 브랜치에 `android/`가 바뀌면 CI가 APK를 빌드해서 Actions 결과물로 올려요(배포는 안 함).
- **main에 `android/`가 바뀌어 올라오면**, `version.properties`의 버전이 아직 릴리스되지 않았을 때만 CI가 빌드해서
  GitHub Release `android-vX.Y.Z`에 APK(`MaplTajong-X.Y.Z.apk`)와 sha256을 올려요. 이미 있는 버전이면 빌드만 해요.
  → 새 버전을 내려면 `version.properties`(versionName, versionCode 둘 다 올리기)와 `CHANGELOG.md`를 고쳐서 main에 넣으면 돼요.
- `release/android-vX.Y.Z` 브랜치나 `android-vX.Y.Z` 태그로도 배포할 수 있어요. 이름과 `version.properties`의 버전이 다르면 멈춰요.
- 배포용 서명 키 비밀값이 없으면 배포하지 않고 멈춰요. 릴리스 노트는 `android/CHANGELOG.md`의 같은 버전 항목이에요.
- 안드로이드 릴리스는 `--latest=false`로 올려서 데스크톱 "최신 릴리스"를 가리지 않아요. 데스크톱 업데이트는 설치 파일 이름으로만 릴리스를 고르니까 섞여도 괜찮아요.

## 파일 지도 (`android/app/src/main/java/com/milky/mataf/`)

| 파일 | 하는 일 |
|---|---|
| `MatafApp.kt` | 앱 시작: 알림 채널, 기본 종소리(bell1~8) 복사(뒤에서), 다음 종 걸기 |
| `MainActivity.kt` | 화면 시작, 알림 권한 한 번 묻기, 돌아올 때 다음 종 다시 걸기·업데이트 확인(6시간마다) |
| `FullscreenActivity.kt` | 전체화면 시계 (화면 꺼짐 방지, 3초 뒤 버튼 숨김, 날씨) |
| `data/Db.kt` | SQLite `tajong.db` — **데스크톱과 같은 표 구조** (백업 호환 때문) |
| `data/Repo.kt` | 읽기/쓰기 전부 (설정, 종소리, 세트, 일정, 한 번만 건너뛰기/울림, 쉬는 날, 기록) |
| `data/TimeUtil.kt` | 요일 비트(월=1 … 일=64), 오전/오후, 남은 시간 글자 |
| `core/Scheduler.kt` | 다음 종·오늘 목록 계산 (데스크톱 scheduler.py와 같은 규칙), 건너뛰기/지금 울리기/되돌리기 |
| `core/Alarms.kt` | 다음 종 하나만 `setAlarmClock`으로 걸기, 알람 받는 곳, 부팅/시간 변경 받는 곳 |
| `core/BellService.kt` | 종 울리는 동안 앞에서 도는 서비스. 120초 넘게 늦으면 '놓침'으로 기록 |
| `core/Sounds.kt` | 종소리 파일 관리, 재생기(100% 넘는 음량은 LoudnessEnhancer), 미리 듣기 |
| `core/Online.kt` | YouTube·SoundCloud 검색, 소리 주소 찾기(구글 로그인 → 로그인 없이 순서), 받기(나눠 받기 / HLS), `youtube.log` |
| `core/GoogleLogin.kt` | YouTube 구글 로그인 쿠키 저장·로그아웃, SAPISIDHASH 인증 헤더 |
| `core/JsChallenge.kt` | YouTube 주소의 n·서명 풀기 (yt-dlp/ejs 스크립트를 JavaScriptSandbox에서) |
| `core/AudioEdit.kt` | MediaCodec으로 풀어서 파형 만들기, 자르기·페이드·음량·크기 맞춤 → WAV 저장, 원본 보관 |
| `core/Weather.kt` | MET Norway 예보(Expires/Last-Modified, `weather.json` 보관), Nominatim 지역 검색(1초 간격, 도로명 structured 먼저) |
| `core/Backup.kt` | 데스크톱 backup.py 그대로: zip(`manifest.json`+`data.json`+`sounds/`), 불러오기, 시간표 CSV |
| `core/Updater.kt` | `Updater`: 릴리스 확인·받기·SHA-256·PackageInstaller 설치, `Updates`: 상태 흐름(데스크톱 update_manager.py), `InstallReceiver` |
| `ui/App.kt` | 탭/왼쪽 메뉴, 찾기·다듬기 화면 열기, 알림(토스트), 업데이트 직후 '새로워진 점' |
| `ui/theme/Theme.kt` | 데스크톱과 같은 색, Pretendard 글꼴 |
| `ui/components/` | 버튼·카드·스위치·시각 고르기·시트·확인 창·썸네일·날씨 그림(`WeatherIcon.kt`) 등 공통 부품 |
| `ui/screens/` | 홈, 시간표, 종소리, 기록, 설정, 찾기, 다듬기, 지역 고르기(`PlaceSheet`), 업데이트 기록(`ChangelogSheet`), 구글 로그인(`GoogleLoginScreen`) |

`android/CHANGELOG.md`는 빌드할 때 `copyChangelog` 작업이 앱 assets로 넣어요 (`app/build.gradle.kts`).

## 남은 일 (하면 좋은 순서)

1. **막히지 않은 네트워크에서 로그인 없이 YouTube 받기 확인** — 휴대폰 데이터 등. NewPipeExtractor dev 커밋(visionOS)이 실제로 되는지.
2. **실제 기기 시험** — 아래 "기기에서 꼭 확인할 것".
3. **다음 업데이트(2.1.6 → 2.1.7) 확인** — 설치기를 이 앱으로 기록했으니(installer=com.milky.mataf) 확인 창 없이 설치되는지.
   설치가 끝나면 앱은 닫힌 채로 있어요(안드로이드 10부터 앱이 뒤에서 화면을 열 수 없음). 종 예약은 `BootReceiver`가 다시 걸어요.
   자동 설치 안내(`Updates.tryAutoInstall`)도 "앱이 닫혀도 종은 그대로 울려요"로 맞춰 두었어요.
   로컬 디버그 빌드는 서명이 달라서 릴리스 APK 위에 덮어 설치할 수 없어요.
4. **예전 앱 데이터 옮기기(선택)** — 예전 앱은 `mataf.db`(다른 표 구조: `volume_percent`, hour/minute 따로)와 `filesDir/sounds`. 요일 비트는 같아요. 같은 키로 서명해야 예전 데이터에 접근할 수 있어요.

## 기기에서 꼭 확인할 것

- 처음 실행: 기본 종소리 8개가 생기는지, 알림 권한을 한 번 묻는지.
- 설정 → "알람 및 리마인더" 허용, "배터리 사용량 최적화 제외".
- 1~2분 뒤로 일정을 만들고 화면을 끈 채로 정확히 울리는지, 알림의 "정지"가 되는지.
- 재부팅 뒤에도 울리는지.
- 홈: 다음 종 지금 울리기 / 건너뛰기 / 되돌리기 / 오늘 쉬기, 오늘 목록의 "울리기"·"제때 울리기".
- 찾기: YouTube·SoundCloud 검색, 썸네일, 미리 듣기(앞 30초), 바로 추가, 받아서 다듬기.
  YouTube가 막히면 `Online.explain()` 메시지가 떠요. NewPipeExtractor 버전을 올리면 고쳐지는 경우가 많아요(`app/build.gradle.kts`).
- 다듬기: 파형이 뜨는지(특히 webm/opus, m4a), 손잡이 끌기, 길게 눌러 그 자리부터 듣기, 저장·덮어쓰기·원본으로.
- 날씨: 한글 주소(예: 서울 강남구 테헤란로 152) 검색, 전체화면 시계를 오래 켜 둘 때 10분마다 갱신.
- 전체화면 시계를 처음 열 때 화면이 잠깐 까맣게 남는지 (에뮬레이터에서 '전체 화면 보기' 안내를 닫은 직후 한 번 그랬어요).
- 태블릿 가로 화면: 왼쪽 메뉴, 홈 두 칸 배치, 전체화면 시계 배치.

## 정해 둔 것

- 커밋 작성자는 구현민. 커밋·PR·브랜치 이름·파일 어디에도 AI 도구 표기를 넣지 않아요.
- 큰 기능을 새로 넣을 때는 먼저 물어보기.
- 업데이트를 배포하면 임시 브랜치를 정리하고 main으로 PR을 올려요.

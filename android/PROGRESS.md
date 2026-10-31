# 안드로이드 앱 진행 기록

마지막 정리: 2026-10-31 · 브랜치 `claude/pensive-bell-vwybqx` → `main`

데스크톱(2.1.5)과 똑같이 쓰도록 안드로이드 앱을 `android/` 폴더에 **새로** 만들고 있어요.
예전 앱 `AndroidStudioProjects/Mataf/`는 참고만 했고 빌드에는 쓰지 않아요. 아이콘만 예전 앱 것을 그대로 써요.

## 지금 상태 한눈에

| 항목 | 상태 | 비고 |
|---|---|---|
| 앱 뼈대·자동 빌드(CI) | 완료 | `.github/workflows/android.yml` |
| 종 울리기 핵심 | 완료 | 정확 알람, 부팅 뒤 다시 걸기, 앞에서 도는 서비스 |
| 홈 / 시간표 / 종소리 / 기록 / 설정 화면 | 완료 | 휴대폰은 아래 탭, 태블릿(가로 840dp 이상)은 왼쪽 메뉴 |
| 전체화면 시계 | 완료(날씨 빼고) | 어둡게/밝게, 다음 종 원, 남은 종 카드 |
| YouTube·SoundCloud 찾아서 받기 | 완료 | 로그인 없음 (NewPipeExtractor) |
| 종소리 다듬기(편집기) | 코드 완료, **빌드 확인 전** | 마지막 커밋에서 CI 결과를 보지 않고 올렸어요 |
| 날씨·지역 검색 | 안 함 | 아래 "남은 일" 1번 |
| 백업/불러오기 | 안 함 | 2번 |
| 앱 자동 업데이트 | 안 함 | 3번 |
| 업데이트 기록 보기 | 안 함 | 4번 |
| 예전 앱 데이터 옮기기 | 안 함(선택) | 5번 |
| 실제 기기 시험 | **한 번도 안 함** | CI에서 빌드만 확인 |

CI 빌드 결과: 1단계(화면들)와 찾아서 받기까지는 빌드 통과. 편집기와 아이콘 바꾼 커밋은 확인하지 않았어요.
빌드가 깨져 있으면 `SoundEditorScreen.kt`, `AudioEdit.kt`부터 보면 돼요.

## 로컬에서 빌드하기

- Android Studio(Ladybug 이상)로 `android/` 폴더를 열어요. (저장소 최상위가 아니라 `android/`)
- JDK 17, Android SDK 35 필요.
- 명령어로: `cd android` → `./gradlew assembleDebug` → `app/build/outputs/apk/debug/`
- 버전은 `android/version.properties`(versionName, versionCode) 한 곳에서 바꿔요.
- 패키지 이름은 예전 앱과 같은 `com.milky.mataf`. 서명 키가 다르면 예전 앱을 지우고 설치해야 해요.

### 서명 키
- 예전 앱은 `CN=Hyunmin Koo` 키로 서명돼 있어요. 키 파일(.jks/.keystore) 위치를 아직 못 찾았어요.
  - Android Studio → Build → Generate Signed Bundle/APK 화면의 "Key store path"에 마지막으로 쓴 경로가 보여요.
- 찾으면 GitHub 저장소 Settings → Secrets에 넣어요: `ANDROID_KEYSTORE_BASE64`(파일을 base64로), `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS`, `ANDROID_KEY_PASSWORD`.
- 비밀값이 없으면 CI는 시험용(디버그) 키로 서명해요. 로컬에서도 같은 환경 변수(`ANDROID_KEYSTORE_FILE` 등)를 주면 그 키로 서명해요.

### 배포
- `release/android-vX.Y.Z` 브랜치를 만들면 CI가 빌드해서 GitHub Release `android-vX.Y.Z`에 APK와 sha256을 올리고 브랜치를 지워요.
  브랜치 이름과 `version.properties`의 버전이 다르면 멈춰요.
- 안드로이드 릴리스는 `--latest=false`로 올려서 데스크톱 "최신 릴리스"를 가리지 않아요. 데스크톱 업데이트는 설치 파일 이름으로만 릴리스를 고르니까 섞여도 괜찮아요.

## 파일 지도 (`android/app/src/main/java/com/milky/mataf/`)

| 파일 | 하는 일 |
|---|---|
| `MatafApp.kt` | 앱 시작: 알림 채널, 기본 종소리(bell1~8) 복사(뒤에서), 다음 종 걸기 |
| `MainActivity.kt` | 화면 시작, 알림 권한 한 번 묻기, 돌아올 때 다음 종 다시 걸기 |
| `FullscreenActivity.kt` | 전체화면 시계 (화면 꺼짐 방지, 3초 뒤 버튼 숨김) |
| `data/Db.kt` | SQLite `tajong.db` — **데스크톱과 같은 표 구조** (백업 호환 때문) |
| `data/Repo.kt` | 읽기/쓰기 전부 (설정, 종소리, 세트, 일정, 한 번만 건너뛰기/울림, 쉬는 날, 기록) |
| `data/TimeUtil.kt` | 요일 비트(월=1 … 일=64), 오전/오후, 남은 시간 글자 |
| `core/Scheduler.kt` | 다음 종·오늘 목록 계산 (데스크톱 scheduler.py와 같은 규칙), 건너뛰기/지금 울리기/되돌리기 |
| `core/Alarms.kt` | 다음 종 하나만 `setAlarmClock`으로 걸기, 알람 받는 곳, 부팅/시간 변경 받는 곳 |
| `core/BellService.kt` | 종 울리는 동안 앞에서 도는 서비스. 120초 넘게 늦으면 '놓침'으로 기록 |
| `core/Sounds.kt` | 종소리 파일 관리, 재생기(100% 넘는 음량은 LoudnessEnhancer), 미리 듣기 |
| `core/Online.kt` | YouTube·SoundCloud 검색, 소리 주소 찾기, 받기(나눠 받기 / HLS) |
| `core/AudioEdit.kt` | MediaCodec으로 풀어서 파형 만들기, 자르기·페이드·음량·크기 맞춤 → WAV 저장, 원본 보관 |
| `ui/App.kt` | 탭/왼쪽 메뉴, 찾기·다듬기 화면 열기, 알림(토스트) |
| `ui/theme/Theme.kt` | 데스크톱과 같은 색, Pretendard 글꼴 |
| `ui/components/` | 버튼·카드·스위치·시각 고르기·시트·확인 창·썸네일 등 공통 부품 |
| `ui/screens/` | 홈, 시간표, 종소리, 기록, 설정, 찾기(`SearchScreen`), 다듬기(`SoundEditorScreen`) |

## 남은 일 (하면 좋은 순서)

1. **날씨 + 지역 검색** — 데스크톱 `app/core/weather.py`, `app/ui/place_dialog.py`, `app/ui/weather_icons.py`, `app/ui/fullscreen_clock.py`(`_WeatherNow`, `_HourlyStrip`)를 그대로 옮기면 돼요.
   - 날씨: MET Norway Locationforecast 2.0 compact, User-Agent 필수, 응답의 `Expires`/`Last-Modified` 지키기(최소 15분 간격), 마지막 예보를 파일로 보관.
   - 지역: OpenStreetMap Nominatim, **1초에 한 번 이하, 검색 버튼(엔터)을 눌렀을 때만**. 도로명주소는 structured 검색(street/city/state) 먼저 → 거꾸로 쓴 주소 → 그대로, 건물 번호가 맞는 결과를 먼저. 좌표 직접 입력도 받기.
   - 설정 값: `weather_place`(JSON `{name, lat, lon}`), 예전 값 `weather_city`도 읽기. 이미 있는 설정: `weather_on`, `fs_theme`.
   - 화면 아래에 "날씨 정보: 노르웨이 기상청(MET Norway)", 지역 검색에 "© OpenStreetMap 기여자" 표시.
2. **백업/불러오기** — 데스크톱 `app/core/backup.py`와 같은 zip(`manifest.json` + `data.json` + `sounds/`). 설정 화면에 카드 추가. 파일은 SAF(CreateDocument/OpenDocument)로.
3. **앱 자동 업데이트** — GitHub Releases에서 `android-v*` 찾기 → APK와 `.sha256` 받기 → 확인 → 설치 화면 열기.
   매니페스트에 `REQUEST_INSTALL_PACKAGES`, FileProvider(`${applicationId}.files`, `res/xml/file_paths.xml`)는 이미 넣어 뒀어요.
4. **업데이트 기록 보기** — 최상위 `CHANGELOG.md`를 빌드할 때 assets로 복사(gradle 작업)해서 설정 화면에서 보여 주기. 안드로이드용 항목도 CHANGELOG에 써야 해요.
5. **예전 앱 데이터 옮기기(선택)** — 예전 앱은 `mataf.db`(다른 표 구조: `volume_percent`, hour/minute 따로)와 `filesDir/sounds`. 요일 비트는 같아요. 같은 키로 서명해야 예전 데이터에 접근할 수 있어요.

## 기기에서 꼭 확인할 것

- 처음 실행: 기본 종소리 8개가 생기는지, 알림 권한을 한 번 묻는지.
- 설정 → "알람 및 리마인더" 허용, "배터리 사용량 최적화 제외".
- 1~2분 뒤로 일정을 만들고 화면을 끈 채로 정확히 울리는지, 알림의 "정지"가 되는지.
- 재부팅 뒤에도 울리는지.
- 홈: 다음 종 지금 울리기 / 건너뛰기 / 되돌리기 / 오늘 쉬기, 오늘 목록의 "울리기"·"제때 울리기".
- 찾기: YouTube·SoundCloud 검색, 썸네일, 미리 듣기(앞 30초), 바로 추가, 받아서 다듬기.
  YouTube가 막히면 `Online.explain()` 메시지가 떠요. NewPipeExtractor 버전을 올리면 고쳐지는 경우가 많아요(`app/build.gradle.kts`).
- 다듬기: 파형이 뜨는지(특히 webm/opus, m4a), 손잡이 끌기, 길게 눌러 그 자리부터 듣기, 저장·덮어쓰기·원본으로.
- 태블릿 가로 화면: 왼쪽 메뉴, 홈 두 칸 배치, 전체화면 시계 배치.

## 정해 둔 것

- 커밋 작성자는 구현민, Claude 표기는 넣지 않아요.
- 큰 기능을 새로 넣을 때는 먼저 물어보기.
- 업데이트를 배포하면 임시 브랜치를 정리하고 main으로 PR을 올려요.

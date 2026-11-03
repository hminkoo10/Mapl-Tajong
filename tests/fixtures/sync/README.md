# PC ↔ Android 동기화 호환 시험

## Fixture 출처

- `pc/`: `tests.test_sync_compat.pc_documents()`가 실제 SQLite에서
  `build_config` / `build_state`로 만든 뒤 PC `dumps_signed`로 서명한 바이트.
- `android/`: JVM `SyncCompatibilityTest.androidDocuments()`가 실제 Android
  `configFile` / `stateFile` / `signedJson`으로 만든 바이트.
  이 builder들은 `Cloud.buildConfig` / `buildState`가 사용하는 함수다.
  config의 입력 행은 PC fixture의 동일한 SQLite 열 값이며, state는 JVM에서 별도로 만든다.
- `phone-2.2.7/`: 제공된 휴대폰 원본 파일 그대로 복사. `meta` / `sig` 포함.
  원본 SHA-256:
  - config: `e2e872f39bb169f2de31e4c877a87c7a4dd0b4da1c1cbf1a5f80357861f67e2d`
  - state: `ed6b3bea014767a89dc2c59646c2aec8bc8b478b59d2e01020b8fa39f178f221`
- 테스트 키: `sync-compat-test-key-한글-only` (실제 계정 키 아님).
  휴대폰 원본 서명은 키가 없어 검증하지 않는다. 원본 payload 적용과 양방향 테스트 키 서명 검증을 분리한다.
- 고정된 오늘은 `2026-11-03`. 날짜가 지나도 fixture가 만료되지 않도록 테스트 시각을 고정한다.
  `paused` → `day` → `resumed`는 잠시 멈춤 해제와 오늘 쉬기 해제를 별도로 시험한다.
  `ring_at`은 `.257Z` / `.000Z`, 요청은 일정 지정 / 소리 직접 지정 모두 포함한다.
- 서명은 공백·줄바꿈까지 포함하므로 `.gitattributes`에서 JSON 줄바꿈 변환을 금지한다.

## 검증 범위

- PC→Android: 원본 바이트 파싱, config/state sanitizer 전후 내용 동등성,
  SQLite 입력 열 투영, `parseState` / `referencedState` / `sharedOverrides` 후 내용 동등성.
- Android→PC: 실제 `apply_config` / `apply_state`로 SQLite에 적용하고 builder로 되읽어 모든 공유 값을 비교.
- 양방향 HMAC, 다른 키/바이트 변경 거부, 무서명 최초 수용 및 서명 이후 거부,
  `ring_at` 없는 구버전 요청의 `at` 대체 규칙.
- PC 실제 `QFileSystemWatcher` + 원자적 파일 교체 → DB → 스케줄러 캐시/다음 종 재계산 → 홈 버튼/토글 갱신.
  폴링 타이머는 꺼서 watcher만으로 증명. 재전송 없음, 파일 재감시도 확인.
- Android 서명 fixture의 요청 → PC 재생 호출: `.257Z`는 257ms 타이머,
  `.000Z`는 즉시 처리, 각각 한 번만 재생 호출. 오디오 출력은 mock이다.
- Android JVM에서는 새 서버 revision의 APPLY/NONE 판단과 다음 날짜 계산을 시험한다.
  실제 Android SQLite / AlarmManager / SSE 연결 / Compose 렌더링은 실행하지 않았다.

## 트리거 코드 추적

| 방향 | 연결된 경로 |
| --- | --- |
| Android 로컬 변경→서버 | `Scheduler.setPaused` / `Repo.setPauseDay` → `DataChanges.STATE` → `Cloud.onDataChanged` → `exportState` → 업로드 |
| 서버→PC | 런처의 파일 전달 → `CloudSync._on_fs` → `check_files` → `_read`(서명) → `_apply` → `remote_applied` → `AppContext.remote_changed` → `invalidate/recompute_next` → `DashboardPage._on_data_changed` |
| PC 로컬 변경→서버 | 홈 동작 → `AppContext.changed` → `CloudSync.local_changed` → `_export` → 런처 업로드 |
| 서버→Android | `CloudEvents` 연결/hello/change → `requestPull` → `pull/pullState` → `fetchJson`(서명 후 sanitize) → `applyState` → `Alarms.reschedule` + `AppEvents.changed` → 홈 `version` 수집 |

Android `Alarms.reschedule`은 paused면 알람 취소, PAUSE_DAY면 `Scheduler.next`에서 그 날짜를 건너뛴다.
PC의 실제 자동 울림도 `tick`에서 paused / PAUSE_DAY를 검사한다.
서버 알림은 다른 기기 변경만 받고, 재연결 시에도 pull한다.
Android 화면이 닫혔을 때는 로그인 + 이 기기 울림 설정이 켜진 경우 CloudService가 연결을 유지한다.
PC 런처의 실제 전송, 실기기 백그라운드 서비스, 원본 계정 키 일치는 이 오프라인 테스트로 증명하지 않는다.

## 재현된 차이와 수정

1. PC `recompute_next`는 PAUSE_DAY를 무시해 쉬는 날의 다음 종/카운트다운을 계속 선택했다.
   Android `Scheduler.next`처럼 날짜를 제외하도록 수정. 테스트에서 11/3 10:00 → 11/4 09:00으로 바뀜.
2. PC 원격 요청의 `mark_schedule_fired`는 PAUSE_DAY / SKIP_ONCE / FIRED_ONCE를 무시하고
   그 일정의 날짜를 선택했다. Android `Scheduler.nextDateOf`처럼 다음 유효 차례에만 FIRED_ONCE를 기록하도록 수정.
   8일 안에 차례가 없으면 수동 재생은 허용하되 임의의 오늘 FIRED_ONCE는 만들지 않는다.

파일 형식·정상 값 검증·서명 알고리즘의 비호환은 재현되지 않았다.
휴대폰 샘플은 일정이 없고 PAUSE_DAY도 없으므로, 두 후속 처리 차이가 테스터의 원래 연결 실패 원인이라고 단정하지 않는다.

## 전체 실행 결과 (2026-11-03)

- PC: 요청된 Python 환경에서 `-m unittest discover -s tests -t .` → **136개, 134 통과 / 2 skip**, 실패 없음. 신규 10개 전부 통과.
- Android: JDK `17.0.20.101-hotspot`, SDK `C:\Android\Sdk`에서
  `gradlew.bat testDebugUnitTest -Pandroid.overridePathCheck=true -Dorg.gradle.jvmargs=-Xmx4g`
  → **70개 전부 통과** (JUnit XML 합산). 신규 9개 전부 통과.
- `git diff --check` 통과. `Updater.kt` / `SoundsScreen.kt` 수정 없음. 커밋·푸시 없음.

## 재생성

정상 테스트는 golden 파일을 변경하지 않는다. 프로토콜 변경 검토 시에만 재생성한다.
아래 `$python`은 프로젝트 의존성이 설치된 Python 경로다.

```powershell
# 저장소 루트: PC fixture 생성
$env:PYTHONUTF8 = '1'
$env:QT_QPA_PLATFORM = 'offscreen'
& $python -m tests.test_sync_compat --write-pc-fixtures

# Android fixture 생성 (JDK 17 / Android SDK 환경 필요)
$env:TAJONG_WRITE_SYNC_FIXTURES = (Resolve-Path tests/fixtures/sync).Path
Push-Location android
.\gradlew.bat testDebugUnitTest --tests com.milky.mataf.core.SyncCompatibilityTest.androidSnapshotsAreActualBuilderAndSignerOutput '-Pandroid.overridePathCheck=true' '-Dorg.gradle.jvmargs=-Xmx4g' --rerun-tasks
Pop-Location
Remove-Item Env:TAJONG_WRITE_SYNC_FIXTURES

# 양쪽 독립 검증
& $python -m unittest tests.test_sync_compat
Push-Location android
.\gradlew.bat testDebugUnitTest --tests com.milky.mataf.core.SyncCompatibilityTest '-Pandroid.overridePathCheck=true' '-Dorg.gradle.jvmargs=-Xmx4g'
Pop-Location
```

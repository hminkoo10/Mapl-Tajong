# 마고수학학원 타종 프로그램
## 마고수학학원은 킹왕짱 학원입니다.
---
# 장점
- 마고플러스가 굿또임
- 서T가 존재함
- 쌈뽕한 400원 자판기가 존재함
---
# 단점
- 혁T
- 원장님이 중등수학 싫어함
- ***마플할 때 인강이 안 됨!***

---
# 2.0 바뀐 점
- 새 디자인: 회색 바탕 + 주황 포인트, Pretendard 글꼴, 부드러운 화면 전환과 숫자 애니메이션
- 시간표 여러 개를 체크해서 한 번에 바꾸기 (요일·시간 옮기기·종소리·음량·이름·세트 이동, 켜기/끄기, 복제, 삭제)
- YouTube에서 종소리 검색 → 소리만 받아서 바로 추가하거나 다듬어서 추가
- 종소리 다듬기: 파형 보면서 구간 자르기, 페이드 인/아웃, 음량, 크기 자동 맞춤, 원본 되돌리기
- 일정·세트 복제, 백업/불러오기, 시간표·기록 엑셀(CSV) 내보내기
- 교실 화면용 전체화면 시계
- 설치 프로그램 + 자동 업데이트
- 고친 버그: ‘다음 종 건너뛰기’와 ‘지금 울리기’가 실제로 적용되지 않던 문제, 일정에서 쓰는 종소리를 지우면 프로그램이 꺼지던 문제, Python 3.13에서 100% 넘는 음량이 재생되지 않던 문제

## 설치
[Releases](https://github.com/hminkoo10/Mapl-Tajong/releases)에서 `MaplTajong-Setup-x.y.z.exe`를 받아 실행하면 돼요.
- 관리자 권한 없이 내 계정에 설치돼요. (시작 메뉴·바탕 화면 바로가기, 제거 프로그램 포함)
- 시간표와 종소리는 `%APPDATA%\MaplTajong`에 있어서 업데이트하거나 지워도 남아 있어요.
- 예전 `Mataf.exe`를 쓰던 컴퓨터도 설치 파일로 한 번만 설치하면 데이터를 그대로 이어서 써요.

## 자동 업데이트
설치한 프로그램은 6시간마다 GitHub Releases를 확인해요. 새 버전이 있으면 미리 받아 두고(SHA-256 확인),
**다음 종까지 10분 넘게 남았고 소리가 나지 않을 때** 조용히 설치한 뒤 다시 켜져요.
설정 → 업데이트에서 끄거나 바로 설치할 수 있어요.

## 새 버전 내보내기 (개발자용)
1. `app/core/version.py`의 `APP_VERSION`을 올려요. (예: `2.0.1`)
2. `CHANGELOG.md` 맨 위에 `## 2.0.1` 항목을 써요. 이 내용이 릴리스 노트와 ‘새로워진 점’이 돼요.
3. 커밋하고 `desktop-v2.0.1` 태그를 올려요. (또는 GitHub에서 `release/desktop-v2.0.1` 브랜치를 만들어도 돼요)
   ```
   git tag desktop-v2.0.1
   git push origin desktop-v2.0.1
   ```
4. GitHub Actions가 설치 파일을 만들어 Release에 올리면, 설치된 프로그램들이 알아서 업데이트해요.

## 직접 빌드하기
```
pip install -r requirements.txt
python -m app.main          # 바로 실행
build_exe.bat               # 설치 파일 만들기 (Inno Setup 6.3 이상 필요)
```
결과: `dist\installer\MaplTajong-Setup-x.y.z.exe`

글꼴: [Pretendard](https://github.com/orioncactus/pretendard) (SIL Open Font License 1.1, `app/assets/fonts/Pretendard-LICENSE.txt`)

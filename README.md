# 마고수학학원 타종 프로그램
## 마고수학학원은 킹왕짱 학원입니다.
---
# 장점
- 마고플러스가 굿또임
- 서T가 존재함
- 쌈뽕한 400원 자판기가 존재함
---
# 단점
- 혁T가 나 싫어함
- 원장님이 중등수학 싫어함
- ***마플할 때 인강이 안 됨!***
---
Developed with Vibe Coding

---
# 2.0 바뀐 점
- 새 디자인: 회색 바탕 + 주황 포인트, Pretendard 글꼴, 부드러운 화면 전환과 숫자 애니메이션
- 시간표 여러 개를 체크해서 한 번에 바꾸기 (요일·시간 옮기기·종소리·음량·이름·세트 이동, 켜기/끄기, 복제, 삭제)
- YouTube에서 종소리 검색 → 소리만 받아서 바로 추가하거나 다듬어서 추가
- 종소리 다듬기: 파형 보면서 구간 자르기, 페이드 인/아웃, 음량, 크기 자동 맞춤, 원본 되돌리기
- 일정·세트 복제, 백업/불러오기, 시간표·기록 엑셀(CSV) 내보내기
- 교실 화면용 전체화면 시계
- 고친 버그: ‘다음 종 건너뛰기’와 ‘지금 울리기’가 실제로 적용되지 않던 문제, 일정에서 쓰는 종소리를 지우면 프로그램이 꺼지던 문제, Python 3.13에서 100% 넘는 음량이 재생되지 않던 문제

## 실행 / 빌드
```
pip install -r requirements.txt
python -m app.main
```
Windows 실행 파일은 `build_exe.bat` 를 실행하면 `dist\Mataf.exe` 로 만들어져요.

글꼴: [Pretendard](https://github.com/orioncactus/pretendard) (SIL Open Font License 1.1, `app/assets/fonts/Pretendard-LICENSE.txt`)

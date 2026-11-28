# 매일 동기화 작업 지침 (valuelens.kr)

매일 오전 예약 작업이 이 문서를 따라 블로그 새 글을 사이트에 반영함. `_ops/` 폴더는 밑줄로 시작해 GitHub Pages에 게시되지 않음.

## 자동 실행 (2026.11.23부터)
- 프레디 PC의 Windows 예약 작업 「valuelens사이트갱신」(매일 09:15, 21:15. 2026.11.28에 09:00/21:00에서 옮김: 정각 예약 발행 글이 실행 시점에 아직 목록에 없어 놓친 일 있음)이 `python _ops/auto.py`를 실행함. Claude 예약 작업은 쓰지 않음
- 코드가 하는 일: 목록 페이지(18, 19, 13, 25), 사이트맵, IndexNow, 처리 표시 → main 바로 반영
- DeepSeek가 하는 일: 페이지가 있는 종목의 새 글 → 최신 판단 상자와 글 카드 문장. 코드가 숫자 원문 대조와 원문 복제(45자) 검사를 한 뒤 `auto/<logNo>` PR로 올리고 바로 자동 병합함 (2026.11.25 프레디 요청: 검토 없이 반영). 검사에 실패한 글만 보류
- Claude가 하는 일: 새 종목 페이지(3장)와 보류(pending) 글 처리. 프레디 승인을 기다리지 않고 main에 바로 반영하고 「반영됨」으로만 알림
- 실행 기록: 실행마다 `_ops/logs/auto_YYYY-MM.log`에 시작/종료 시각, 처리 글, 오류를 쌓음 (git 제외, PC에만 있음). bat 단계(git fetch, 파이썬 종료 코드)는 `_ops/logs/bat.log`. 마지막 실행 한 번분은 `G:\내 드라이브\60_투자\valuelens_sync\last_run.log`에도 남김
- 아래 1~4장은 Claude가 직접 처리할 때의 기준으로 계속 씀

## 0. 준비
- main 최신 상태에서 시작: `git fetch origin main && git checkout -B sync-work origin/main`
- 대상 글 조회: `python3 _ops/sync.py list` (기준선 이후 글 중 processed가 false인 것만 처리)

## 1. 글 종류별 처리
| 글 | 처리 | 게시 방식 |
|---|---|---|
| 종목분석, 사이트에 이미 페이지가 있는 종목 | 해당 종목 페이지 갱신 | main에 바로 반영 후 알림 |
| 종목분석, 페이지가 없는 종목(단일 종목 글) | 새 종목 페이지 작성 | main 바로 반영 후 알림 (2026.11.25부터 승인 없음) |
| 저평가 종목 스크린, 공시 정리처럼 여러 종목 글 | 페이지가 있는 종목에는 글 카드 추가, 없는 종목은 보고만 함 | main 바로 반영 |
| 주린이 강의(18), 모의펀드(19), ETF(13), 증권사 리포트 브리핑(25) | `python3 _ops/sync.py lists`로 /lecture/, /fund/, /etf/, /brief/ 목록 페이지를 다시 만듦 (제목, 날짜, 원문 링크만 싣고 본문은 옮기지 않음) | main 바로 반영 |
| 그 밖의 카테고리 | `state.json`의 pending에 사유를 적고 보고만 함 | 없음 |

- LX세미콘은 2026.11.23 새 분석 글이 올라왔으므로 이제 새 종목 페이지 경로로 처리함
- 같은 종목의 과거 글 모으기: `python3 _ops/sync.py find 종목코드 회사명`

## 2. 종목 페이지 갱신 규칙
- 본문 읽기: `python3 _ops/sync.py body LOGNO` 첫머리에서 기준일, KRX 종가, 목표주가, 한 줄 요약, 결론을 뽑음
- 요약은 원문 문장을 옮기지 않고 새로 씀. 글 하나당 1~2문장, 원문 복제는 15% 이하
- 최신 판단 상자: 의견, 핵심 수치, 출처와 기준일(DART 공시일, KRX 종가). 프레디 추정은 「필자 계산」
- 글 카드를 맨 위에 추가하고, 의견이 바뀐 예전 글 카드에는 「당시 판단이며 이후 바뀌었다」를 덧붙임
- 함께 고칠 곳: 상단 note의 글 수와 갱신일, meta description과 og:description, JSON-LD(dateModified, isBasedOn, ItemList 순번)
- 종목 목록 `/stock/index.html`: 해당 종목을 맨 위로 올리고 글 수와 최근일 갱신
- 첫 화면 `/index.html`: 「최근 분석한 종목은?」 10개를 최근 순으로 유지. ul의 class(개편 후 stocks)와 li 마크업은 기존 항목을 그대로 따름
- 새 종목 페이지가 생기면 첫 화면의 종목 수 두 곳(히어로 문장(p.count)의 `<b>숫자</b>개 종목 분석`, 종목분석 카드의 `<p class="big">숫자<small>개 종목</small>`)을 stock 폴더의 종목 페이지 수(index.html 제외)로 갱신
- 원문 제목의 가운데 점(·)은 쉼표로 바꿔 적음 (사이트 전체 규칙)

## 3. 새 종목 페이지
- 파일명 `stock/종목코드.html`, 기존 종목 페이지와 같은 틀(제목, 질문형 소제목 3개, 구조화 데이터, 하단 투자 권유 아님 안내)
- head의 스타일 부분은 고정 틀을 쓰지 말고 main에 있는 기존 종목 페이지 head에서 그대로 복사함. 디자인 개편(PR #2) 병합 후에는 인라인 style 블록 대신 링크 묶음(og:image, theme-color, 고운바탕(Gowun Batang) 폰트, /assets/site.css)을 씀
- head 맨 앞(`<head>` 바로 다음)의 구글 애널리틱스 태그 두 줄도 기존 페이지에서 그대로 복사함. 빠뜨려도 `python3 _ops/sync.py ga`(auto.py 실행 때 자동)가 보완함
- 「OO은 어떤 회사인가요?」는 블로그 원문(그 종목의 글들)에 근거가 있는 내용만 씀. 원문에 없는 일반 정보는 쓰지 않음 (검토 없이 반영하므로)
- 반영 뒤 valuelens.kr에서 페이지가 열리는지 확인

## 4. 마무리
- 목록 페이지: 새 글이 없어도 매일 `python3 _ops/sync.py lists`를 실행 (갱신된 페이지만 파일이 바뀜)
- 사이트맵: `python3 _ops/sync.py sitemap 바뀐주소...` (/ 와 /stock/, 바뀐 목록 페이지 포함)
- 처리 표시: `python3 _ops/sync.py done LOGNO...`
- main 반영분: 커밋 후 main에 push, 1~2분 뒤 https://valuelens.kr 에서 바뀐 페이지 확인
- 게시된 주소 통보: `python3 _ops/sync.py indexnow 주소...` (빙, 네이버 등. 구글은 사이트맵 lastmod로 재수집)
- 새 페이지도 main에 바로 반영한 뒤 같은 방식으로 통보
- 보고: 처리한 글, 반영한 페이지(「반영됨」), 보류(pending) 글을 ~함체 하이픈 불릿으로 짧게 알림. 새 글이 없으면 한 줄로 알림
- 새 페이지가 생긴 날은 Claude가 프레디 브라우저(Claude in Chrome, 서치콘솔 로그인 상태)로 직접 처리함: URL 검사 후 「색인 생성 요청」, Sitemaps에서 https://valuelens.kr/sitemap.xml 재제출. 브라우저 연결이 없으면 보고에 「서치콘솔 처리 못 함」으로 적음

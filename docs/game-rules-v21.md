# 공룡 점프 2.1.0 규칙

2026-09-26 사용자 요청 반영. 현재 규칙은 `shared/game_constants.json`, 고정된 재현 규칙은 `shared/game_constants_v21.json`이다.

## 난이도

단계마다 15초 진행하며 10단계는 게임이 끝날 때까지 유지한다. 8단계부터 속도 증가와 장애물 간격 단축이 커진다. 물리·점프·코인·하트·10분 제한은 기존과 같다.

| 단계 | 시작~종료(초) | 속도(px/s) | 기본 최소 장애물 간격(초) |
|---|---|---|---|
| 1 | 0–15 | 390→450 | 0.95 |
| 2 | 15–30 | 450→530 | 0.88 |
| 3 | 30–45 | 530→620 | 0.80 |
| 4 | 45–60 | 620→710 | 0.74 |
| 5 | 60–75 | 710→800 | 0.68 |
| 6 | 75–90 | 800→880 | 0.62 |
| 7 | 90–105 | 880→940 | 0.58 |
| 8 | 105–120 | 940→1080 | 0.50 |
| 9 | 120–135 | 1080→1200 | 0.44 |
| 10 | 135 이후 | 1200→1320, 150초부터 고정 | 0.40 |

기존 무작위 추가 간격 및 연속 장애물 간격 규칙은 유지한다.

## 부활 감점

- 최종 점수 = `max(0, 시간 점수 + 코인 점수 - 부활 횟수 × 100)`.
- 1회 부활 총 −100점, 2회 총 −200점, 3회 총 −300점이다.
- 부활할 때마다 화면에 이번 감점과 누적 감점을 표시한다.
- 서버가 점프 기록을 재생해 부활 횟수·점수를 직접 계산한다.
- 중간 복원도 같은 규칙으로 재생한다.

## 기존 기록

`2.0.0` 고정 규칙 파일과 기존 점수·접수 기록을 보존한다. 진행 중인 기존 게임은 2.0.0으로 완료할 수 있다. 새로운 게임은 2.1.0을 사용하고 랭킹은 버전별로 집계한다.

## TOP3 안내

현재 N위로 TOP3예요.  
최종 경품 지급 순위는 이벤트 종료 시점에 확정돼요.

## DB 변경 검토

20260926093414 migration은 네 개 CHECK 제약에 2.1.0을 추가한다. 기존 1.2.0/2.0.0 기록 및 권한은 유지한다. 기존 점수와 새 점수는 버전별로 분리된다.

Supabase Advisor에서 dino_dev 관련 경고는 없었다. 변경하지 않은 public 함수·Auth 설정에는 다음 경고가 있어 별도 운영 점검 항목으로 보존한다.

- [public.set_updated_at 검색 경로](https://supabase.com/docs/guides/database/database-linter?lint=0011_function_search_path_mutable)
- [public.rls_auto_enable 익명 실행](https://supabase.com/docs/guides/database/database-linter?lint=0028_anon_security_definer_function_executable) 및 [인증 사용자 실행](https://supabase.com/docs/guides/database/database-linter?lint=0029_authenticated_security_definer_function_executable)
- [Auth 유출 비밀번호 보호](https://supabase.com/docs/guides/auth/password-security#password-strength-and-leaked-password-protection)

## 검증 결과

- Node 162개, Python 189개 전체 통과(생략 없음).
- 부활 0·1·2·3회 감점, 8~10단계 속도·간격, 2.0/2.1 중간 복원, JS/Python 재현 일치, DB 점수·랭킹 버전 격리 검증.
- 원격 부하 테스트는 실행하지 않았다.

## Preview 반영

- 제품 커밋: `d548ec5`, 기존 작업 브랜치 `codex/ranking-ticket-ui`, PR #7.
- 배포: `dpl_FntoNWY3YEBJZkwJgjDs9F9pdLer` (`READY`).
- 테스트 주소: https://google-korea-team-gemini.vercel.app/
- 원격 DB ready, 공개 config의 게임 버전 2.1.0, 변경된 JS/CSS 6개 파일의 원격 내용 일치 확인.
- 합성 참가자 1명으로 접속→예약→시작→종료→잔액 조회 6회 API 확인: 새 버전으로 32점 저장 성공, 무제한 유지, 잔액 미차감. 부하·추첨은 실행하지 않았다.

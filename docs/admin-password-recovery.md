# 관리자 비밀번호 복구

운영 관리자 비밀번호를 처음 만들거나 잊은 경우 `admin.html`에서 이메일 복구 링크를 요청한다. 브라우저에는 Supabase publishable key만 사용하며 서비스 역할 키는 사용하지 않는다.

## Supabase Auth 설정

Supabase Dashboard의 **Authentication → URL Configuration → Redirect URLs**에 아래 주소를 정확히 추가한다.

- `https://google-korea-team-gemini.vercel.app/admin.html`
- 검증할 후보 배포의 정확한 주소: `https://<candidate-deployment>.vercel.app/admin.html`

와일드카드는 사용하지 않는다. 이 프로젝트는 다른 서비스와 Supabase를 공유하므로 기존 Site URL은 변경하지 않는다. 후보 배포가 바뀌면 이전 후보 주소를 제거하고 새 주소를 등록한다.

## 사용자 흐름

1. 관리자 페이지에서 이메일을 입력하고 **비밀번호 만들기·재설정**을 누른다.
2. 화면은 해당 이메일의 가입 여부와 관계없이 같은 확인 문구를 표시한다.
3. 이메일 링크로 돌아오면 페이지가 URL 조각의 복구 토큰을 읽고 주소에서 즉시 제거한다.
4. `/api/admin/session`이 현재 운영 스키마의 활성 관리자임을 확인한 경우에만 새 비밀번호 입력을 허용한다.
5. 12자 이상의 새 비밀번호를 저장하면 기존 관리자 화면을 연다.

복구 토큰은 검증 전후 모두 브라우저의 영구 저장소에 기록하지 않는다. 비밀번호 갱신이 성공한 뒤에만 기존 관리자 로그인과 동일하게 현재 탭의 `sessionStorage`에 접근 토큰을 보관한다.

## 배포 전 수동 확인

- 등록된 운영 관리자 이메일에 복구 메일이 도착한다.
- 링크를 연 직후 주소 표시줄에 `access_token`, `refresh_token`이 남지 않는다.
- 운영 관리자 명단에 없는 Supabase Auth 계정은 새 비밀번호 화면을 사용할 수 없다.
- 새 비밀번호 저장 후 통계와 수령함이 열린다.
- 로그아웃 후 새 비밀번호로 다시 로그인할 수 있다.

복구 메일 발송 자체는 Supabase Auth 메일 설정과 발송 한도의 영향을 받는다. 본행사 전 위 확인을 실제 운영 이메일로 한 번 완료한다.

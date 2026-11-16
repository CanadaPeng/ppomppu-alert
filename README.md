# 뽐뿌 키워드 → 카카오톡 알림

뽐뿌게시판 목록을 10분마다 확인해서 제목에 키워드(기본값 `두유`)가 들어간 새 글이 올라오면, 카카오톡 '나와의 채팅'으로 보내 줍니다.

## 1. 카카오 디벨로퍼스 설정 (developers.kakao.com)
1. 카카오 계정으로 로그인한 뒤 **앱 만들기**를 누릅니다(이름 예시: 뽐뿌알림).
2. **[앱] > [플랫폼 키] > [REST API 키]**
   - REST API 키를 복사해 둡니다.
   - 같은 화면의 **클라이언트 시크릿** 값도 복사해 둡니다.
   - **리다이렉트 URI**에 `https://example.com/oauth`를 등록합니다.
3. **카카오 로그인** 메뉴에서 사용 설정을 **ON**으로 바꿉니다.
4. **카카오 로그인 > 동의항목**에서 **카카오톡 메시지 전송(talk_message)**을 '선택 동의'로 설정합니다.
5. **[앱] > [제품 링크 관리] > [웹 도메인]**에 `https://www.ppomppu.co.kr`과 `https://m.ppomppu.co.kr`을 등록합니다. 이걸 빼면 카톡에서 '글 보기' 버튼이 열리지 않습니다.

## 2. GitHub 저장소 만들기
1. github.com에서 **New repository**를 누르고, 이름(예: ppomppu-alert)을 정한 뒤 **Public**으로 만듭니다. 공개 저장소여야 Actions를 무료로 무제한 쓸 수 있습니다. 토큰은 Secrets에 따로 저장되기 때문에 공개 저장소에는 노출되지 않습니다.
2. **Add file > Upload files**를 누르고, 압축을 푼 폴더 안의 `ppomppu_alert.py`, `README.md`, `.github` 폴더를 끌어다 놓은 뒤 **Commit**합니다.

## 3. GitHub 토큰(PAT) 만들기
오른쪽 위 프로필 > **Settings > Developer settings > Personal access tokens > Fine-grained tokens > Generate new token** 순서로 들어갑니다.
- Repository access: **Only select repositories**를 고르고 방금 만든 저장소를 선택합니다.
- Permissions: **Secrets**와 **Variables**를 둘 다 **Read and write**로 설정합니다.
- 만료일은 길게 잡습니다. 만료되면 새로 발급해서 `GH_PAT` 값을 바꿔 넣으면 됩니다.

## 4. 저장소에 비밀값 넣기
저장소에서 **Settings > Secrets and variables > Actions > Secrets 탭 > New repository secret**을 눌러 아래 세 개를 넣습니다.

| 이름 | 값 |
|---|---|
| `KAKAO_REST_API_KEY` | 1-2에서 복사한 REST API 키 |
| `KAKAO_CLIENT_SECRET` | 1-2에서 복사한 클라이언트 시크릿 |
| `GH_PAT` | 3에서 만든 토큰 |

키워드를 바꾸고 싶다면 **Variables 탭**에서 `KEYWORDS`를 추가합니다(예: `두유,콩물`). 넣지 않으면 기본값 `두유`로 동작합니다.

## 5. 카카오 연결 (1회)
1. 아래 주소에서 `REST_API_키` 부분을 내 키로 바꾼 뒤 브라우저 주소창에 넣습니다.
   `https://kauth.kakao.com/oauth/authorize?client_id=REST_API_키&redirect_uri=https://example.com/oauth&response_type=code&scope=talk_message`
2. 로그인하고 동의하면 `example.com/oauth?code=...` 페이지로 넘어갑니다. 주소창의 주소를 통째로 복사합니다.
3. 바로 저장소의 **Actions** 탭으로 가서 **카카오 최초 연결 (1회)** > **Run workflow**를 누르고, 복사한 주소를 붙여넣은 뒤 실행합니다. 인가 코드는 금방 만료되니 바로 진행해야 합니다.
4. 카카오톡 '나와의 채팅'에 "✅ 연결됐습니다" 메시지가 오면 성공입니다.

## 6. 시작
1. **Actions > 뽐뿌 키워드 알림 > Run workflow**를 눌러 '테스트만 하기'를 체크한 채로 실행합니다. 실행 로그에 뽐뿌 최신 글 제목이 보이면 접속과 읽기가 정상입니다.
2. 이번에는 체크를 해제하고 한 번 더 실행합니다. 카톡으로 "🔔 알림을 시작합니다"가 오면 설정이 끝난 것입니다.
3. 이후로는 10분마다 자동으로 확인합니다. 실행에 실패하면 GitHub가 메일로 알려 줍니다.

## 참고
- GitHub 예약 실행은 지연될 수 있습니다. 실제 확인 간격은 10~30분 정도가 됩니다.
- 공개 저장소는 60일 동안 활동이 없으면 예약 실행이 멈춥니다. 이 워크플로가 45일마다 빈 커밋을 남겨서 멈추지 않게 합니다.
- 카카오 토큰은 매일 1회 자동으로 갱신됩니다.
- 알림을 끄려면 **Actions > 뽐뿌 키워드 알림 > ··· > Disable workflow**를 누릅니다.

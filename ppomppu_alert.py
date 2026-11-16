#!/usr/bin/env python3
"""뽐뿌 게시판 키워드 새 글 → 카카오톡 '나에게 보내기' 알림.

표준 라이브러리만 사용하므로 설치할 패키지가 없습니다.
GitHub Actions에서 실행되며, 상태(마지막으로 본 글 번호)와 카카오 토큰은
저장소의 Variables / Secrets에 보관합니다.

사용법:
  python3 ppomppu_alert.py setup   # 최초 1회: 인가 코드 → 토큰 발급 → 테스트 메시지
  python3 ppomppu_alert.py run     # 새 글 확인 및 알림 (10분마다 자동 실행)
"""
import html
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

BOARD = os.environ.get("PPOMPPU_BOARD") or "ppomppu"
PAGES = int(os.environ.get("PPOMPPU_PAGES") or "2")
KEYWORDS = [k.strip() for k in (os.environ.get("KEYWORDS") or "두유").split(",") if k.strip()]
REDIRECT_URI = os.environ.get("KAKAO_REDIRECT_URI") or "http://localhost/oauth"
MAX_SEND = 10  # 한 번에 보내는 최대 알림 수

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
FORM = "application/x-www-form-urlencoded;charset=utf-8"

ANCHOR = re.compile(r"<a\s[^>]*href=[\"']([^\"']*view\.php\?[^\"']*)[\"'][^>]*>(.*?)</a>", re.S | re.I)
TAG = re.compile(r"<[^>]+>")


def env(name):
    value = os.environ.get(name, "").strip()
    if not value:
        sys.exit(f"오류: {name} 값이 없습니다. 저장소 Settings > Secrets and variables > Actions 를 확인하세요.")
    return value


def http(url, data=None, headers=None, timeout=20):
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


# ---------------------------------------------------------------- 뽐뿌 읽기
def board_url(no=None, mobile=False):
    if no is None:
        return f"https://www.ppomppu.co.kr/zboard/zboard.php?id={BOARD}"
    if mobile:
        return f"https://m.ppomppu.co.kr/new/bbs_view.php?id={BOARD}&no={no}"
    return f"https://www.ppomppu.co.kr/zboard/view.php?id={BOARD}&no={no}"


def parse_posts(page_html):
    """목록 HTML에서 {글번호: 제목} 추출. 한 글에 링크가 여러 개면 가장 긴 텍스트를 제목으로."""
    posts = {}
    for href, inner in ANCHOR.findall(page_html):
        query = urllib.parse.parse_qs(urllib.parse.urlparse(html.unescape(href)).query)
        if query.get("id", [""])[0] != BOARD:
            continue
        no = query.get("no", [""])[0]
        if not no.isdigit():
            continue
        title = " ".join(html.unescape(TAG.sub(" ", inner)).split())
        if len(title) > len(posts.get(int(no), "")):
            posts[int(no)] = title
    return {n: t for n, t in posts.items() if t}


def fetch_posts():
    posts = {}
    for page in range(1, PAGES + 1):
        url = f"{board_url()}&page={page}"
        try:
            raw = http(url, headers={
                "User-Agent": UA,
                "Accept-Language": "ko-KR,ko;q=0.9",
                "Referer": "https://www.ppomppu.co.kr/",
            })
        except urllib.error.HTTPError as e:
            sys.exit(f"오류: 뽐뿌 접속 실패 (HTTP {e.code}). 접속이 막혔을 수 있습니다.")
        posts.update(parse_posts(raw.decode("cp949", errors="replace")))
    if not posts:
        sys.exit("오류: 글 목록을 하나도 읽지 못했습니다. 접속이 막혔거나 페이지 구조가 바뀌었습니다.")
    return posts


def matched_keyword(title):
    flat = title.replace(" ", "").lower()
    for kw in KEYWORDS:
        if kw.replace(" ", "").lower() in flat:
            return kw
    return None


# ---------------------------------------------------------------- 카카오
def kakao_token(params):
    params = {**params, "client_id": env("KAKAO_REST_API_KEY")}
    secret = os.environ.get("KAKAO_CLIENT_SECRET", "").strip()
    if secret:
        params["client_secret"] = secret
    try:
        return json.loads(http("https://kauth.kakao.com/oauth/token", params, {"Content-Type": FORM}))
    except urllib.error.HTTPError as e:
        sys.exit(f"오류: 카카오 토큰 요청 실패 (HTTP {e.code}) {e.read().decode(errors='replace')}")


def save_refresh_token(token):
    gh_set("secret", "KAKAO_REFRESH_TOKEN", token)
    print("카카오 리프레시 토큰을 Secrets에 저장했습니다.")


def get_access_token():
    tok = kakao_token({"grant_type": "refresh_token", "refresh_token": env("KAKAO_REFRESH_TOKEN")})
    if tok.get("refresh_token"):  # 만료 1개월 미만일 때만 새로 내려옴
        save_refresh_token(tok["refresh_token"])
    return tok["access_token"]


def send_kakao(access_token, text, url, mobile_url=None, button="글 보기"):
    template = {
        "object_type": "text",
        "text": text[:200],
        "link": {"web_url": url, "mobile_web_url": mobile_url or url},
        "button_title": button,
    }
    try:
        res = json.loads(http(
            "https://kapi.kakao.com/v2/api/talk/memo/default/send",
            {"template_object": json.dumps(template, ensure_ascii=False)},
            {"Authorization": f"Bearer {access_token}", "Content-Type": FORM},
        ))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"카톡 발송 실패 (HTTP {e.code}) {e.read().decode(errors='replace')}")
    if res.get("result_code") != 0:
        raise RuntimeError(f"카톡 발송 실패: {res}")


# ---------------------------------------------------------------- GitHub 저장소 설정 쓰기
def gh_set(kind, name, value):
    env("GH_TOKEN")
    cmd = ["gh", kind, "set", name, "--repo", env("GITHUB_REPOSITORY")]
    if kind == "variable":
        subprocess.run(cmd + ["--body", value], check=True)
    else:  # secret 은 명령줄에 노출되지 않도록 표준입력으로 전달
        subprocess.run(cmd, input=value.encode(), check=True)


# ---------------------------------------------------------------- 실행 모드
def setup():
    code = env("KAKAO_AUTH_CODE")
    if "code=" in code:  # 주소 전체를 붙여넣은 경우
        code = urllib.parse.parse_qs(urllib.parse.urlparse(code).query).get("code", [""])[0]
    tok = kakao_token({"grant_type": "authorization_code", "redirect_uri": REDIRECT_URI, "code": code})
    save_refresh_token(tok["refresh_token"])
    send_kakao(tok["access_token"], "✅ 뽐뿌 알림 봇이 카카오톡에 연결됐습니다.", board_url())
    print("테스트 메시지를 보냈습니다. 카카오톡 '나와의 채팅'을 확인하세요.")


def run():
    posts = fetch_posts()
    newest = sorted(posts, reverse=True)
    print(f"뽐뿌 목록에서 글 {len(posts)}개를 읽었습니다. 최신 글 5개:")
    for n in newest[:5]:
        print(f"  {n}  {posts[n]}")
    print(f"감시 키워드: {', '.join(KEYWORDS)}")

    if os.environ.get("DRY_RUN"):
        hits = [n for n in newest if matched_keyword(posts[n])]
        print(f"[테스트 모드] 현재 목록 중 키워드가 들어간 글 {len(hits)}개:")
        for n in hits:
            print(f"  {n}  {posts[n]}")
        print("[테스트 모드] 카톡 발송과 상태 저장은 하지 않았습니다.")
        return

    max_no = newest[0]
    last = os.environ.get("LAST_SEEN_NO", "").strip()

    if not last.isdigit():  # 첫 실행: 기준점만 잡고 시작 알림
        access = get_access_token()
        send_kakao(access, f"🔔 뽐뿌 키워드 알림을 시작합니다.\n키워드: {', '.join(KEYWORDS)}\n"
                           f"지금부터 새로 올라오는 글을 알려드립니다.", board_url())
        gh_set("variable", "LAST_SEEN_NO", str(max_no))
        print(f"첫 실행: 기준 글 번호를 {max_no}로 저장했습니다.")
        return

    last = int(last)
    new_hits = sorted(n for n in posts if n > last and matched_keyword(posts[n]))[-MAX_SEND:]
    print(f"마지막으로 본 글 번호 {last} 이후 키워드 새 글: {len(new_hits)}개")

    access = get_access_token() if (new_hits or os.environ.get("DAILY")) else None
    for n in new_hits:
        kw = matched_keyword(posts[n])
        try:
            send_kakao(access, f"🛒 뽐뿌 '{kw}' 새 글\n{posts[n]}", board_url(n), board_url(n, mobile=True))
            print(f"  발송: {n} {posts[n]}")
        except RuntimeError:
            gh_set("variable", "LAST_SEEN_NO", str(n - 1))  # 실패한 글부터 다음에 다시 시도
            raise

    if max_no > last:
        gh_set("variable", "LAST_SEEN_NO", str(max_no))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "run"
    {"setup": setup, "run": run}.get(mode, run)()

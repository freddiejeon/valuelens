#!/usr/bin/env python3
"""valuelens.kr 매일 자동 갱신 (Claude 예약 작업 대신 PC에서 실행).

나눠 맡는 일
  코드      목록 페이지(/lecture/ /fund/ /etf/ /brief/), 사이트맵, IndexNow, 처리 표시 → main에 바로 반영
  DeepSeek  사이트에 페이지가 있는 종목의 새 분석 글 → 최신 판단 상자와 글 카드 문장 작성
  코드      DeepSeek 문장의 숫자가 블로그 원문에 실제로 있는지, 원문을 길게 베끼지 않았는지 검사
            → 통과하면 PR로 올림 (Claude 감수, 프레디 병합)
  보고만    페이지가 없는 종목(새 페이지는 Claude 작업), 처리 규칙이 없는 카테고리

사용법
  python _ops/auto.py                 # 실제 실행 (main push, PR 생성)
  python _ops/auto.py --dry-run       # 무엇을 할지만 출력, 파일과 git은 건드리지 않음
  python _ops/auto.py --test LOGNO    # 그 글로 DeepSeek 요약과 검사만 시험 (파일, git 변경 없음)
"""
import argparse, copy, datetime as dt, html, json, os, re, subprocess, sys, urllib.request

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sync  # noqa: E402

ROOT = sync.ROOT
KST = sync.KST
LIST_CATS = {s["cat"] for s in sync.SECTIONS.values()}
MODEL = "deepseek/deepseek-v4.1-flash-1017"
TODAY = dt.datetime.now(KST).strftime("%Y-%m-%d")
LOG = r"G:\내 드라이브\60_투자\valuelens_sync\last_run.log"


# ---------- 공통 ----------
def git(*a, check=True):
    r = subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    if check and r.returncode:
        raise RuntimeError(f"git {' '.join(a)} 실패: {r.stderr.strip()}")
    return r.stdout.strip()


def gh(*a):
    r = subprocess.run(["gh", *a], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    if r.returncode:
        raise RuntimeError(f"gh {' '.join(a)} 실패: {r.stderr.strip()}")
    return r.stdout.strip()


def api_key():
    k = os.environ.get("OPENROUTER_API_KEY")
    if not k and os.name == "nt":
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as h:
            k = winreg.QueryValueEx(h, "OPENROUTER_API_KEY")[0]
    if not k:
        raise RuntimeError("OPENROUTER_API_KEY 가 없습니다")
    return k


def deepseek(prompt):
    body = {"model": MODEL, "messages": [{"role": "user", "content": prompt}], "max_tokens": 1500,
            "temperature": 0.2, "reasoning": {"enabled": False}, "response_format": {"type": "json_object"}}
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {api_key()}", "Content-Type": "application/json"})
    r = json.load(urllib.request.urlopen(req, timeout=120))
    t = r["choices"][0]["message"]["content"]
    return json.loads(t[t.find("{"): t.rfind("}") + 1])


def rd(p):
    return open(os.path.join(ROOT, p), encoding="utf-8").read()


def wr(p, s):
    with open(os.path.join(ROOT, p), "w", encoding="utf-8") as f:
        f.write(s)


def clean(t):
    return t.replace("·", ", ").strip()


# ---------- 종목 페이지 ----------
PROMPT = """너는 가치투자 블로그 글을 개인 사이트 종목 페이지용으로 요약하는 편집자다.
아래 블로그 글(필자: 프레디)을 읽고 JSON만 출력하라.

{{
 "기준일": "글의 기준일 YYYY-MM-DD",
 "의견": "필자의 현재 의견 짧게 (예: BUY(나눠 사기 시작), HOLD, SELL)",
 "목표주가": 12개월 목표주가 정수(원) 또는 null,
 "종가": 글에 적힌 기준 종가 정수(원) 또는 null,
 "종가일": "그 종가의 날짜 YYYY-MM-DD" 또는 null,
 "판단": "2~3문장. 첫 문장은 'YYYY년 M월 D일 기준 의견.' 형식. 이어서 판단의 핵심 근거 숫자 1~2개를 쓰고, 공시나 주가 숫자 뒤에는 원문에 적힌 출처와 날짜를 괄호로, 필자 추정치(목표주가, 내재가치) 뒤에는 (필자 계산)을 붙인다.",
 "카드": "1~2문장. 이 글이 무엇을 판단했는지 새 문장으로 요약 (~습니다체)."
}}

규칙
- 숫자는 원문에 적힌 값만 쓰고, 원문과 똑같은 표기(쉼표, 단위)로 쓴다. 계산하거나 반올림하지 않는다.
- 원문 문장을 그대로 옮기지 말고 새로 쓴다. ~습니다체.
- 가운데 점(·)을 쓰지 않는다. 나열은 쉼표나 '와/과'.
- 매수를 권하는 표현(꼭 사세요 등)을 쓰지 않는다.

[글 제목]
{title}

[글 본문]
{body}
"""


def nums(s):
    return re.findall(r"\d{4}\.\s?\d{1,2}\.\s?\d{1,2}|\d[\d,]*(?:\.\d+)?", s)


def check(out, body):
    """DeepSeek 결과 검사. 문제 목록을 돌려준다 (비면 통과)."""
    probs = []
    nb = re.sub(r"[\s,]", "", body)
    for k in ("판단", "카드"):
        txt = out.get(k) or ""
        if not txt:
            probs.append(f"{k} 비어 있음")
            continue
        for n in nums(txt):
            m = re.match(r"(\d{4})\.\s?(\d{1,2})\.\s?(\d{1,2})$", n)
            if m:  # 날짜: 2026.11.20 / 2026.11.2 / 11월 20일 / 11/20 중 하나로 원문에 있으면 통과
                y, mo, d = m.group(1), int(m.group(2)), int(m.group(3))
                if not any(v in nb for v in (f"{y}.{mo:02d}.{d:02d}", f"{y}.{mo}.{d}", f"{mo}월{d}일", f"{mo}/{d}", f"{mo:02d}.{d:02d}")):
                    probs.append(f"{k}의 날짜 {n} 원문에 없음")
                continue
            if n.replace(",", "") not in nb:
                probs.append(f"{k}의 숫자 {n} 원문에 없음")
        flat = re.sub(r"\s", "", re.sub(r"\([^)]*\)", "", txt))  # 괄호 속 출처 표기는 원문과 같아도 됨
        nbs = re.sub(r"\s", "", body)
        for i in range(0, max(0, len(flat) - 45)):
            if flat[i:i + 45] in nbs:
                probs.append(f"{k}에 원문과 같은 45자 이상 구간 있음: {flat[i:i + 45]}")
                break
    m = re.match(r"(\d{4})년 (\d{1,2})월 (\d{1,2})일 기준", out.get("판단", ""))
    if not m:
        probs.append("판단 첫 문장이 'YYYY년 M월 D일 기준' 형식이 아님")
    for k in ("목표주가", "종가"):
        v = out.get(k)
        if v and f"{int(v):,}" not in body and str(int(v)) not in body:
            probs.append(f"{k} {v} 원문에 없음")
    return probs


def ymd_kor(s):
    y, m, d = s.split("-")
    return f"{y}년 {int(m)}월 {int(d)}일"


def update_stock_page(code, post, out, card_only=False):
    """stock/{code}.html 에 새 글을 반영. 바꾼 파일 목록을 돌려준다."""
    p = f"stock/{code}.html"
    s = rd(p)
    title = clean(post["title"])
    url = post["url"]
    if url in s:
        return []
    card = (f'<div class="post"><div class="d">{post["date"].replace("-", ".")}</div><h3><a href="{url}">{html.escape(title)}</a></h3>'
            f'<p>{html.escape(clean(out["카드"]))}</p><a class="go" href="{url}">원문 보기</a></div>\n')
    anchor = re.search(r'<p class="note">최신 글부터[^\n]*</p>\n', s)
    if not anchor:
        raise RuntimeError(f"{p}: 글 카드 위치(최신 글부터 note)를 찾지 못함")
    s = s[:anchor.end()] + card + s[anchor.end():]
    n = len(re.findall(r'<div class="post">', s))
    s = re.sub(r"분석 글 \d+편 / 페이지 갱신 [\d.]+", f"분석 글 {n}편 / 페이지 갱신 {TODAY.replace('-', '.')}", s)

    if not card_only:
        s = re.sub(r'<div class="box">.*?</div>', lambda _: f'<div class="box">{html.escape(clean(out["판단"]))}</div>', s, count=1, flags=re.S)
        s = re.sub(r'(<a class="go" href=")[^"]+(">최신 분석 전문 읽기)', lambda m: m.group(1) + url + m.group(2), s, count=1)

    # 설명 문구 (meta, og, JSON-LD)
    old_desc = re.search(r'<meta name="description" content="([^"]*)">', s).group(1)
    name = re.search(r"<h1>(.*?)\(\d{6}\) 분석 모음</h1>", s).group(1)
    if not card_only and out.get("목표주가") and out.get("종가") and out.get("종가일"):
        desc = (f"{name}({code}) 가치투자 분석 글 {n}편의 핵심 요약과 최신 판단. {ymd_kor(out['기준일'])} 기준 {clean(out['의견'])}, "
                f"12개월 목표주가 {int(out['목표주가']):,}원(필자 계산), KRX 종가 {int(out['종가']):,}원({out['종가일'].replace('-', '.')}).")
    else:
        desc = re.sub(r"글 \d+편", f"글 {n}편", html.unescape(old_desc))
    s = s.replace(f'<meta name="description" content="{old_desc}">', f'<meta name="description" content="{html.escape(desc)}">')
    s = re.sub(r'<meta property="og:description" content="[^"]*">', lambda _: f'<meta property="og:description" content="{html.escape(desc)}">', s)

    m = re.search(r'(<script type="application/ld\+json">\n)(.*?)(\n</script>)', s, re.S)
    ld = json.loads(m.group(2))
    page = ld["@graph"][0]
    page["description"] = desc
    page["dateModified"] = TODAY
    page.setdefault("isBasedOn", []).insert(0, url)
    items = page["mainEntity"]["itemListElement"]
    new = copy.deepcopy(items[0]) if items else {"@type": "ListItem", "item": {"@type": "BlogPosting"}}
    new["item"].update({"headline": title, "datePublished": post["date"], "url": url})
    items.insert(0, new)
    for i, it in enumerate(items):
        it["position"] = i + 1
    s = s[:m.start(2)] + json.dumps(ld, ensure_ascii=False, indent=1) + s[m.end(2):]
    wr(p, s)

    # 종목 목록과 첫 화면: 맨 위로
    idx = rd("stock/index.html")
    li = re.search(rf'<li><a href="/stock/{code}">[^\n]*</li>\n', idx)
    if li:
        row = re.sub(r"글 \d+편, 최근 [\d.]+", f"글 {n}편, 최근 {post['date'].replace('-', '.')}", li.group(0))
        idx = idx.replace(li.group(0), "")
        idx = idx.replace('<ul class="list">\n', '<ul class="list">\n' + row, 1)
        wr("stock/index.html", idx)
    home = rd("index.html")
    li = re.search(rf'\n(\s*)<li><a href="/stock/{code}">[^\n]*</li>', home)
    if li:
        home = home.replace(li.group(0), "", 1)
        um = re.search(r'<ul class="stocks">', home)
        home = home[:um.end()] + li.group(0) + home[um.end():]
        wr("index.html", home)
    return [p, "stock/index.html", "index.html"]


# ---------- 분류 ----------
def stock_names():
    idx = rd("stock/index.html")
    return {m.group(2): m.group(1) for m in re.finditer(r'<a href="/stock/(\d{6})">([^<(]+)\(\d{6}\)</a>', idx)}


def plan(posts):
    names = stock_names()
    jobs = []
    for p in posts:
        cat = str(p["category"])
        if cat in LIST_CATS:
            jobs.append(("list", p, None))
        elif cat == "14":
            codes = re.findall(r"\((\d{6})\)", p["title"])
            if len(codes) == 1:
                code = codes[0]
                if os.path.exists(os.path.join(ROOT, "stock", f"{code}.html")):
                    jobs.append(("stock", p, code))
                else:
                    jobs.append(("pending", p, f"새 종목 페이지 필요({code}): Claude 작업"))
            else:
                hit = [c for n, c in names.items() if n in p["title"]]
                jobs.append(("cards", p, hit) if hit else ("done", p, "여러 종목 글, 사이트에 페이지 있는 종목 없음"))
        else:
            jobs.append(("pending", p, f"카테고리 {cat}({p['categoryName']}) 처리 규칙 없음"))
    return jobs


# ---------- 실행 ----------
def stock_pr(p, codes, card_only, log, dry):
    br = f"auto/{p['logNo']}"
    if not dry and gh("pr", "list", "--head", br, "--state", "all", "--json", "number") not in ("", "[]"):
        log.append(f"- 이미 PR 있음: {br} ({p['title']})")
        return True
    body = sync.body(p["logNo"])[:8000]
    out = deepseek(PROMPT.format(title=p["title"], body=body))
    probs = check(out, body) if not card_only else [x for x in check(out, body) if not x.startswith("판단")]
    if probs:
        log.append(f"- 보류: {p['title']} → DeepSeek 결과 검사 실패 ({'; '.join(probs)})")
        return False
    if dry:
        log.append(f"- (시험) 종목 페이지 PR 예정: {', '.join(codes)} ← {p['title']}")
        return True
    git("checkout", "-B", br, "origin/main")
    files = set()
    for c in codes:
        files.update(update_stock_page(c, p, out, card_only))
    sync.sitemap([f"https://valuelens.kr/stock/{c}" for c in codes] + ["https://valuelens.kr/stock/", "https://valuelens.kr/"])
    git("add", *files, "sitemap.xml")
    git("commit", "-m", f"자동: {', '.join(codes)} 페이지에 새 글 반영 ({p['logNo']})\n\n문장은 DeepSeek 작성, 숫자는 원문 대조 통과.")
    git("push", "-f", "-u", "origin", br)
    pr_body = (f"블로그 새 글을 종목 페이지에 반영합니다.\n\n- 원문: {p['url']}\n- 종목: {', '.join(codes)}\n"
               f"- 문장 작성: DeepSeek ({MODEL}), 코드 검사: 숫자 원문 대조, 45자 이상 원문 복제 없음\n\n"
               f"감수할 점\n- 최신 판단 상자와 글 카드 문장이 원문 판단과 맞는지\n- 의견이 바뀌었다면 예전 글 카드에 「당시 판단」 문구가 필요한지\n\n"
               f"DeepSeek 출력\n```json\n{json.dumps(out, ensure_ascii=False, indent=1)}\n```\n\n🤖 valuelens 자동 갱신 (_ops/auto.py)")
    url = gh("pr", "create", "--base", "main", "--head", br, "--title", f"자동: {p['title'][:60]}", "--body", pr_body)
    log.append(f"- 감수 대기 PR: {url} ({', '.join(codes)})")
    git("checkout", "main")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--test", metavar="LOGNO")
    ap.add_argument("--log", action="store_true", help="출력을 실행 기록 파일(LOG)에도 저장 (예약 작업용)")
    a = ap.parse_args()
    if a.log:
        import io, traceback
        buf, real = io.StringIO(), sys.stdout
        sys.stdout = buf
        try:
            run(a)
        except BaseException:
            traceback.print_exc(file=buf)
            raise
        finally:
            sys.stdout = real
            open(LOG, "w", encoding="utf-8").write(buf.getvalue())
            print(buf.getvalue())
    else:
        run(a)


def run(a):

    if a.test:
        p = next(x for x in sync.all_posts() if x["logNo"] == a.test)
        body = sync.body(p["logNo"])[:8000]
        out = deepseek(PROMPT.format(title=p["title"], body=body))
        print(json.dumps(out, ensure_ascii=False, indent=1))
        print("검사:", check(out, body) or "통과")
        return

    log = [f"# valuelens 자동 갱신 {dt.datetime.now(KST):%Y-%m-%d %H:%M}", ""]
    if not a.dry_run:
        if git("status", "--porcelain"):
            raise SystemExit("작업 폴더에 커밋 안 된 변경이 있어 멈춤: " + git("status", "--porcelain"))
        git("fetch", "origin")
        git("checkout", "-B", "main", "origin/main")

    st = sync.load_state()
    posts = [p for p in sync.all_posts(stop_below=st["baseline_logNo"]) if int(p["logNo"]) > int(st["baseline_logNo"])]
    posts = [p for p in posts if p["logNo"] not in st["processed"] and not sync.site_has(p["logNo"])]
    jobs = plan(posts)
    if not jobs:
        log.append("- 새 글 없음")

    done, pending = [], {}
    for kind, p, arg in jobs:
        try:
            if kind == "list":
                done.append(p["logNo"]); log.append(f"- 목록 반영: {p['title']}")
            elif kind == "done":
                done.append(p["logNo"]); log.append(f"- 반영할 곳 없음: {p['title']} ({arg})")
            elif kind == "pending":
                if st.get("pending", {}).get(p["logNo"]) != arg:
                    pending[p["logNo"]] = arg
                log.append(f"- 보류: {p['title']} → {arg}")
            elif kind in ("stock", "cards"):
                stock_pr(p, [arg] if kind == "stock" else arg, kind == "cards", log, a.dry_run)
        except Exception as e:
            log.append(f"- 오류: {p['title']} → {e}")
            if not a.dry_run:
                git("checkout", "-f", "main", check=False)

    if a.dry_run:
        print("\n".join(log))
        return

    # main 반영: 목록 페이지, 상태 파일
    sync.lists()
    changed = [l[3:] for l in git("status", "--porcelain").splitlines()]
    urls = [f"https://valuelens.kr/{f.split('/')[0]}/" for f in changed if f.endswith("/index.html")]
    st = sync.load_state()
    for n in done:
        if n not in st["processed"]:
            st["processed"].append(n)
    st.setdefault("pending", {}).update(pending)
    sync.save_state(st)
    if urls:
        sync.sitemap(urls + ["https://valuelens.kr/"])
    if git("status", "--porcelain"):
        git("add", "-A")
        git("commit", "-m", "자동: 목록 페이지와 처리 상태 갱신")
        git("push", "origin", "main")
        log.append(f"- main 반영: {', '.join(urls) or '상태 파일만'}")
        if urls:
            sync.indexnow(urls)
    print("\n".join(log))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""valuelens.kr 매일 동기화 보조 스크립트.

사용법
  python3 _ops/sync.py list            # 기준선 이후 새 글 목록(JSON)
  python3 _ops/sync.py body LOGNO      # 글 본문 텍스트
  python3 _ops/sync.py find 키워드...    # 전체 글에서 제목 검색 (종목 과거 글 모으기)
  python3 _ops/sync.py sitemap URL...   # sitemap.xml에 주소 추가 또는 lastmod를 오늘로 갱신
  python3 _ops/sync.py indexnow URL...  # IndexNow(빙, 네이버 등)에 변경 주소 통보
  python3 _ops/sync.py done LOGNO...    # 처리 완료 표시 (state.json)
  python3 _ops/sync.py lists           # 강의, 모의펀드, ETF, 리포트 브리핑 목록 페이지 재생성 (/lecture/, /fund/, /etf/, /brief/)
"""
import datetime as dt, html, json, os, re, sys, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, "_ops", "state.json")
KST = dt.timezone(dt.timedelta(hours=9))
BLOG = "journk"
CATS = {"14": "종목분석", "13": "ETF", "18": "주린이 강의", "19": "모의펀드", "25": "증권사 리포트 브리핑"}


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (valuelens-sync)"})
    return urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")


def load_state():
    with open(STATE, encoding="utf-8") as f:
        return json.load(f)


def save_state(s):
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=1)
        f.write("\n")


def abs_date(s):
    """'3시간 전', '2026. 11. 22.' 같은 표기를 YYYY-MM-DD로 바꿈."""
    now = dt.datetime.now(KST)
    m = re.match(r"(\d+)\s*(분|시간)\s*전", s)
    if m:
        n = int(m.group(1))
        d = now - (dt.timedelta(minutes=n) if m.group(2) == "분" else dt.timedelta(hours=n))
        return d.strftime("%Y-%m-%d")
    m = re.match(r"(\d{4})\.\s*(\d+)\.\s*(\d+)", s)
    if m:
        return "%s-%02d-%02d" % (m.group(1), int(m.group(2)), int(m.group(3)))
    return s


def all_posts(stop_below=None):
    out, seen, page = [], set(), 1
    while page <= 60:
        t = get(f"https://blog.naver.com/PostTitleListAsync.naver?blogId={BLOG}&currentPage={page}&categoryNo=0&countPerPage=30")
        pl = json.loads(t.replace("\\'", "'"))["postList"]
        new = [p for p in pl if p["logNo"] not in seen]
        if not new:
            break
        for p in new:
            seen.add(p["logNo"])
            out.append({
                "logNo": p["logNo"],
                "date": abs_date(p["addDate"]),
                "category": p.get("categoryNo"),
                "categoryName": CATS.get(str(p.get("categoryNo")), "기타"),
                "title": urllib.parse.unquote_plus(p["title"]),
                "url": f"https://blog.naver.com/{BLOG}/{p['logNo']}",
            })
        if stop_below and int(new[-1]["logNo"]) <= int(stop_below):
            break
        page += 1
    return out


def site_has(logno):
    for dp, dn, fn in os.walk(ROOT):
        if "/.git" in dp or "/_ops" in dp:
            continue
        for f in fn:
            if f.endswith(".html"):
                with open(os.path.join(dp, f), encoding="utf-8") as fh:
                    if logno in fh.read():
                        return True
    return False


def body(logno):
    t = get(f"https://blog.naver.com/PostView.naver?blogId={BLOG}&logNo={logno}&redirect=Dlog&widgetTypeCall=true&directAccess=false")
    i = t.find("se-main-container")
    t = t[i:] if i >= 0 else t
    j = t.find("post_footer_contents")
    t = t[:j] if j > 0 else t
    t = re.sub(r"<script.*?</script>|<style.*?</style>", "", t, flags=re.S)
    t = html.unescape(re.sub(r"<[^>]+>", "\n", t))
    lines = [l.strip() for l in t.split("\n")]
    return "\n".join(l for l in lines if l and l != "​" and not l.startswith("se-main-container"))


def sitemap(urls):
    p = os.path.join(ROOT, "sitemap.xml")
    s = open(p, encoding="utf-8").read()
    today = dt.datetime.now(KST).strftime("%Y-%m-%d")
    for u in urls:
        pat = re.compile(r"(<loc>" + re.escape(u) + r"</loc>\s*<lastmod>)[^<]*(</lastmod>)")
        if pat.search(s):
            s = pat.sub(r"\g<1>" + today + r"\g<2>", s)
        else:
            s = s.replace("</urlset>", f"  <url>\n    <loc>{u}</loc>\n    <lastmod>{today}</lastmod>\n  </url>\n</urlset>")
    open(p, "w", encoding="utf-8").write(s)
    print("sitemap 갱신:", today, len(urls), "개")


def indexnow(urls):
    key = load_state()["indexnow_key"]
    data = json.dumps({"host": "valuelens.kr", "key": key,
                       "keyLocation": f"https://valuelens.kr/{key}.txt", "urlList": urls}).encode()
    req = urllib.request.Request("https://api.indexnow.org/indexnow", data=data,
                                 headers={"Content-Type": "application/json; charset=utf-8"})
    try:
        r = urllib.request.urlopen(req, timeout=30)
        print("IndexNow 응답", r.status)
    except urllib.error.HTTPError as e:
        print("IndexNow 응답", e.code, e.read()[:200])


SECTIONS = {
    "lecture": {"cat": "18", "name": "주식투자 강의", "title": "주린이 주식투자 강의 목록",
                "desc": "가치투자자 프레디의 주린이 주식투자 강의와 특강 전체 목록. 각 강의는 네이버 블로그 원문에서 읽을 수 있습니다.",
                "intro": "주식을 처음 시작하는 분을 위한 강의와 특강을 최근 순으로 모았습니다. 제목을 누르면 네이버 블로그 원문으로 이동합니다."},
    "fund": {"cat": "19", "name": "모의투자", "title": "모의펀드 「프레디 가치망원경 1호」 운용보고 목록",
             "desc": "1억원 모의펀드 「프레디 가치망원경 1호」의 주간 운용보고와 매매보고서 전체 목록. 원문은 네이버 블로그에서 읽을 수 있습니다.",
             "intro": "1억원으로 시작한 모의펀드 「프레디 가치망원경 1호」의 운용보고와 매매보고서를 최근 순으로 모았습니다. 제목을 누르면 네이버 블로그 원문으로 이동합니다."},
    "etf": {"cat": "13", "name": "ETF 투자", "title": "ETF 투자 글 목록",
            "desc": "가치투자자 프레디의 ETF 분석과 투자 이야기 전체 목록. 원문은 네이버 블로그에서 읽을 수 있습니다.",
            "intro": "여러 종목을 한 바구니에 담는 ETF를 분석한 글을 최근 순으로 모았습니다. 제목을 누르면 네이버 블로그 원문으로 이동합니다."},
    "brief": {"cat": "25", "name": "증권사 리포트 브리핑", "title": "증권사 리포트 브리핑 목록",
              "desc": "그날 나온 증권사 리포트를 가치투자자 프레디가 요약하고 정리한 「증권사 리포트 브리핑」 전체 목록. 원문은 네이버 블로그에서 읽을 수 있습니다.",
              "intro": "그날 나온 증권사 리포트를 읽고 시장 전망, 금리와 환율, 섹터, 눈에 띈 종목을 요약한 브리핑을 최근 순으로 모았습니다. 리포트 원문은 싣지 않고 출처만 밝힙니다. 제목을 누르면 네이버 블로그 원문으로 이동합니다."},
}


# 방문 통계: 구글 애널리틱스(GA4). 모든 공개 HTML의 <head> 바로 다음에 넣음
GA_ID = "G-N4J28VDQ0Z"
GA_TAG = f"""<script async src="https://www.googletagmanager.com/gtag/js?id={GA_ID}"></script>
<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag('js',new Date());gtag('config','{GA_ID}');</script>"""


def ensure_ga():
    """GA 태그가 없는 공개 HTML에 태그를 넣음. 바꾼 파일 목록을 돌려줌 (새 페이지가 태그 없이 만들어져도 자동으로 보완)."""
    changed = []
    for d, dirs, files in os.walk(ROOT):
        dirs[:] = [x for x in dirs if not x.startswith((".", "_"))]
        for f in files:
            if not f.endswith(".html"):
                continue
            path = os.path.join(d, f)
            s = open(path, encoding="utf-8").read()
            if "googletagmanager.com/gtag/js" in s or "<head>" not in s:
                continue
            s = s.replace("<head>\n", "<head>\n" + GA_TAG + "\n", 1) if "<head>\n" in s else s.replace("<head>", "<head>\n" + GA_TAG, 1)
            open(path, "w", encoding="utf-8", newline="\n").write(s)
            changed.append(os.path.relpath(path, ROOT).replace(os.sep, "/"))
    return changed


def esc(t):
    return html.escape(t, quote=True)


def head_links():
    """종목 페이지 head의 디자인 링크 묶음을 그대로 가져옴 (디자인 변경을 자동으로 따름)."""
    src = open(os.path.join(ROOT, "stock", "000660.html"), encoding="utf-8").read()
    h = src[:src.index("</head>")]
    keep = [l for l in h.split("\n") if re.match(r'<(link rel="(preconnect|stylesheet)"|meta name="theme-color"|meta property="og:image|meta name="twitter:card")', l)]
    style = re.search(r"<style>.*?</style>", h, re.S)
    return "\n".join(keep) + ("\n" + style.group(0) if style else "")


def lists(posts=None):
    posts = posts or all_posts()
    links = head_links()
    for slug, sec in SECTIONS.items():
        ps = [p for p in posts if str(p["category"]) == sec["cat"]]
        url = f"https://valuelens.kr/{slug}/"
        upd = ps[0]["date"] if ps else ""
        items = [{"@type": "ListItem", "position": i + 1, "item": {"@type": "BlogPosting", "headline": p["title"].replace("·", ", "),
                  "datePublished": p["date"], "url": p["url"], "author": {"@id": "https://valuelens.kr/#freddie"}}} for i, p in enumerate(ps)]
        ld = {"@context": "https://schema.org", "@graph": [
            {"@type": "CollectionPage", "@id": url, "url": url, "name": f"{sec['title']} | 프레디의 가치망원경", "description": sec["desc"],
             "inLanguage": "ko-KR", "dateModified": upd, "isPartOf": {"@id": "https://valuelens.kr/#website"},
             "author": {"@type": "Person", "@id": "https://valuelens.kr/#freddie", "name": "프레디 (전병각)"},
             "mainEntity": {"@type": "ItemList", "numberOfItems": len(ps), "itemListElement": items}},
            {"@type": "BreadcrumbList", "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "홈", "item": "https://valuelens.kr/"},
                {"@type": "ListItem", "position": 2, "name": sec["name"], "item": url}]}]}
        cards = "\n".join(
            f'<div class="post"><div class="d">{p["date"].replace("-", ".")}</div><h3><a href="{p["url"]}">{esc(p["title"].replace("·", ", "))}</a></h3><a class="go" href="{p["url"]}">원문 보기</a></div>'
            for p in ps)
        page = f"""<!DOCTYPE html>
<html lang="ko">
<head>
{GA_TAG}
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{sec['title']} | 프레디의 가치망원경</title>
<meta name="description" content="{esc(sec['desc'])}">
<link rel="canonical" href="{url}">
<meta property="og:title" content="{sec['title']} | 프레디의 가치망원경">
<meta property="og:description" content="{esc(sec['desc'])}">
<meta property="og:url" content="{url}">
<meta property="og:type" content="website">
{links}
<script type="application/ld+json">
{json.dumps(ld, ensure_ascii=False, indent=1)}
</script>
</head>
<body>
<header><div class="in"><a href="/">프레디의 가치망원경 Freddie's Value Lens</a><h1>{sec['title']}</h1></div></header>
<main>
<p class="note">글 {len(ps)}편 / 최근 글 {upd.replace('-', '.')} / 네이버 블로그 목록을 매일 한 번 옮겨 옵니다</p>
<p>{sec['intro']}</p>
{cards}
<p><a href="/">처음으로</a> / <a href="/stock/">종목 분석 보기</a> / <a href="https://blog.naver.com/PostList.naver?blogId=journk&amp;categoryNo={sec['cat']}">블로그에서 이 카테고리 보기</a></p>
</main>
<footer>© 2026 프레디의 가치망원경 Freddie's Value Lens<br>이 사이트는 블로그 글의 제목과 링크를 안내하며, 전문은 원문 링크에서 읽을 수 있습니다. 투자 권유가 아닙니다.</footer>
</body>
</html>
"""
        path = os.path.join(ROOT, slug, "index.html")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        old = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
        if old != page:
            open(path, "w", encoding="utf-8").write(page)
            print("갱신:", url, len(ps), "편")
        else:
            print("변경 없음:", url)


def main():
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd == "list":
        st = load_state()
        base = st["baseline_logNo"]
        posts = [p for p in all_posts(stop_below=base) if int(p["logNo"]) > int(base)]
        for p in posts:
            p["processed"] = p["logNo"] in st["processed"] or site_has(p["logNo"])
            p["pending_note"] = st.get("pending", {}).get(p["logNo"])
        print(json.dumps(posts, ensure_ascii=False, indent=1))
    elif cmd == "body":
        print(body(args[0]))
    elif cmd == "find":
        for p in all_posts():
            if any(k in p["title"] for k in args):
                print(p["logNo"], p["date"], p["categoryName"], p["title"])
    elif cmd == "sitemap":
        sitemap(args)
    elif cmd == "indexnow":
        indexnow(args)
    elif cmd == "lists":
        lists()
    elif cmd == "ga":
        for f in ensure_ga():
            print("GA 태그 추가:", f)
    elif cmd == "done":
        st = load_state()
        for a in args:
            if a not in st["processed"]:
                st["processed"].append(a)
            st.get("pending", {}).pop(a, None)
        save_state(st)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()

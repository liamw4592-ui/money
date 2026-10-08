#!/usr/bin/env python3
"""赚钱雷达：抓取 GitHub 热门 / AI 赚钱案例 / 接活线索 / 命理客户线索，输出中文 Markdown 报告。
仅用标准库。可选环境变量：GITHUB_TOKEN（提高 API 额度）、ANTHROPIC_API_KEY（把英文标题译成中文）。
任何数据源失败只会跳过，不会中断。"""
import json, os, re, sys, time, datetime as dt, urllib.request, urllib.parse
import xml.etree.ElementTree as ET
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = "money-radar/1.0 (personal research)"
TODAY = dt.date.today().isoformat()
SINCE = (dt.date.today() - dt.timedelta(days=7)).isoformat()
ERRORS = []

def get(url, headers=None, timeout=20):
    h = {"User-Agent": UA}
    h.update(headers or {})
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")

def safe(name, fn, *a):
    print(f"  - 正在抓取: {name} ...", flush=True)
    try:
        return fn(*a)
    except Exception as e:  # 单个来源失败不影响其它
        ERRORS.append(f"{name}: {type(e).__name__} {e}")
        return []

def gh_headers():
    t = os.environ.get("GITHUB_TOKEN")
    return {"Authorization": f"Bearer {t}", "Accept": "application/vnd.github+json"} if t else {"Accept": "application/vnd.github+json"}

# ---------- 1. GitHub 热帖 ----------
def github_hot():
    out = []
    qs = [f"created:>{SINCE} stars:>50", f"pushed:>{SINCE} stars:>3000"]
    for q in qs:
        u = "https://api.github.com/search/repositories?" + urllib.parse.urlencode(
            {"q": q, "sort": "stars", "order": "desc", "per_page": 12})
        for it in json.loads(get(u, gh_headers())).get("items", []):
            out.append({"title": it["full_name"], "desc": it.get("description") or "", "url": it["html_url"],
                        "meta": f"★{it['stargazers_count']} {it.get('language') or '-'}"})
    seen, uniq = set(), []
    for x in out:
        if x["url"] not in seen:
            seen.add(x["url"]); uniq.append(x)
    return uniq[:20]

# ---------- 2. AI 赚钱案例（HN） ----------
HN_QUERIES = ["make money with AI", "AI side project revenue", "indie hacker AI MRR", "I built AI SaaS $", "AI agency clients"]
def hn_search(q, tags="story", days=7, min_pts=15):
    ts = int(time.time()) - days * 86400
    u = "https://hn.algolia.com/api/v1/search?" + urllib.parse.urlencode(
        {"query": q, "tags": tags, "numericFilters": f"created_at_i>{ts},points>{min_pts}", "hitsPerPage": 10})
    res = []
    for h in json.loads(get(u)).get("hits", []):
        res.append({"title": h.get("title") or (h.get("comment_text") or "")[:100], "desc": "",
                    "url": h.get("url") or f"https://news.ycombinator.com/item?id={h['objectID']}",
                    "meta": f"HN▲{h.get('points')} 讨论: https://news.ycombinator.com/item?id={h['objectID']}"})
    return res

def ai_money():
    res = []
    for q in HN_QUERIES:
        res += hn_search(q)
    return dedupe(res)[:15]

# ---------- 3/4. RSS：接活 & 命理客户 ----------
def rss(url, limit=40):
    root = ET.fromstring(get(url))
    items = []
    for e in root.iter():
        tag = e.tag.split("}")[-1]
        if tag in ("item", "entry"):
            d = {c.tag.split("}")[-1]: c for c in e}
            link = d["link"].text if "link" in d and d["link"].text else (d["link"].get("href") if "link" in d else "")
            title = (d["title"].text or "") if "title" in d else ""
            body = ""
            for k in ("description", "content", "summary"):
                if k in d and d[k].text:
                    body = re.sub(r"<[^>]+>", " ", d[k].text); break
            items.append({"title": title.strip(), "desc": re.sub(r"\s+", " ", body).strip()[:200], "url": link, "meta": ""})
    return items[:limit]

AI_KW = re.compile(r"\b(ai|gpt|llm|chatbot|automation|scrap|agent|prompt|n8n|zapier|claude|openai|app|website|bot)\b|小程序|爬虫|接单|外包|兼职|开发|AI", re.I)
def gigs():
    res = []
    for src, url in [("r/forhire", "https://www.reddit.com/r/forhire/new/.rss"),
                     ("r/slavelabour", "https://www.reddit.com/r/slavelabour/new/.rss"),
                     ("V2EX 酷工作", "https://www.v2ex.com/feed/jobs.xml"),
                     ("V2EX 外包", "https://www.v2ex.com/feed/outsourcing.xml")]:
        for it in safe(src, rss, url):
            t = it["title"]
            if "forhire" in src and "[hiring]" not in t.lower(): continue
            if "slavelabour" in src and "[task]" not in t.lower(): continue
            if AI_KW.search(t + " " + it["desc"]):
                it["meta"] = src; res.append(it)
    return dedupe(res)[:25]

LEAD_QUERIES = [("英文·想起中文名", "chinese name for me"), ("英文·看八字", "bazi reading"),
                ("英文·风水", "feng shui consultation"), ("英文·看八字2", "four pillars destiny reading")]
def mystic_leads():
    res = []
    for label, q in LEAD_QUERIES:
        u = "https://www.reddit.com/search.rss?" + urllib.parse.urlencode({"q": q, "sort": "new", "t": "week"})
        for it in safe("reddit:" + q, rss, u, 8):
            it["meta"] = label; res.append(it)
    for it in safe("hn:feng shui", hn_search, "feng shui bazi", "story", 30, 0):
        it["meta"] = "HN"; res.append(it)
    return dedupe(res)[:20]

def dedupe(items):
    s, o = set(), []
    for x in items:
        if x["url"] and x["url"] not in s:
            s.add(x["url"]); o.append(x)
    return o

# ---------- 翻译（可选） ----------
def translate(items):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key or not items:
        return
    payload = [f"{i}. {x['title']} | {x['desc'][:120]}" for i, x in enumerate(items)]
    body = json.dumps({"model": "claude-haiku-5-5", "max_tokens": 4000, "messages": [{"role": "user", "content":
        "把下面每行翻译成简洁中文(一句话，说明这是什么/能怎么赚钱或有什么用)，保持编号，每行一条，只输出结果:\n" + "\n".join(payload)}]}).encode()
    try:
        req = urllib.request.Request("https://api.anthropic.com/v1/messages", body, {
            "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
        txt = json.loads(urllib.request.urlopen(req, timeout=60).read())["content"][0]["text"]
        for line in txt.splitlines():
            m = re.match(r"\s*(\d+)[.、]\s*(.+)", line)
            if m and int(m.group(1)) < len(items):
                items[int(m.group(1))]["zh"] = m.group(2).strip()
    except Exception as e:
        ERRORS.append(f"translate: {e}")

# ---------- 排版（纯文本表格对齐，CJK 按双宽） ----------
def w(s): return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)
def clip(s, n):
    out, c = "", 0
    for ch in s:
        cw = 2 if unicodedata.east_asian_width(ch) in "WF" else 1
        if c + cw > n - 1 and w(s) > n: return out + "…"
        out += ch; c += cw
    return out
def pad(s, n): return s + " " * (n - w(s))

def table(items, with_meta=True):
    if not items: return "（本期无数据）\n"
    rows = [(str(i + 1), clip(x.get("zh") or x["title"], 44), clip(x["meta"].split(" 讨论")[0], 22)) for i, x in enumerate(items)]
    hdr = ("#", "内容", "来源/热度")
    ws = [max(w(r[k]) for r in rows + [hdr]) for k in range(3)]
    line = "+" + "+".join("-" * (x + 2) for x in ws) + "+"
    fmt = lambda r: "| " + " | ".join(pad(r[k], ws[k]) for k in range(3)) + " |"
    t = ["```", line, fmt(hdr), line] + [fmt(r) for r in rows] + [line, "```", ""]
    for i, x in enumerate(items):  # 链接列在表下方，保证复制/点击方便
        t.append(f"{i + 1}. {x['url']}")
        if x["desc"] and not x.get("zh"): t.append(f"   原文: {clip(x['desc'], 100)}")
    return "\n".join(t) + "\n"

def build(sections):
    md = [f"# 赚钱雷达日报 {TODAY}", "",
          "说明：以下按“先接活快钱 → 再做产品长线”排序。每条都附原文链接，点开即可。", ""]
    for title, tip, items in sections:
        md += [f"## {title}", f"> {tip}", "", table(items)]
    md += ["## 今日行动清单(30分钟版)", "```",
           "1. 从【接活线索】挑3条最匹配的，用 docs/沟通话术.md 里的模板当天回复",
           "2. 从【命理客户线索】挑2条真实求助的帖子，礼貌留言并给出免费小样",
           "3. 在小红书/闲鱼发1条起名或八字案例(打码隐私)引流", "```", ""]
    if ERRORS:
        md += ["## 抓取异常(自动忽略)", "```"] + ERRORS + ["```"]
    return "\n".join(md)


import html as _h, webbrowser
def build_html(sections):
    css = ("body{font-family:'Microsoft YaHei',sans-serif;max-width:900px;margin:20px auto;padding:0 12px;background:#f5f6f8;color:#222}"
           "h1{font-size:22px}h2{margin-top:28px;border-left:5px solid #e67e22;padding-left:8px}"
           ".tip{color:#666;font-size:13px;margin:4px 0 10px}.card{background:#fff;border-radius:8px;padding:10px 14px;margin:8px 0;box-shadow:0 1px 3px #0001}"
           ".card a{font-weight:bold;color:#1a56db;text-decoration:none}.meta{font-size:12px;color:#888}.d{font-size:13px;color:#555;margin-top:4px}"
           ".todo{background:#fff8e1;padding:10px 14px;border-radius:8px}.err{color:#b00;font-size:12px}")
    out = [f"<!doctype html><meta charset=utf-8><title>赚钱雷达 {TODAY}</title><style>{css}</style>",
           f"<h1>赚钱雷达 {TODAY}</h1><div class=tip>点蓝色标题直接打开原文。接活线索越新越要早回复。</div>"]
    for title, tip, items in sections:
        out.append(f"<h2>{_h.escape(title)}</h2><div class=tip>{_h.escape(tip)}</div>")
        if not items: out.append("<div class=card>（本期无数据，可能网络未通，见页面底部异常）</div>")
        for x in items:
            zh = x.get("zh"); t = _h.escape(zh or x["title"])
            sub = f"<div class=d>原文: {_h.escape(x['title'])}</div>" if zh else (f"<div class=d>{_h.escape(x['desc'][:150])}</div>" if x["desc"] else "")
            out.append(f"<div class=card><a href='{_h.escape(x['url'])}' target=_blank>{t}</a><div class=meta>{_h.escape(x['meta'].split(' 讨论')[0])}</div>{sub}</div>")
    out.append("<h2>今日行动</h2><div class=todo>1. 从接活线索挑3条回复(模板见 docs/沟通话术.md)<br>2. 从命理线索挑2条真实求助留言<br>3. 小红书/闲鱼发1条案例引流</div>")
    if ERRORS: out.append("<h2>抓取异常</h2><div class=err>" + "<br>".join(_h.escape(e) for e in ERRORS) + "</div>")
    return "".join(out)

def main():
    print(f"=== 赚钱雷达 {TODAY} 开始运行 ===")
    secs = [
        ("1. GitHub 本周热门项目", "新项目飙星榜 + 老牌项目近期活跃榜；热门开源项目常是做产品/接活的灵感来源", safe("github", github_hot)),
        ("2. AI 赚钱案例与讨论", "HN 上近 7 天的 AI 变现/独立开发案例，点讨论页看别人怎么做、赚多少", safe("hn", ai_money)),
        ("3. 接活线索(可用 AI 交付的需求)", "reddit 雇佣帖 + V2EX 外包/酷工作；越新越好抢，先回复先得单", safe("gigs", gigs)),
        ("4. 命理客户线索(起名/八字/风水)", "主要是海外想取中文名、看八字的人；国内客户见 docs/获客渠道.md", safe("mystic", mystic_leads)),
    ]
    print("  - 翻译/整理中 ...", flush=True)
    for _, _, items in secs: translate(items)
    md = build(secs)
    os.makedirs(os.path.join(ROOT, "reports"), exist_ok=True)
    for name in (f"{TODAY}.md", "latest.md"):
        open(os.path.join(ROOT, "reports", name), "w", encoding="utf-8").write(md)
    hp = os.path.join(ROOT, "reports", "latest.html")
    open(hp, "w", encoding="utf-8").write(build_html(secs))
    print(f"\n完成! 结果页: {hp}")
    if "--open" in sys.argv:
        webbrowser.open("file:///" + hp.replace(os.sep, "/"))

if __name__ == "__main__":
    main()

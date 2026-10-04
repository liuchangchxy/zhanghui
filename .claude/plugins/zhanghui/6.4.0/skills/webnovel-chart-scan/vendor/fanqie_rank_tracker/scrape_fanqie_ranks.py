"""
番茄全榜爬虫 v2 - 直接遍历男女频+阅读榜/新书榜的所有分类 URL
绕过 tab 菜单交互不稳定的问题
"""
import os
import json
import time
from datetime import datetime
from playwright.sync_api import sync_playwright

START_CODE = 58344
CHAR_SEQUENCE = [
    "D", "在", "主", "特", "家", "军", "然", "表", "场", "4", "要", "只", "v", "和", "?", "6",
    "别", "还", "g", "现", "儿", "岁", "?", "?", "此", "象", "月", "3", "出", "战", "工", "相",
    "o", "男", "直", "失", "世", "F", "都", "平", "文", "什", "V", "O", "将", "真", "T", "那",
    "当", "?", "会", "立", "些", "u", "是", "十", "张", "学", "气", "大", "爱", "两", "命",
    "全", "后", "东", "性", "通", "被", "1", "它", "乐", "接", "而", "感", "车", "山", "公",
    "了", "常", "以", "何", "可", "话", "先", "p", "i", "叫", "轻", "M", "士", "w", "着",
    "变", "尔", "快", "l", "个", "说", "少", "色", "里", "安", "花", "远", "7", "难", "师",
    "放", "t", "报", "认", "面", "道", "S", "?", "克", "地", "度", "I", "好", "机", "U",
    "民", "写", "把", "万", "同", "水", "新", "没", "书", "电", "吃", "像", "斯", "5", "为",
    "y", "白", "几", "日", "教", "看", "但", "第", "加", "候", "作", "上", "拉", "住", "有",
    "法", "r", "事", "应", "位", "利", "你", "声", "身", "国", "问", "马", "女", "他", "Y",
    "比", "父", "x", "A", "H", "N", "s", "X", "边", "美", "对", "所", "金", "活", "回", "意",
    "到", "z", "从", "j", "知", "又", "内", "因", "点", "Q", "三", "定", "8", "R", "b", "正",
    "或", "夫", "向", "德", "听", "更", "?", "得", "告", "并", "本", "q", "过", "记", "L",
    "让", "打", "f", "人", "就", "者", "去", "原", "满", "体", "做", "经", "K", "走", "如",
    "孩", "c", "G", "给", "使", "物", "?", "最", "笑", "部", "?", "员", "等", "受", "k",
    "行", "一", "条", "果", "动", "光", "门", "头", "见", "往", "自", "解", "成", "处", "天",
    "能", "于", "名", "其", "发", "总", "母", "的", "死", "手", "入", "路", "进", "心", "来",
    "h", "时", "力", "多", "开", "已", "许", "d", "至", "由", "很", "界", "n", "小", "与",
    "Z", "想", "代", "么", "分", "生", "口", "再", "妈", "望", "次", "西", "风", "种", "带",
    "J", "?", "实", "情", "才", "这", "?", "E", "我", "神", "格", "长", "觉", "间", "年",
    "眼", "无", "不", "亲", "关", "结", "0", "友", "信", "下", "却", "重", "己", "老", "2",
    "音", "字", "m", "呢", "明", "之", "前", "高", "P", "B", "目", "太", "e", "9", "起",
    "稜", "她", "也", "W", "用", "方", "子", "英", "每", "理", "便", "四", "数", "期", "中",
    "C", "外", "样", "a", "海", "们", "任"
]

def decode_text(text: str) -> str:
    if not text:
        return ""
    result = []
    for char in text:
        code = ord(char)
        idx = code - START_CODE
        if 0 <= idx < len(CHAR_SEQUENCE):
            result.append(CHAR_SEQUENCE[idx])
        else:
            result.append(char)
    return "".join(result)


OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def run_scraper(limit=30, sleep_sec=5):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d")
    output_file = os.path.join(OUTPUT_DIR, f"fanqie_all_ranks_{date_str}.json")
    state_file = os.path.join(OUTPUT_DIR, f"task_state_{date_str}.json")

    # 读取已完成分类（用 href 而非 name 去重，因为同名分类可能来自不同榜单）
    completed_hrefs = set()
    all_categories = []
    if os.path.exists(state_file):
        with open(state_file, "r", encoding="utf-8") as f:
            try:
                state = json.load(f)
                completed_hrefs = set(state.get("completed_hrefs", []))
            except:
                pass
    if os.path.exists(output_file) and len(completed_hrefs) > 0:
        with open(output_file, "r", encoding="utf-8") as f:
            try:
                existing = json.load(f)
                all_categories = existing.get("categories", [])
            except:
                pass

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        # 首先访问主榜单页，收集所有分类 URL（4个tab依次触发）
        main_url = "https://fanqienovel.com/rank/"
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 访问主榜单页: {main_url}")
        page.goto(main_url, wait_until="load", timeout=15000)
        page.wait_for_load_state("networkidle", timeout=15000)
        time.sleep(2)

        # JS: 依次触发4个tab的下拉菜单展开，然后收集所有分类链接
        collect_links_js = page.evaluate("""() => {
            const tabs = Array.from(document.querySelectorAll('*')).filter(el => {
                const txt = (el.innerText || '').trim();
                return ['男频阅读榜','男频新书榜','女频阅读榜','女频新书榜'].includes(txt) &&
                    (el.getAttribute('onclick') !== null || el.getAttribute('tabindex') !== null);
            });
            const seen = new Set();
            const results = [];

            // 点击每个tab，触发下拉菜单
            for (const tab of tabs) {
                tab.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));
            }
            // 等待所有tab点击完成
            return null; // 不在这里等待，下面单独处理
        }""")
        time.sleep(2)

        # 依次点击每个 tab，等待 1.5s，再收集所有链接
        tab_names = ["男频阅读榜", "男频新书榜", "女频阅读榜", "女频新书榜"]
        seen_hrefs = set()
        all_rank_links = []

        for tab_name in tab_names:
            try:
                page.evaluate(f"""(name) => {{
                    const allEls = Array.from(document.querySelectorAll('*'));
                    const el = allEls.find(e => (e.innerText||'').trim() === name &&
                        (e.getAttribute('onclick') !== null || e.getAttribute('tabindex') !== null));
                    if (el) el.dispatchEvent(new MouseEvent('click', {{bubbles:true,cancelable:true}}));
                }}""", tab_name)
                time.sleep(1.5)
            except:
                pass

            links = page.evaluate("""() => {
                return Array.from(document.querySelectorAll('a'))
                    .filter(a => a.href.match(/\\/rank\\/\\d+_[12]_\\d+/))
                    .map(a => ({ name: (a.innerText||'').trim(), href: a.getAttribute('href') }))
                    .filter(x => x.name && x.href && !x.name.includes('榜单说明') && x.name.length > 1);
            }""")
            for link in links:
                if link["href"] not in seen_hrefs:
                    seen_hrefs.add(link["href"])
                    all_rank_links.append(link)

        categories = all_rank_links
        print(f"✅ 从主榜单页提取到 {len(categories)} 个分类（部分tab）。补充新书榜分类...")

        # 新书榜 tab 点击后跳到 /rank/X_1_0（空白页），需要导航到具体分类页触发侧边栏
        # 访问一个男频新书榜分类页和一个女频新书榜分类页，收集它们侧边栏的新书榜分类链接
        extra_urls = [
            "https://fanqienovel.com/rank/1_1_8",   # 男频新书榜随便一个分类，触发侧边栏显示男频新书榜分类
            "https://fanqienovel.com/rank/0_1_1139", # 女频新书榜，触发侧边栏显示女频新书榜分类
        ]
        for extra_url in extra_urls:
            try:
                page.goto(extra_url, wait_until="load", timeout=15000)
                page.wait_for_load_state("networkidle", timeout=10000)
                time.sleep(2)
                # 收集新书榜分类链接（1_1_xxx 和 0_1_xxx）
                links = page.evaluate("""() => {
                    return Array.from(document.querySelectorAll('a'))
                        .filter(a => a.href.match(/\\/rank\\/\\d+_1_\\d+/))
                        .map(a => ({ name: (a.innerText||'').trim(), href: a.getAttribute('href') }))
                        .filter(x => x.name && x.href && !x.name.includes('榜单说明') && x.name.length > 1);
                }""")
                for link in links:
                    if link["href"] not in seen_hrefs:
                        seen_hrefs.add(link["href"])
                        all_rank_links.append(link)
                print(f"  从 {extra_url} 补充了 {len(links)} 个新书榜分类")
            except Exception as e:
                print(f"  补充 {extra_url} 失败: {e}")

        categories = all_rank_links
        print(f"✅ 共 {len(categories)} 个分类（完整）。开始抓取...")

        for cat in categories:
            cat_name = cat["name"]
            cat_href = cat["href"]

            if cat_href in completed_hrefs:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] ⏭️ 跳过已完成: {cat_name} ({cat_href})")
                continue

            print(f"[{datetime.now().strftime('%H:%M:%S')}] 访问 -> {cat_name} ({cat_href})")
            try:
                # 直接导航到分类页
                page.goto(f"https://fanqienovel.com{cat_href}", wait_until="load", timeout=15000)
                page.wait_for_load_state("networkidle", timeout=15000)
                time.sleep(2)
                page.wait_for_selector('a[href^="/page/"]', timeout=5000)
            except Exception as e:
                print(f"  加载失败 {cat_name}: {e}")
                continue

            # 滚动加载
            for _ in range(3):
                page.evaluate("window.scrollBy(0, window.innerHeight)")
                time.sleep(1.5)

            # 提取数据
            extract_js = """
            () => {
                const bookMap = new Map();
                const links = document.querySelectorAll('a[href^="/page/"]');
                links.forEach(link => {
                    let container = link.parentElement;
                    let depth = 0;
                    while (container && depth < 6) {
                        if (container.querySelector('img') && container.innerText.includes('在读')) {
                            const href = link.getAttribute('href');
                            if (!bookMap.has(href)) { bookMap.set(href, container); }
                            break;
                        }
                        container = container.parentElement;
                        depth++;
                    }
                });

                const cards = Array.from(bookMap.values());
                const results = [];
                for (const item of cards) {
                    let imgNode = item.querySelector('img');
                    let cover = imgNode ? imgNode.getAttribute('src') : "";
                    let title = (imgNode && imgNode.getAttribute('alt')) ? imgNode.getAttribute('alt').trim() : "";
                    if (!title) {
                        let textTitleNode = item.querySelector('h4, .title, h1') || item.querySelector('a[href^="/page/"]');
                        if (textTitleNode) { let t = textTitleNode.innerText.trim(); if (t && !/^\\d+$/.test(t)) title = t; }
                    }
                    if (!title) title = "未知";
                    if (title.includes("榜单说明")) continue;

                    let authorNode = item.querySelector('.author, .author-name') || item.querySelector('a[href^="/author-page/"]');
                    let author = authorNode ? authorNode.innerText.trim() : "未知";

                    let reads = "未知";
                    const lines = item.innerText.split('\\n');
                    for (let line of lines) {
                        if (line.includes('在读')) { reads = line; break; }
                    }

                    let introNode = item.querySelector('.intro, .abstract, .desc');
                    let intro = introNode ? introNode.innerText.trim() : "暂无简介";

                    results.push({
                        title, author, reads, intro, cover,
                        url: 'https://fanqienovel.com' + (item.querySelector('a[href^="/page/"]').getAttribute('href') || '')
                    });
                }
                return results;
            }
            """

            try:
                books_data = page.evaluate(extract_js)
            except Exception as e:
                print(f"  JS抽取失败 {cat_name}: {e}")
                books_data = []

            category_books = []
            for b in books_data[:limit]:
                t = decode_text(b.get("title", ""))
                a = decode_text(b.get("author", ""))
                r_raw = decode_text(b.get("reads", ""))
                i = decode_text(b.get("intro", "")).replace("\\n", " ")
                c = b.get("cover", "")

                if "在读" in r_raw:
                    parts = r_raw.split("在读")
                    cleaned_r = parts[1].replace(":", "").replace("：", "").strip() if len(parts) > 1 else r_raw
                else:
                    cleaned_r = r_raw

                category_books.append({
                    "title": t, "author": a, "reads": cleaned_r,
                    "intro": i, "cover": c, "url": b.get("url", "")
                })

            all_categories.append({"name": cat_name, "books": category_books})

            snapshot = {"date": datetime.now().strftime('%Y-%m-%d'), "categories": all_categories}
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(snapshot, f, ensure_ascii=False, indent=2)

            completed_hrefs.add(cat_href)
            with open(state_file, "w", encoding="utf-8") as f:
                json.dump({"completed_hrefs": list(completed_hrefs)}, f, ensure_ascii=False)

            print(f"  ✅ {cat_name}: {len(category_books)} 本书，已存档。等待 {sleep_sec}s...")
            time.sleep(sleep_sec)

        browser.close()

    print(f"\n✅ 完成！数据源: {output_file}")


if __name__ == "__main__":
    print("开始执行番茄全榜抓取计划（男频+女频，阅读榜+新书榜）...")
    run_scraper(limit=30, sleep_sec=5)
from pathlib import Path
from scripts.adapters import ciweimao as mod
from scripts.adapters.ciweimao import CiweimaoAdapter, parse_category_html


def test_parse_category_html_extracts_basic_fields():
    html = (Path(__file__).parent / "fixtures" / "ciweimao_category_xuanhuan.html").read_text()
    books = parse_category_html(html, top=10)
    assert all(b.platform_book_id for b in books)
    assert all(b.title for b in books)
    assert all(b.author for b in books)


def test_ciweimao_adapter_metadata():
    a = CiweimaoAdapter()
    assert a.platform == "ciweimao"
    assert a.strategy.value == "webfetch"


def test_ciweimao_fetch_calls_correct_url():
    """验证 URL 构造逻辑（默认 sort 玄幻 / 显式 daily all）。"""
    from scripts.adapters import ciweimao as mod
    captured = []

    def fake_fetch(url, **kwargs):
        captured.append(url)
        return _FakeResp("")

    mod.httpx.get = fake_fetch
    a = CiweimaoAdapter()

    # 玄幻 + 未映射 period：默认排序（sort_key="0"） → 走 canonical category URL
    a.fetch("玄幻", "default", 5)
    assert captured[0] == f"{mod.CIWEIMAO_BASE}/book_list/yijiehuanxiang/", \
        f"expected default sort URL, got {captured[0]}"

    # Daily + all：显式排序（sort_key="day_no_vip_click"） → quanbu + sort key
    captured.clear()
    a.fetch("all", "daily", 5)
    assert "day_no_vip_click" in captured[0], \
        f"expected daily sort key in URL, got {captured[0]}"
    assert "quanbu" in captured[0], \
        f"expected 'all' category slug in URL, got {captured[0]}"


class _FakeResp:
    def __init__(self, text):
        self.text = text
        self.status_code = 200

    def raise_for_status(self):
        pass
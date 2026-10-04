"""Tests for the fanqie subcategory → normalized category mapping.

The dump file groups books by FANQIE-NATIVE subcategory names like 西方奇幻,
传统玄幻, 都市修真 — not our normalized main categories (玄幻, 都市, 仙侠).
This module defines the mapping so the adapter can answer fetch(category=玄幻, ...).

A subcategory maps to ONE normalized category. If a subcategory is not in the map,
it falls back to passing the raw name through (acceptable: adapter returns books
under that platform-native category name, orchestrator normalize() handles it).
"""
from scripts.adapters.fanqie_subcat_map import map_subcategory, SUBCAT_TO_NORMALIZED


def test_known_subcategories_resolve_to_main_categories(fixtures_dir):
    """Core mappings: every fanqie subcategory in the dump must resolve
    to a normalized main category from our NORMALIZED_CATEGORIES list."""
    # Read the actual dump to find all unique subcategory names
    import json
    dump_file = fixtures_dir / "fanqie_dump_20260815.json"
    with open(dump_file) as f:
        dump = json.load(f)
    actual_subcats = {c["name"] for c in dump["categories"]}

    for subcat in actual_subcats:
        normalized = map_subcategory(subcat)
        assert normalized in ("玄幻", "都市", "仙侠", "历史", "军事",
                              "科幻", "游戏", "体育", "灵异", "二次元",
                              "古言", "现言", "悬疑", "同人", "all"), \
            f"{subcat!r} mapped to {normalized!r} which is not a main category"


def test_xifang_qihuang_maps_to_xuanhuan():
    """西方奇幻 (Western Fantasy) → 玄幻 (our normalized main category)."""
    assert map_subcategory("西方奇幻") == "玄幻"


def test_dongfang_xianxia_maps_to_xianxia():
    """东方仙侠 (Eastern Xianxia) → 仙侠."""
    assert map_subcategory("东方仙侠") == "仙侠"


def test_guofeng_shiching_maps_to_guyan():
    """古风世情 (Female: ancient style) → 古言."""
    assert map_subcategory("古风世情") == "古言"


def test_unknown_subcategory_passes_through():
    """Unknown subcategory: return the raw name (let orchestrator handle)."""
    assert map_subcategory("未来科技") == "未来科技"


def test_mapping_dict_covers_at_least_30_subcategories():
    """Sanity: the mapping table should cover most subcategories in the dump,
    not just 2-3 hardcoded ones. The dump has 34 unique subcategories."""
    assert len(SUBCAT_TO_NORMALIZED) >= 30, \
        f"only {len(SUBCAT_TO_NORMALIZED)} subcategories mapped, need ≥30"

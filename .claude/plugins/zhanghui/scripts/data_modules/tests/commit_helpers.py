from data_modules.reconciliation import reconcile_changes
import json

EMPTY_PROPOSAL = {
    "character_state_changes": [], "new_plot_points": [],
    "foreshadowing_actions": [], "location_state_changes": [],
    "faction_state_changes": [], "time_progression": None,
    "item_transfers": [], "unresolved_questions": [],
}


def build_commit_with_reconciliation(service, **kwargs):
    extraction = kwargs.get("extraction_result", {})
    kwargs.setdefault("proposed_changes", EMPTY_PROPOSAL)
    kwargs.setdefault(
        "chapter_text",
        "test final prose\n<chapter_changes>"
        + json.dumps(kwargs["proposed_changes"], ensure_ascii=False)
        + "</chapter_changes>",
    )
    kwargs["reconciliation_result"] = reconcile_changes(
        kwargs["proposed_changes"],
        extraction,
        chapter_text=kwargs["chapter_text"],
    )
    return service.build_commit(**kwargs)

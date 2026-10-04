from data_modules.reconciliation import reconcile_changes


def build_commit_with_reconciliation(service, **kwargs):
    extraction = kwargs.get("extraction_result", {})
    kwargs["reconciliation_result"] = reconcile_changes(
        {
            "character_state_changes": [], "new_plot_points": [],
            "foreshadowing_actions": [], "location_state_changes": [],
            "faction_state_changes": [], "time_progression": None,
            "item_transfers": [], "unresolved_questions": [],
        },
        extraction,
        chapter_text="test-final-chapter",
    )
    return service.build_commit(**kwargs)

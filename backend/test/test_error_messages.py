from app.core.error_messages import to_user_friendly_error_message


def test_max_tokens_message_is_humanized() -> None:
    raw = (
        "Error code: 400 - {'error': {'message': \"Unsupported parameter: "
        "'max_tokens' is not supported with this model. Use "
        "'max_completion_tokens' instead.\"}}"
    )
    assert (
        to_user_friendly_error_message(raw)
        == "This model expects max completion tokens instead of max tokens. Please retry the workflow."
    )


def test_loop_node_cap_message_is_humanized() -> None:
    raw = "Loop safety cap reached for node 'delay_a': max_node_executions=2"
    assert (
        to_user_friendly_error_message(raw)
        == "Loop limit reached for node 'delay_a' (max 2 runs). Increase loop limits or adjust loop conditions."
    )


def test_blocked_branch_message_is_humanized() -> None:
    raw = "All incoming branches were blocked."
    assert to_user_friendly_error_message(raw) == "No branch produced data for this step."


def test_raw_message_passes_through_when_no_rule_matches() -> None:
    raw = "Custom integration failed with unknown reason."
    assert to_user_friendly_error_message(raw) == raw

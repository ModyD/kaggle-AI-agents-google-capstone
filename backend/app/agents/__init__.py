"""
Agent modules for incident response.

This package contains the core agent implementations:
- Triage: Rule-based incident scoring
- Explain: LLM-powered explanation generation
- Runbook: RAG-enhanced runbook generation
- Policy: Safety verification and rewriting
- Simulate: Runbook execution simulation
"""

from .triage import (
    score_incident,
    triage_incident,
    normalize_features,
    get_example_features,
    evaluate_rule,
    get_rule_description,
)
from .explain import explain_incident, explain_triage_decision, explain_incident_sync
from .runbook import (
    generate_runbook,
    generate_runbook_from_description,
    get_template_runbook,
    build_retrieval_query,
    generate_runbook_sync,
)
from .policy import (
    policy_check,
    policy_is_safe,
    find_forbidden_match,
    rewrite_step,
    get_safe_alternative,
    policy_check_dict,
    get_policy_rules,
    validate_custom_runbook,
)
from .simulate import (
    simulate_runbook,
    simulate_step,
    simulate_runbook_steps,
    dry_run_step,
    dry_run_runbook,
    determine_outcome,
    get_simulation_message,
)

__all__ = [
    # Triage
    "score_incident",
    "triage_incident",
    "normalize_features",
    "get_example_features",
    "evaluate_rule",
    "get_rule_description",
    # Explain
    "explain_incident",
    "explain_triage_decision",
    "explain_incident_sync",
    # Runbook
    "generate_runbook",
    "generate_runbook_from_description",
    "get_template_runbook",
    "build_retrieval_query",
    "generate_runbook_sync",
    # Policy
    "policy_check",
    "policy_is_safe",
    "find_forbidden_match",
    "rewrite_step",
    "get_safe_alternative",
    "policy_check_dict",
    "get_policy_rules",
    "validate_custom_runbook",
    # Simulate
    "simulate_runbook",
    "simulate_step",
    "simulate_runbook_steps",
    "dry_run_step",
    "dry_run_runbook",
    "determine_outcome",
    "get_simulation_message",
]

"""
Safety policy verifier for runbook steps.

This module scans generated runbook steps for dangerous or forbidden
commands and rewrites them to safe investigative alternatives.
"""

import re
from typing import Any

from app.models import RunbookResponse, RunbookStep

# =============================================================================
# Forbidden Patterns Configuration
# =============================================================================

# Exact substring matches (case-insensitive)
FORBIDDEN_SUBSTRINGS = [
    "rm -rf",
    "rm -fr",
    "rmdir /s",
    "del /f /s",
    "format c:",
    "mkfs",
    "dd if=",
    "shutdown",
    "reboot",
    "halt",
    "poweroff",
    "init 0",
    "init 6",
    "> /dev/sda",
    ":(){:|:&};:",  # Fork bomb
    "chmod 777",
    "chmod -R 777",
]

# Regex patterns for more complex matching
FORBIDDEN_PATTERNS = [
    # Dangerous curl/wget to unknown URLs
    r"curl\s+http://(?!localhost|127\.0\.0\.1)",
    r"wget\s+http://(?!localhost|127\.0\.0\.1)",
    # Dropping tables or databases
    r"drop\s+(table|database)",
    r"truncate\s+table",
    # Dangerous sudo operations
    r"sudo\s+rm\s+-rf\s+/",
    # Kill all processes
    r"killall\s+-9",
    r"pkill\s+-9\s+\*",
    # Password/credential exposure
    r"echo\s+.*password",
    r"cat\s+/etc/(passwd|shadow)",
    # Network disruption
    r"iptables\s+-F",
    r"ufw\s+disable",
    # Dangerous file operations
    r"mv\s+/\s+",
    r"cp\s+/dev/null",
]

# Compiled regex patterns for performance
COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in FORBIDDEN_PATTERNS]

# Safe replacement actions
SAFE_ALTERNATIVES = {
    "rm -rf": "Review files for deletion: ls -la",
    "shutdown": "Document need for system restart in incident report",
    "reboot": "Document need for system restart in incident report",
    "mkfs": "Document disk remediation requirements",
    "dd if=": "Document disk imaging requirements",
    "curl http": "Review URL in sandbox environment before fetching",
    "wget http": "Review URL in sandbox environment before fetching",
    "chmod 777": "Review and document required permission changes",
    "drop table": "Document database remediation in change request",
    "truncate table": "Document database cleanup in change request",
    "iptables -F": "Document firewall rule changes needed",
    "killall": "Identify specific processes to terminate",
}


# =============================================================================
# Policy Check Functions
# =============================================================================


def policy_is_safe(text: str) -> bool:
    """
    Quick check if text contains any forbidden content.

    Args:
        text: Text to check (e.g., a runbook step)

    Returns:
        True if text is safe, False if it contains forbidden content
    """
    text_lower = text.lower()

    # Check substrings
    for forbidden in FORBIDDEN_SUBSTRINGS:
        if forbidden.lower() in text_lower:
            return False

    # Check regex patterns
    for pattern in COMPILED_PATTERNS:
        if pattern.search(text):
            return False

    return True


def find_forbidden_match(text: str) -> tuple[bool, str | None]:
    """
    Find which forbidden pattern matches the text.

    Args:
        text: Text to check

    Returns:
        Tuple of (is_forbidden, matched_pattern_or_none)
    """
    text_lower = text.lower()

    # Check substrings first
    for forbidden in FORBIDDEN_SUBSTRINGS:
        if forbidden.lower() in text_lower:
            return True, forbidden

    # Check regex patterns
    for i, pattern in enumerate(COMPILED_PATTERNS):
        if pattern.search(text):
            return True, FORBIDDEN_PATTERNS[i]

    return False, None


def get_safe_alternative(forbidden_pattern: str) -> str:
    """
    Get a safe alternative action for a forbidden pattern.

    Args:
        forbidden_pattern: The matched forbidden pattern

    Returns:
        Safe alternative action string
    """
    pattern_lower = forbidden_pattern.lower()

    for key, alternative in SAFE_ALTERNATIVES.items():
        if key.lower() in pattern_lower:
            return alternative

    # Default safe alternative
    return f"BLOCKED: Review and manually approve action. Original pattern: {forbidden_pattern}"


def rewrite_step(step: RunbookStep, forbidden_pattern: str) -> RunbookStep:
    """
    Rewrite a forbidden step to a safe investigative action.

    Args:
        step: The original runbook step
        forbidden_pattern: The matched forbidden pattern

    Returns:
        New RunbookStep with safe alternative
    """
    safe_action = get_safe_alternative(forbidden_pattern)

    return RunbookStep(
        step=f"[POLICY REWRITTEN] {safe_action}",
        why=f"Original action blocked by safety policy. Reason: contains '{forbidden_pattern}'. {step.why}",
        risk="low",  # Rewritten steps are always low risk
    )


def policy_check(runbook: RunbookResponse) -> dict[str, Any]:
    """
    Check and sanitize a runbook for policy violations.

    Scans each step for forbidden content and rewrites dangerous
    steps to safe investigative alternatives.

    Args:
        runbook: The RunbookResponse to check

    Returns:
        Dictionary with:
            - runbook: List of safe RunbookStep objects
            - changes: List of {'from': str, 'to': str} documenting changes
            - violations_found: int count of violations

    Example:
        >>> from app.models import RunbookResponse, RunbookStep
        >>> step = RunbookStep(step="rm -rf /tmp/malware", why="Clean up", risk="high")
        >>> runbook = RunbookResponse(runbook=[step], source="llm")
        >>> result = policy_check(runbook)
        >>> print(result['violations_found'])
        1
    """
    safe_steps: list[RunbookStep] = []
    changes: list[dict[str, str]] = []

    for step in runbook.runbook:
        is_forbidden, matched_pattern = find_forbidden_match(step.step)

        if is_forbidden and matched_pattern:
            # Rewrite the step
            safe_step = rewrite_step(step, matched_pattern)
            safe_steps.append(safe_step)

            changes.append(
                {
                    "from": step.step,
                    "to": safe_step.step,
                    "reason": f"Matched forbidden pattern: {matched_pattern}",
                }
            )
        else:
            # Step is safe, keep as-is
            safe_steps.append(step)

    return {
        "runbook": safe_steps,
        "changes": changes,
        "violations_found": len(changes),
    }


def policy_check_dict(runbook_dict: dict[str, Any]) -> dict[str, Any]:
    """
    Policy check for dictionary-format runbooks.

    Convenience wrapper when runbook is a dict rather than Pydantic model.

    Args:
        runbook_dict: Dictionary with 'runbook' key containing step dicts

    Returns:
        Same format as policy_check()
    """
    # Convert dict to Pydantic model
    steps = [
        RunbookStep(
            step=s.get("step", ""),
            why=s.get("why", ""),
            risk=s.get("risk", "medium"),
        )
        for s in runbook_dict.get("runbook", [])
    ]

    runbook = RunbookResponse(
        runbook=steps,
        source=runbook_dict.get("source", "unknown"),
    )

    result = policy_check(runbook)

    # Convert back to dict format
    return {
        "runbook": [
            {"step": s.step, "why": s.why, "risk": s.risk} for s in result["runbook"]
        ],
        "changes": result["changes"],
        "violations_found": result["violations_found"],
        "source": runbook.source,
    }


# =============================================================================
# Utility Functions
# =============================================================================


def get_policy_rules() -> dict[str, Any]:
    """
    Get current policy rules for documentation/debugging.

    Returns:
        Dictionary describing all active policy rules
    """
    return {
        "forbidden_substrings": FORBIDDEN_SUBSTRINGS,
        "forbidden_patterns": FORBIDDEN_PATTERNS,
        "safe_alternatives": SAFE_ALTERNATIVES,
    }


def validate_custom_runbook(steps: list[str]) -> list[dict[str, Any]]:
    """
    Validate a list of custom runbook step strings.

    Args:
        steps: List of step strings to validate

    Returns:
        List of validation results for each step
    """
    results = []

    for i, step in enumerate(steps):
        is_forbidden, pattern = find_forbidden_match(step)
        results.append(
            {
                "step_index": i,
                "step": step,
                "is_safe": not is_forbidden,
                "matched_pattern": pattern,
                "suggested_alternative": (
                    get_safe_alternative(pattern) if pattern else None
                ),
            }
        )

    return results

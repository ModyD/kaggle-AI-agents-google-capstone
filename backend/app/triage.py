"""
Deterministic, explainable rule-based triage engine.

This module implements a weighted scoring system for security incident triage.
The rules are transparent and auditable, providing clear contribution breakdowns.
"""

from typing import Any

# =============================================================================
# Scoring Weights (tune these based on your security policy)
# =============================================================================

WEIGHTS = {
    # Authentication anomalies
    "failed_logins_last_hour": {
        "threshold": 5,
        "weight": 3,
        "description": "Multiple failed login attempts indicate potential brute force",
    },
    # Process behavior
    "process_spawn_count": {
        "threshold": 20,
        "weight": 2,
        "description": "Excessive process spawning may indicate malware or cryptominer",
    },
    # File system activity
    "suspicious_file_activity": {
        "threshold": True,  # Boolean flag
        "weight": 2,
        "description": "Suspicious file modifications detected (e.g., ransomware patterns)",
    },
    # Network behavior
    "rare_outgoing_connection": {
        "threshold": True,  # Boolean flag
        "weight": 2,
        "description": "Connection to rarely-seen external IP (potential C2 traffic)",
    },
    # Privilege escalation indicators
    "privilege_escalation_attempt": {
        "threshold": True,
        "weight": 3,
        "description": "Detected attempt to escalate privileges",
    },
    # Data exfiltration signals
    "large_data_transfer": {
        "threshold": 100,  # MB
        "weight": 2,
        "description": "Unusually large outbound data transfer",
    },
    # Known bad indicators
    "known_malware_hash": {
        "threshold": True,
        "weight": 4,
        "description": "File hash matches known malware signature",
    },
    # Anomaly score from ML (if available)
    "anomaly_score": {
        "threshold": 0.8,
        "weight": 2,
        "description": "ML-based anomaly detection score",
    },
}

# Label thresholds
LABEL_THRESHOLDS = {
    "HIGH": 6,
    "MEDIUM": 3,
    # Below 3 = LOW
}


# =============================================================================
# Feature Normalization
# =============================================================================


def normalize_features(features: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize and validate incident features.

    Converts string values to appropriate types and provides defaults.

    Args:
        features: Raw feature dictionary from incident data

    Returns:
        Normalized feature dictionary with consistent types
    """
    normalized = {}

    for key, value in features.items():
        # Convert string booleans
        if isinstance(value, str):
            if value.lower() in ("true", "yes", "1"):
                normalized[key] = True
            elif value.lower() in ("false", "no", "0"):
                normalized[key] = False
            else:
                # Try numeric conversion
                try:
                    if "." in value:
                        normalized[key] = float(value)
                    else:
                        normalized[key] = int(value)
                except ValueError:
                    normalized[key] = value
        else:
            normalized[key] = value

    return normalized


# =============================================================================
# Scoring Functions
# =============================================================================


def evaluate_rule(
    feature_name: str,
    feature_value: Any,
    threshold: Any,
    weight: int,
) -> tuple[bool, int]:
    """
    Evaluate a single scoring rule.

    Args:
        feature_name: Name of the feature being evaluated
        feature_value: Current value of the feature
        threshold: Threshold value for triggering the rule
        weight: Points to add if rule triggers

    Returns:
        Tuple of (triggered: bool, points: int)
    """
    if feature_value is None:
        return False, 0

    # Boolean threshold
    if isinstance(threshold, bool):
        if bool(feature_value) == threshold:
            return True, weight
        return False, 0

    # Numeric threshold (greater-than comparison)
    try:
        if float(feature_value) >= float(threshold):
            return True, weight
    except (ValueError, TypeError):
        pass

    return False, 0


def score_incident(features: dict[str, Any]) -> tuple[str, int, list[tuple[str, int]]]:
    """
    Score an incident using the weighted rule engine.

    This function applies deterministic rules to incident features and
    produces an explainable severity classification.

    Args:
        features: Dictionary of incident features

    Returns:
        Tuple of:
            - label: "LOW", "MEDIUM", or "HIGH"
            - score: Total numeric score
            - contribs: List of (feature_name, points) for each contributing rule

    Example:
        >>> features = {"failed_logins_last_hour": 15, "suspicious_file_activity": True}
        >>> label, score, contribs = score_incident(features)
        >>> print(f"Severity: {label}, Score: {score}")
        Severity: HIGH, Score: 5
    """
    # Normalize input features
    normalized = normalize_features(features)

    total_score = 0
    contributions: list[tuple[str, int]] = []

    # Evaluate each rule
    for feature_name, rule in WEIGHTS.items():
        feature_value = normalized.get(feature_name)

        if feature_value is not None:
            triggered, points = evaluate_rule(
                feature_name=feature_name,
                feature_value=feature_value,
                threshold=rule["threshold"],
                weight=rule["weight"],
            )

            if triggered:
                total_score += points
                contributions.append((feature_name, points))

    # Determine label based on thresholds
    if total_score >= LABEL_THRESHOLDS["HIGH"]:
        label = "HIGH"
    elif total_score >= LABEL_THRESHOLDS["MEDIUM"]:
        label = "MEDIUM"
    else:
        label = "LOW"

    return label, total_score, contributions


def get_rule_description(feature_name: str) -> str:
    """Get the human-readable description for a rule."""
    rule = WEIGHTS.get(feature_name)
    if rule:
        return rule.get("description", "No description available")
    return "Unknown rule"


# =============================================================================
# Example Features for Testing
# =============================================================================


def get_example_features() -> dict[str, dict[str, Any]]:
    """
    Get example feature sets for testing and documentation.

    Returns:
        Dictionary of named example scenarios with their features
    """
    return {
        "high_severity_brute_force": {
            "failed_logins_last_hour": 50,
            "process_spawn_count": 5,
            "suspicious_file_activity": False,
            "rare_outgoing_connection": True,
            "source_ip": "10.0.0.50",
            "affected_user": "admin",
        },
        "high_severity_ransomware": {
            "failed_logins_last_hour": 0,
            "process_spawn_count": 100,
            "suspicious_file_activity": True,
            "rare_outgoing_connection": True,
            "known_malware_hash": True,
            "source_ip": "10.0.0.75",
        },
        "medium_severity_anomaly": {
            "failed_logins_last_hour": 8,
            "process_spawn_count": 10,
            "suspicious_file_activity": False,
            "rare_outgoing_connection": False,
            "source_ip": "192.168.1.100",
        },
        "low_severity_normal": {
            "failed_logins_last_hour": 2,
            "process_spawn_count": 5,
            "suspicious_file_activity": False,
            "rare_outgoing_connection": False,
            "source_ip": "192.168.1.50",
            "affected_user": "user1",
        },
    }


# =============================================================================
# Convenience Wrappers
# =============================================================================


def triage_incident(features: dict[str, Any]) -> dict[str, Any]:
    """
    Triage an incident and return a dictionary result.

    Convenience wrapper for score_incident that returns a dict.

    Args:
        features: Incident features

    Returns:
        Dictionary with label, score, contribs, and descriptions
    """
    label, score, contribs = score_incident(features)

    return {
        "label": label,
        "score": score,
        "contribs": contribs,
        "contrib_details": [
            {"feature": feat, "points": pts, "description": get_rule_description(feat)}
            for feat, pts in contribs
        ],
    }

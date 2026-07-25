"""Eligibility engine — evaluates scheme rules against farmer profile.

The engine takes:
1. A scheme's eligibility_rules (JSONB from the database)
2. A farmer's profile data (compiled from identity, plots, crop cycles)

And returns:
- is_eligible: True/False
- matched_conditions: list of conditions that passed
- failed_conditions: list of conditions that failed (with labels)

Rules format (stored in scheme_catalog.eligibility_rules):
{
    "role": "farmer",              // Required role
    "aadhaar_verified": true,     // Optional: must have Aadhaar verified
    "conditions": [
        {
            "field": "total_land_holding_ha",  // Farmer profile field
            "op": "gt",                        // Operator: gt, lt, eq, in, not_in, not_null
            "value": 0,                        // Comparison value
            "label": "Must own cultivable land"  // Human-readable description
        },
        ...
    ]
}

Supported operators:
- gt: field > value
- gte: field >= value
- lt: field < value
- lte: field <= value
- eq: field == value
- ne: field != value
- in: field in value (list)
- not_in: field not in value (list)
- not_null: field is not None

Supported fields (from farmer profile):
- role: user's role (farmer, agri_officer, etc.)
- aadhaar_verified: bool
- state: farmer's plot state (first plot's state)
- district: farmer's plot district
- total_land_holding_ha: total area across all plots
- irrigation_source: list of irrigation sources across plots
- has_active_crop_cycle: bool (any sown/growing crop cycle)
- bank_account_number: from insurance policy or profile
- occupation_category: farmer's occupation category (future field)
"""

from __future__ import annotations

from typing import Any


def evaluate_eligibility(
    rules: dict[str, Any],
    farmer_data: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate scheme eligibility rules against farmer profile data.

    Args:
        rules: The eligibility_rules JSONB from scheme_catalog
        farmer_data: Compiled farmer profile data (see _compile_farmer_data)

    Returns:
        {
            "eligible": bool,
            "matched_conditions": [{"field": ..., "label": ...}],
            "failed_conditions": [{"field": ..., "label": ..., "reason": ...}],
        }
    """
    matched: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []

    # Check role requirement
    required_role = rules.get("role")
    if required_role:
        farmer_role = farmer_data.get("role", "")
        if farmer_role == required_role:
            matched.append({"field": "role", "label": f"Role is {required_role}"})
        else:
            failed.append({
                "field": "role",
                "label": f"Must be a {required_role}",
                "reason": f"Current role is {farmer_role}",
            })

    # Check Aadhaar verification
    if rules.get("aadhaar_verified"):
        if farmer_data.get("aadhaar_verified"):
            matched.append({"field": "aadhaar_verified", "label": "Aadhaar verified"})
        else:
            failed.append({
                "field": "aadhaar_verified",
                "label": "Aadhaar verification required",
                "reason": "Aadhaar not verified. Complete e-KYC to become eligible.",
            })

    # Check each condition
    conditions = rules.get("conditions", [])
    for cond in conditions:
        field_name = cond.get("field", "")
        operator = cond.get("op", "")
        expected_value = cond.get("value")
        label = cond.get("label", f"{field_name} {operator} {expected_value}")

        actual_value = farmer_data.get(field_name)

        result, reason = _evaluate_condition(
            actual_value, operator, expected_value, field_name
        )

        if result:
            matched.append({"field": field_name, "label": label})
        else:
            failed.append({
                "field": field_name,
                "label": label,
                "reason": reason,
            })

    is_eligible = len(failed) == 0

    return {
        "eligible": is_eligible,
        "matched_conditions": matched,
        "failed_conditions": failed,
    }


def _evaluate_condition(
    actual: Any,
    operator: str,
    expected: Any,
    field_name: str,
) -> tuple[bool, str]:
    """Evaluate a single condition.

    Returns (passed, reason_if_failed).
    """
    if operator == "not_null":
        if actual is not None and actual != "":
            return True, ""
        return False, f"{field_name} is not provided"

    if actual is None:
        return False, f"{field_name} is not available in your profile"

    try:
        if operator == "gt":
            return float(actual) > float(expected), f"{field_name} must be greater than {expected}"
        elif operator == "gte":
            return float(actual) >= float(expected), f"{field_name} must be {expected} or greater"
        elif operator == "lt":
            return float(actual) < float(expected), f"{field_name} must be less than {expected}"
        elif operator == "lte":
            return float(actual) <= float(expected), f"{field_name} must be {expected} or less"
        elif operator == "eq":
            return actual == expected, f"{field_name} must be {expected}"
        elif operator == "ne":
            return actual != expected, f"{field_name} must not be {expected}"
        elif operator == "in":
            if isinstance(expected, list):
                # Handle list fields (e.g., irrigation_source is a list)
                if isinstance(actual, list):
                    return any(a in expected for a in actual), f"{field_name} must be one of: {', '.join(str(v) for v in expected)}"
                return actual in expected, f"{field_name} must be one of: {', '.join(str(v) for v in expected)}"
            return False, f"Invalid 'in' condition for {field_name}"
        elif operator == "not_in":
            if isinstance(expected, list):
                if isinstance(actual, list):
                    return not any(a in expected for a in actual), f"{field_name} must not be any of: {', '.join(str(v) for v in expected)}"
                return actual not in expected, f"{field_name} must not be any of: {', '.join(str(v) for v in expected)}"
            return False, f"Invalid 'not_in' condition for {field_name}"
        else:
            return False, f"Unknown operator: {operator}"
    except (ValueError, TypeError):
        return False, f"Cannot evaluate {field_name} {operator} {expected}"

from flask import Flask, render_template, request, jsonify
import math

from io import BytesIO
from datetime import datetime
from flask import send_file
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
)


app = Flask(__name__)

FACILITIES = {
    "hospital": {
        "name": "Hospital",
        "criticality": 5,
        "recommendation": (
            "Confirm potable water for drinking, cooking, patient care "
            "and other essential hospital needs."
        ),
    },
    "school": {
        "name": "School",
        "criticality": 3,
        "recommendation": (
            "Confirm drinking water, sanitation needs and supply "
            "arrangements for students and staff."
        ),
    },
    "care_home": {
        "name": "Care home",
        "criticality": 5,
        "recommendation": (
            "Confirm drinking water, residents' hydration and continuity "
            "of essential care."
        ),
    },
    "shelter": {
        "name": "Emergency shelter",
        "criticality": 4,
        "recommendation": (
            "Review potable water availability, sanitation and occupancy."
        ),
    },
    "emergency_services": {
        "name": "Emergency services",
        "criticality": 5,
        "recommendation": (
            "Confirm water availability for responders and essential "
            "emergency operations."
        ),
    },
}

PERMITTED_USES = {"toilet_flushing", "cleaning", "irrigation"}
SUPPORTED_USES = PERMITTED_USES | {"drinking_cooking"}


def finite_number(value, field_name):
    """Convert a value to a finite float or raise ValueError."""
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"{field_name} must be a number.")
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be a finite number.")
    return number


def assess_facility_priority(key, shortage, shortage_percent):
    """
    Explainable prototype-only triage score.
    This is not an official emergency or medical allocation standard.
    """
    if shortage <= 0:
        return {
            "priority_score": 0,
            "priority_level": "NO CURRENT SHORTAGE",
            "priority_reason": (
                "No shortage is calculated from the entered inputs. "
                "Continue checking reserves and delivery timing."
            ),
        }

    criticality = FACILITIES[key]["criticality"]

    if shortage_percent < 10:
        severity_points = 1
    elif shortage_percent < 20:
        severity_points = 2
    elif shortage_percent < 30:
        severity_points = 3
    else:
        severity_points = 4

    score = criticality * 10 + severity_points * 10

    if score >= 80:
        level = "IMMEDIATE REVIEW"
    elif score >= 60:
        level = "HIGH PRIORITY"
    else:
        level = "PRIORITY REVIEW"

    reason = (
        f"Calculated shortage is {shortage_percent:.1f}% of daily demand. "
        f"The prototype assigns this facility a criticality factor of "
        f"{criticality}/5. Human review is required."
    )

    return {
        "priority_score": score,
        "priority_level": level,
        "priority_reason": reason,
    }


def build_decision_support(analysis):
    """Produce explainable, rule-based decision support without an external AI."""
    facilities = analysis["facility_results"]
    shortage_facilities = [
        facility for facility in facilities if facility["shortage_l"] > 0
    ]

    missing_checks = []
    if not analysis["alternative_verified"]:
        missing_checks.append("verify the alternative-water source")
    if not analysis["alternative_suitable"]:
        missing_checks.append("confirm suitability for the selected non-potable use")
    if analysis["intended_use"] == "drinking_cooking":
        missing_checks.append(
            "ensure drinking and cooking water is potable-quality water"
        )

    if shortage_facilities:
        top = shortage_facilities[0]
        summary = (
            f"{len(shortage_facilities)} selected facility/facilities have "
            f"a calculated potable-water shortage totalling "
            f"{analysis['shortage_l']:,.0f} L/day. The highest-ranked "
            f"facility is {top['name']} ({top['priority_level']})."
        )
        next_steps = [
            f"Review the {top['name']} shortage first under the prototype's "
            "priority rules.",
            "Check each facility's actual storage, reserve requirements, "
            "and time-specific demand.",
            "Compare verified available supply and delivery capacity with "
            "the shortages before approving a delivery plan.",
        ]
    else:
        summary = (
            "No facility-level potable-water shortage is calculated from "
            "the entered values. This does not confirm real-world supply "
            "reliability or sufficient emergency reserves."
        )
        next_steps = [
            "Confirm actual supplies and delivery schedules at each facility.",
            "Check reserve requirements and demand changes before closing the scenario.",
        ]

    if missing_checks:
        next_steps.append("Before considering reuse, " + "; ".join(missing_checks) + ".")

    next_steps.append(
        "This is rule-based decision support, not a live AI agent or "
        "automated allocation decision. A responsible human must verify "
        "the inputs and approve any real-world action."
    )

    return {
        "mode": "rule_based_explainable_decision_support",
        "summary": summary,
        "key_findings": [
            {
                "facility": facility["name"],
                "priority_level": facility["priority_level"],
                "priority_score": facility["priority_score"],
                "shortage_l": facility["shortage_l"],
                "reason": facility["priority_reason"],
            }
            for facility in facilities
        ],
        "missing_checks": missing_checks,
        "recommended_next_steps": next_steps,
        "human_approval_required": True,
    }


def plan_deliveries(facility_results, sources, vehicles):
    """
    Create a simple proposed delivery plan using manually entered data.
    Plans only potable water for potable shortages. This is a prototype
    heuristic, not a route optimiser or a live dispatch system.
    """
    source_remaining = []
    for index, source in enumerate(sources, start=1):
        source_remaining.append({
            "source_id": source.get("source_id") or f"S{index}",
            "name": source["name"],
            "available_l": source["available_l"],
            "potable_confirmed": source["potable_confirmed"],
        })

    vehicle_remaining = []
    for index, vehicle in enumerate(vehicles, start=1):
        vehicle_remaining.append({
            "vehicle_id": vehicle.get("vehicle_id") or f"V{index}",
            "name": vehicle["name"],
            "capacity_l": vehicle["capacity_l"],
            "available": vehicle["available"],
            "eta_minutes": vehicle["eta_minutes"],
        })

    remaining_shortages = [
        {
            "key": facility["key"],
            "name": facility["name"],
            "priority_score": facility["priority_score"],
            "priority_level": facility["priority_level"],
            "shortage_l": facility["shortage_l"],
            "remaining_l": facility["shortage_l"],
        }
        for facility in sorted(
            facility_results,
            key=lambda item: item["priority_score"],
            reverse=True,
        )
        if facility["shortage_l"] > 0
    ]

    deliveries = []
    total_planned_l = 0.0
    unallocated_l = 0.0
    vehicle_index = 0

    for shortage in remaining_shortages:
        need = shortage["remaining_l"]

        for source in source_remaining:
            if need <= 0:
                break
            if not source["potable_confirmed"] or source["available_l"] <= 0:
                continue

            while need > 0 and source["available_l"] > 0:
                while (
                    vehicle_index < len(vehicle_remaining)
                    and (
                        not vehicle_remaining[vehicle_index]["available"]
                        or vehicle_remaining[vehicle_index]["capacity_l"] <= 0
                    )
                ):
                    vehicle_index += 1

                if vehicle_index >= len(vehicle_remaining):
                    break

                vehicle = vehicle_remaining[vehicle_index]
                quantity = min(
                    need,
                    source["available_l"],
                    vehicle["capacity_l"],
                )

                if quantity <= 0:
                    break

                deliveries.append({
                    "facility_key": shortage["key"],
                    "facility": shortage["name"],
                    "priority_level": shortage["priority_level"],
                    "source_id": source["source_id"],
                    "source": source["name"],
                    "vehicle_id": vehicle["vehicle_id"],
                    "vehicle": vehicle["name"],
                    "quantity_l": round(quantity, 2),
                    "eta_minutes": vehicle["eta_minutes"],
                    "status": "PROPOSED — HUMAN APPROVAL REQUIRED",
                })

                need -= quantity
                source["available_l"] -= quantity
                vehicle["capacity_l"] -= quantity
                total_planned_l += quantity

                # One vehicle is treated as one delivery trip in this
                # simple MVP plan. It cannot be reused for another facility.
                vehicle["available"] = False
                vehicle_index += 1

        shortage["remaining_l"] = round(max(0.0, need), 2)
        unallocated_l += max(0.0, need)

    return {
        "delivery_plan": deliveries,
        "total_planned_l": round(total_planned_l, 2),
        "unallocated_shortage_l": round(unallocated_l, 2),
        "source_notes": [
            "Only sources marked as potable-confirmed are considered for potable shortages.",
            "Availability and potable confirmation are manually entered assumptions, not live verification.",
            "Each vehicle is used for at most one proposed delivery in this prototype.",
            "ETA is an entered estimate, not a live traffic calculation.",
            "Every delivery is a proposal and requires human approval."
        ],
    }


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/api/analyze", methods=["POST"])
def analyze():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "Invalid request data."}), 400

    facility_types = data.get("facility_types", [])
    if (
        not isinstance(facility_types, list)
        or not facility_types
        or not all(isinstance(item, str) and item in FACILITIES for item in facility_types)
    ):
        return jsonify({"error": "Select at least one valid facility."}), 400

    facility_types = list(dict.fromkeys(facility_types))
    intended_use = data.get("intended_use", "toilet_flushing")
    if not isinstance(intended_use, str) or intended_use not in SUPPORTED_USES:
        return jsonify({"error": "Select a supported intended water use."}), 400

    facility_inputs = []
    total_demand = 0.0
    total_potable_available = 0.0
    total_eligible_demand = 0.0

    try:
        for key in facility_types:
            demand = finite_number(data.get(f"demand_{key}"), f"{key} demand")
            potable = finite_number(data.get(f"potable_{key}"), f"{key} potable supply")
            eligible_percent = finite_number(
                data.get(f"eligible_{key}"), f"{key} eligibility percentage"
            )

            if demand <= 0 or potable < 0:
                raise ValueError("Demand must be positive and supply cannot be negative.")
            if not 0 <= eligible_percent <= 100:
                raise ValueError("Eligibility must be between 0 and 100 percent.")

            eligible_demand = demand * eligible_percent / 100.0
            facility_inputs.append({
                "key": key,
                "name": FACILITIES[key]["name"],
                "demand": demand,
                "potable": potable,
                "eligible": eligible_demand,
            })
            total_demand += demand
            total_potable_available += potable
            total_eligible_demand += eligible_demand

        alternative_available = finite_number(
            data.get("alternative_available", 0), "Alternative water available"
        )
        if alternative_available < 0:
            raise ValueError("Alternative water available cannot be negative.")
    except ValueError as exc:
        return jsonify({
            "error": (
                "Please check the inputs. Daily demand must be positive, "
                "supplies must be non-negative, and eligibility must be "
                "between 0 and 100%. Details: " + str(exc)
            )
        }), 400

    alternative_verified = data.get("alternative_verified") is True
    alternative_suitable = data.get("alternative_suitable") is True
    alternative_accepted = (
        alternative_verified
        and alternative_suitable
        and intended_use in PERMITTED_USES
    )
    usable_alternative = alternative_available if alternative_accepted else 0.0
    substitution = min(total_eligible_demand, usable_alternative)

    facility_results = []
    total_shortage = 0.0
    total_surplus = 0.0

    for facility in facility_inputs:
        if total_eligible_demand > 0:
            facility_substitution = (
                substitution * facility["eligible"] / total_eligible_demand
            )
        else:
            facility_substitution = 0.0

        remaining_demand = facility["demand"] - facility_substitution
        shortage = max(0.0, remaining_demand - facility["potable"])
        surplus = max(0.0, facility["potable"] - remaining_demand)
        shortage_percent = shortage / facility["demand"] * 100.0
        priority = assess_facility_priority(
            facility["key"], shortage, shortage_percent
        )

        if shortage > 0:
            review_status = "URGENT REVIEW"
        elif surplus == 0:
            review_status = "CHECK RESERVES"
        else:
            review_status = "COVERED IN SCENARIO"

        facility_results.append({
            "key": facility["key"],
            "name": facility["name"],
            "total_demand_l": round(facility["demand"], 2),
            "potable_available_l": round(facility["potable"], 2),
            "eligible_demand_l": round(facility["eligible"], 2),
            "substitution_l": round(facility_substitution, 2),
            "remaining_potable_demand_l": round(remaining_demand, 2),
            "shortage_l": round(shortage, 2),
            "surplus_l": round(surplus, 2),
            "shortage_percent": round(shortage_percent, 2),
            "review_status": review_status,
            "priority_score": priority["priority_score"],
            "priority_level": priority["priority_level"],
            "priority_reason": priority["priority_reason"],
        })

        total_shortage += shortage
        total_surplus += surplus

    facility_results.sort(
        key=lambda item: item["priority_score"], reverse=True
    )

    remaining_potable_demand = total_demand - substitution
    savings_percent = substitution / total_demand * 100.0 if total_demand else 0.0
    shortage_percent = total_shortage / total_demand * 100.0 if total_demand else 0.0

    if total_shortage == 0:
        risk_level = "COVERED"
    elif shortage_percent < 15:
        risk_level = "MODERATE"
    elif shortage_percent < 30:
        risk_level = "HIGH"
    else:
        risk_level = "CRITICAL"

    status = "SHORTAGE" if total_shortage > 0 else "COVERED"

    if total_shortage > 0:
        diagnosis = (
            f"The selected facilities have a combined calculated shortage of "
            f"{total_shortage:,.0f} L/day. Review the ranked facility-level "
            "shortages. Surplus at one facility is not assumed transferable."
        )
        first_action = (
            f"Review options to address up to {total_shortage:,.0f} L/day "
            "of calculated potable-water shortages."
        )
    else:
        diagnosis = (
            "Entered supplies cover calculated remaining potable demand at "
            "each selected facility in this scenario. Verify reserves and timing."
        )
        first_action = (
            "Confirm water availability at each facility and at the times needed."
        )

    actions = [first_action]
    safety_warning = None

    if alternative_available > 0 and not alternative_accepted:
        if intended_use == "drinking_cooking":
            reason = (
                "Alternative water cannot replace potable-quality water "
                "for drinking or cooking."
            )
        elif not alternative_verified:
            reason = "The alternative-water source has not been verified."
        elif not alternative_suitable:
            reason = (
                "Suitability for the selected non-potable use has not been confirmed."
            )
        else:
            reason = (
                "The selected water use is not permitted for alternative-water substitution."
            )

        safety_warning = (
            "SAFETY WARNING: " + reason
            + " The alternative water has been excluded from the estimate."
        )
        actions.append(
            reason + " Obtain appropriate verification and approvals before considering reuse."
        )

    for key in facility_types:
        actions.append(FACILITIES[key]["recommendation"])

    if total_eligible_demand > substitution:
        actions.append(
            "Review remaining eligible non-potable demand. Do not assume additional "
            "substitution is safe or feasible without checks."
        )

    actions.append(
        "Verify inputs, water quality, storage, delivery capacity, minimum reserves "
        "and facility requirements before acting."
    )

    result = {
        "total_demand_l": round(total_demand, 2),
        "eligible_demand_l": round(total_eligible_demand, 2),
        "alternative_available_l": round(alternative_available, 2),
        "verified_alternative_l": round(usable_alternative, 2),
        "potable_saved_l": round(substitution, 2),
        "remaining_potable_demand_l": round(remaining_potable_demand, 2),
        "potable_available_l": round(total_potable_available, 2),
        "shortage_l": round(total_shortage, 2),
        "surplus_l": round(total_surplus, 2),
        "savings_percent": round(savings_percent, 2),
        "shortage_percent": round(shortage_percent, 2),
        "risk_level": risk_level,
        "status": status,
        "diagnosis": diagnosis,
        "recommendation": first_action,
        "recommended_actions": actions,
        "safety_warning": safety_warning,
        "intended_use": intended_use,
        "facility_types": facility_types,
        "facility_names": [FACILITIES[key]["name"] for key in facility_types],
        "facility_results": facility_results,
        "alternative_verified": alternative_verified,
        "alternative_suitable": alternative_suitable,
        "assumptions": [
            "All values are manually entered scenario inputs, not live measurements.",
            "Alternative-water verification checkboxes are assumptions, not laboratory certification.",
            "Alternative water is never counted for drinking or cooking.",
            "Eligibility percentages are user estimates, not measured facility data.",
            "Potential substitution is distributed proportionally for analysis only; it is not an allocation instruction.",
            "Each facility's potable supply is treated as facility-specific; surpluses are not transferred between facilities.",
            "Facility results do not model minimum reserves, delivery schedules, storage constraints or changing demand.",
            "Priority scores and risk thresholds are prototype-defined, not official emergency classifications.",
            "Human review and appropriate water-quality verification are required before real-world decisions.",
        ],
    }
    result["decision_support"] = build_decision_support(result)
    return jsonify(result)


@app.route("/api/plan-deliveries", methods=["POST"])
def api_plan_deliveries():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Invalid request data."}), 400

    analysis = data.get("analysis")
    sources = data.get("sources")
    vehicles = data.get("vehicles")

    if not isinstance(analysis, dict) or not isinstance(analysis.get("facility_results"), list):
        return jsonify({
            "error": "Provide a completed analysis result with facility_results."
        }), 400
    if not isinstance(sources, list) or not isinstance(vehicles, list):
        return jsonify({
            "error": "Sources and vehicles must both be lists."
        }), 400

    try:
        clean_sources = []
        for item in sources:
            if not isinstance(item, dict):
                raise ValueError("Each source must be an object.")
            name = str(item.get("name", "")).strip()
            if not name:
                raise ValueError("Each source needs a name.")
            available = finite_number(item.get("available_l"), "Source available litres")
            if available < 0:
                raise ValueError("Source quantity cannot be negative.")
            clean_sources.append({
                "source_id": str(item.get("source_id", "")),
                "name": name,
                "available_l": available,
                "potable_confirmed": item.get("potable_confirmed") is True,
            })

        clean_vehicles = []
        for item in vehicles:
            if not isinstance(item, dict):
                raise ValueError("Each vehicle must be an object.")
            name = str(item.get("name", "")).strip()
            if not name:
                raise ValueError("Each vehicle needs a name.")
            capacity = finite_number(item.get("capacity_l"), "Vehicle capacity")
            eta = finite_number(item.get("eta_minutes"), "Vehicle ETA")
            if capacity <= 0 or eta < 0:
                raise ValueError("Vehicle capacity must be positive and ETA non-negative.")
            clean_vehicles.append({
                "vehicle_id": str(item.get("vehicle_id", "")),
                "name": name,
                "capacity_l": capacity,
                "available": item.get("available") is True,
                "eta_minutes": eta,
            })
    except ValueError as exc:
        return jsonify({"error": "Check supply/vehicle inputs: " + str(exc)}), 400

    plan = plan_deliveries(analysis["facility_results"], clean_sources, clean_vehicles)
    return jsonify(plan)


@app.route("/api/decision-support", methods=["POST"])
def api_decision_support():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Invalid request data."}), 400

    analysis = data.get("analysis")
    if not isinstance(analysis, dict) or not isinstance(analysis.get("facility_results"), list):
        return jsonify({
            "error": "Provide a completed analysis result with facility_results."
        }), 400

    return jsonify(build_decision_support(analysis))



@app.route("/api/emergency-report", methods=["POST"])
def emergency_report():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "Invalid report request."}), 400

    analysis = data.get("analysis")
    delivery = data.get("delivery_plan")

    if not isinstance(analysis, dict):
        return jsonify({"error": "Run scenario analysis first."}), 400

    required = [
        "risk_level", "total_demand_l", "potable_available_l",
        "shortage_l", "facility_results"
    ]
    if any(key not in analysis for key in required):
        return jsonify({"error": "Analysis data is incomplete."}), 400

    if not isinstance(analysis["facility_results"], list):
        return jsonify({"error": "Invalid facility results."}), 400

    if delivery is not None and not isinstance(delivery, dict):
        return jsonify({"error": "Invalid delivery plan."}), 400

    def number(value):
        try:
            result = float(value)
            return result if math.isfinite(result) else 0.0
        except (TypeError, ValueError, OverflowError):
            return 0.0

    def fmt(value):
        return f"{number(value):,.1f} L"

    def safe(value):
        return str(value if value is not None else "Not provided")

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=40,
        leftMargin=40,
        topMargin=42,
        bottomMargin=42,
        title="PotableShield Emergency Readiness Report",
        author="PotableShield"
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="ReportTitle",
        parent=styles["Title"],
        fontSize=21,
        leading=27,
        textColor=colors.HexColor("#12304A"),
        alignment=TA_CENTER,
        spaceAfter=8
    ))
    styles.add(ParagraphStyle(
        name="SectionHeading",
        parent=styles["Heading2"],
        textColor=colors.HexColor("#087E8B"),
        spaceBefore=14,
        spaceAfter=7
    ))
    styles.add(ParagraphStyle(
        name="SmallNote",
        parent=styles["BodyText"],
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#555555")
    ))

    story = [
        Paragraph("PotableShield", styles["ReportTitle"]),
        Paragraph(
            "Emergency Water Readiness Report",
            styles["Heading2"]
        ),
        Paragraph(
            "Generated: " + datetime.now().astimezone().strftime(
                "%d %b %Y, %I:%M %p %Z"
            ),
            styles["Normal"]
        ),
        Spacer(1, 14),
        Paragraph("1. Emergency Summary", styles["SectionHeading"])
    ]

    metrics = [
        ["Indicator", "Calculated result"],
        ["Risk level", safe(analysis.get("risk_level"))],
        ["Total daily demand", fmt(analysis.get("total_demand_l"))],
        ["Potable supply entered", fmt(analysis.get("potable_available_l"))],
        ["Calculated shortage", fmt(analysis.get("shortage_l"))],
        ["Potential potable water savings", fmt(analysis.get("potable_saved_l"))],
        ["Shortage as share of demand",
         f"{number(analysis.get('shortage_percent')):.1f}%"]
    ]

    table = Table(metrics, colWidths=[245, 230], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#12304A")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D6DEE8")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#F2F6FA")]),
        ("PADDING", (0, 0), (-1, -1), 7),
        ("VALIGN", (0, 0), (-1, -1), "TOP")
    ]))
    story.append(table)

    story.append(Paragraph(
        "2. Facility Priorities", styles["SectionHeading"]
    ))

    facility_rows = [[
        "Facility", "Priority", "Demand", "Supply", "Shortage"
    ]]

    for facility in analysis["facility_results"]:
        facility_rows.append([
            Paragraph(safe(facility.get("name")), styles["SmallNote"]),
            Paragraph(safe(facility.get("priority_level")), styles["SmallNote"]),
            fmt(facility.get("total_demand_l")),
            fmt(facility.get("potable_available_l")),
            fmt(facility.get("shortage_l"))
        ])

    if len(facility_rows) == 1:
        facility_rows.append(["No facility results", "-", "-", "-", "-"])

    facility_table = Table(
        facility_rows,
        colWidths=[95, 100, 85, 85, 85],
        repeatRows=1
    )
    facility_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#087E8B")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D6DEE8")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#F2F6FA")]),
        ("PADDING", (0, 0), (-1, -1), 5),
        ("VALIGN", (0, 0), (-1, -1), "TOP")
    ]))
    story.append(facility_table)

    story.append(Paragraph(
        "3. Proposed Delivery Plan", styles["SectionHeading"]
    ))

    if delivery is None:
        story.append(Paragraph(
            "No delivery plan was supplied. Generate a delivery plan in "
            "the dashboard before creating a report that includes deliveries.",
            styles["BodyText"]
        ))
    else:
        deliveries = delivery.get("delivery_plan", [])
        if not isinstance(deliveries, list):
            return jsonify({"error": "Invalid delivery entries."}), 400

        story.append(Paragraph(
            "Total proposed: " + fmt(delivery.get("total_planned_l")),
            styles["BodyText"]
        ))
        story.append(Paragraph(
            "Shortage left unallocated: "
            + fmt(delivery.get("unallocated_shortage_l")),
            styles["BodyText"]
        ))
        story.append(Spacer(1, 6))

        delivery_rows = [[
            "Facility", "Source", "Vehicle", "Quantity", "ETA"
        ]]

        for item in deliveries:
            if not isinstance(item, dict):
                continue
            delivery_rows.append([
                Paragraph(safe(item.get("facility")), styles["SmallNote"]),
                Paragraph(safe(item.get("source")), styles["SmallNote"]),
                Paragraph(safe(item.get("vehicle")), styles["SmallNote"]),
                fmt(item.get("quantity_l")),
                f"{number(item.get('eta_minutes')):.0f} min"
            ])

        if len(delivery_rows) == 1:
            delivery_rows.append(["No proposed deliveries", "-", "-", "-", "-"])

        delivery_table = Table(
            delivery_rows,
            colWidths=[105, 105, 90, 85, 65],
            repeatRows=1
        )
        delivery_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#12304A")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D6DEE8")),
            ("PADDING", (0, 0), (-1, -1), 5),
            ("VALIGN", (0, 0), (-1, -1), "TOP")
        ]))
        story.append(delivery_table)

    story.append(Paragraph(
        "4. Recommended Actions", styles["SectionHeading"]
    ))
    for action in analysis.get("recommended_actions", []):
        story.append(Paragraph(
            "• " + safe(action), styles["BodyText"]
        ))
        story.append(Spacer(1, 4))

    story.append(Paragraph(
        "5. Assumptions and Safety", styles["SectionHeading"]
    ))
    for assumption in analysis.get("assumptions", []):
        story.append(Paragraph(
            "• " + safe(assumption), styles["SmallNote"]
        ))
        story.append(Spacer(1, 3))

    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "<b>IMPORTANT:</b> This report uses manually entered scenario "
        "data and prototype calculations. It does not verify live water "
        "availability, water quality, vehicle availability or actual "
        "delivery times. Proposed deliveries are not dispatch orders. "
        "A responsible human must validate the information and approve "
        "actions before real-world use.",
        styles["SmallNote"]
    ))

    try:
        doc.build(story)
        buffer.seek(0)
        return send_file(
            buffer,
            mimetype="application/pdf",
            as_attachment=True,
            download_name="PotableShield_Emergency_Report.pdf"
        )
    except Exception:
        app.logger.exception("Emergency report generation failed.")
        return jsonify({"error": "Could not generate the PDF report."}), 500

if __name__ == "__main__":
    app.run(debug=True)

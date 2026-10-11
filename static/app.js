"use strict";

// PotableShield - Frontend JavaScript
// Connects the scenario form to the Flask API in app.py.

const form = document.querySelector("#scenario");
const results = document.querySelector("#results");
const message = document.querySelector("#message");
const analyseButton = document.querySelector("#analyse-button");

let latestAnalysis = null;

const FACILITY_LABELS = {
    hospital: "Hospital",
    school: "School",
    care_home: "Care home",
    shelter: "Emergency shelter",
    emergency_services: "Emergency services"
};

// ---------- General helpers ----------

function getElement(id) {
    return document.getElementById(id);
}

function setText(id, value) {
    const element = getElement(id);

    if (element) {
        element.textContent = value ?? "";
    }
}

function showMessage(text, isError = false) {
    if (!message) return;

    message.textContent = String(text ?? "");
    message.hidden = false;
    message.classList.toggle("error", isError);
}

function clearMessage() {
    if (!message) return;

    message.textContent = "";
    message.hidden = true;
    message.classList.remove("error");
}

function litres(value) {
    const number = Number(value ?? 0);

    if (!Number.isFinite(number)) return "N/A";

    return number.toLocaleString("en-IN", {
        maximumFractionDigits: 1
    }) + " L";
}

function percentage(value) {
    const number = Number(value ?? 0);

    if (!Number.isFinite(number)) return "N/A";

    return number.toLocaleString("en-IN", {
        maximumFractionDigits: 1
    }) + "%";
}

function clearChildren(element) {
    if (element) {
        element.replaceChildren();
    }
}

function addTextItem(container, text) {
    if (!container) return;

    const item = document.createElement("li");
    item.textContent = String(text ?? "");
    container.appendChild(item);
}

function addDetail(container, label, value) {
    if (!container) return;

    const item = document.createElement("li");
    const strong = document.createElement("strong");

    strong.textContent = `${label}: `;

    item.append(
        strong,
        document.createTextNode(String(value ?? ""))
    );

    container.appendChild(item);
}

function makeElement(tag, className, text) {
    const element = document.createElement(tag);

    if (className) {
        element.className = className;
    }

    if (text !== undefined && text !== null) {
        element.textContent = String(text);
    }

    return element;
}

function formatRiskClass(value) {
    return String(value ?? "unknown")
        .toLowerCase()
        .replace(/[^a-z0-9-]/g, "-");
}

function readNumber(field, label, minimum = 0) {
    if (!field || String(field.value).trim() === "") {
        throw new Error(`Enter a value for ${label}.`);
    }

    const value = Number(field.value);

    if (!Number.isFinite(value) || value < minimum) {
        throw new Error(
            `${label} must be a valid number greater than or equal to ${minimum}.`
        );
    }

    return value;
}

// ---------- Build request for app.py ----------

function buildPayload() {
    if (!form) {
        throw new Error(
            'The scenario form with id="scenario" was not found.'
        );
    }

    const selectedFacilities = Array.from(
        form.querySelectorAll(
            'input[name="facility_types"]:checked'
        )
    ).map(input => input.value);

    if (selectedFacilities.length === 0) {
        throw new Error(
            "Select at least one facility before analysing."
        );
    }

    for (const key of selectedFacilities) {
        if (!Object.prototype.hasOwnProperty.call(
            FACILITY_LABELS,
            key
        )) {
            throw new Error(
                `Unsupported facility type: ${key}`
            );
        }
    }

    const intendedUseField =
        form.elements.namedItem("intended_use");

    const alternativeField =
        form.elements.namedItem("alternative_available");

    const payload = {
        facility_types: [...new Set(selectedFacilities)],

        intended_use:
            intendedUseField?.value || "toilet_flushing",

        alternative_available: readNumber(
            alternativeField,
            "alternative water available"
        ),

        alternative_verified: Boolean(
            form.elements.namedItem("alternative_verified")?.checked
        ),

        alternative_suitable: Boolean(
            form.elements.namedItem("alternative_suitable")?.checked
        )
    };

    for (const key of payload.facility_types) {
        const demandField =
            form.elements.namedItem(`demand_${key}`);

        const potableField =
            form.elements.namedItem(`potable_${key}`);

        const eligibleField =
            form.elements.namedItem(`eligible_${key}`);

        const label = FACILITY_LABELS[key];

        payload[`demand_${key}`] = readNumber(
            demandField,
            `${label} daily demand`
        );

        payload[`potable_${key}`] = readNumber(
            potableField,
            `${label} potable supply`
        );

        payload[`eligible_${key}`] = readNumber(
            eligibleField,
            `${label} eligible non-potable demand`
        );
    }

    return payload;
}

// ---------- Overall analysis display ----------

function renderRisk(data) {
    const panel = getElement("risk-panel");

    setText("risk-level", data.risk_level);
    setText("risk-description", data.diagnosis);
    setText("shortage-percent", percentage(data.shortage_percent));
    setText("saved", litres(data.potable_saved_l));
    setText("percent", percentage(data.savings_percent));
    setText("remaining", litres(data.remaining_potable_demand_l));
    setText("shortage", litres(data.shortage_l));
    setText("status", data.status);

    if (panel) {
        panel.classList.remove(
            "covered",
            "moderate",
            "high",
            "critical"
        );

        panel.classList.add(
            formatRiskClass(data.risk_level)
        );
    }
}

function renderDetails(data) {
    const details = getElement("details");

    if (!details) return;

    clearChildren(details);

    addDetail(
        details,
        "Selected facilities",
        (data.facility_names || []).join(", ") || "None"
    );

    addDetail(
        details,
        "Intended alternative-water use",
        String(data.intended_use || "").replaceAll("_", " ")
    );

    addDetail(details, "Total daily demand",
        litres(data.total_demand_l));

    addDetail(details, "Eligible non-potable demand",
        litres(data.eligible_demand_l));

    addDetail(details, "Alternative water reported available",
        litres(data.alternative_available_l));

    addDetail(details, "Alternative water accepted by the model",
        litres(data.verified_alternative_l));

    addDetail(details, "Total potable supply",
        litres(data.potable_available_l));

    addDetail(details, "Calculated daily shortage",
        litres(data.shortage_l));

    addDetail(details, "Calculated surplus",
        litres(data.surplus_l));
}

function renderActions(data) {
    const actionsList = getElement("actions-list");

    if (!actionsList) return;

    clearChildren(actionsList);

    (data.recommended_actions || []).forEach(action => {
        addTextItem(actionsList, action);
    });
}

function renderAssumptions(data) {
    const assumptions = getElement("assumptions");

    if (!assumptions) return;

    clearChildren(assumptions);

    (data.assumptions || []).forEach(item => {
        addTextItem(assumptions, item);
    });
}

// ---------- Facility-level results ----------

function renderFacilities(data) {
    const container = getElement("facility-results");

    if (!container) return;

    clearChildren(container);

    const facilities = data.facility_results || [];

    if (facilities.length === 0) {
        container.appendChild(
            makeElement(
                "p",
                "",
                "No facility results were returned."
            )
        );

        return;
    }

    facilities.forEach(facility => {
        const card = makeElement(
            "article",
            "facility-result-card"
        );

        const heading = makeElement(
            "h3",
            "",
            facility.name || "Facility"
        );

        const priority = makeElement(
            "p",
            "facility-priority",
            `Priority: ${facility.priority_level || "Not available"}`
        );

        const review = makeElement(
            "p",
            "facility-review-status",
            `Status: ${facility.review_status || "Not available"}`
        );

        const score = makeElement(
            "p",
            "",
            `Prototype priority score: ${
                facility.priority_score ?? "N/A"
            }`
        );

        const metrics = document.createElement("ul");

        addDetail(metrics, "Daily demand",
            litres(facility.total_demand_l));

        addDetail(metrics, "Potable supply available",
            litres(facility.potable_available_l));

        addDetail(metrics, "Eligible non-potable demand",
            litres(facility.eligible_demand_l));

        addDetail(metrics, "Potential substitution in this scenario",
            litres(facility.substitution_l));

        addDetail(metrics, "Remaining demand after substitution",
            litres(facility.remaining_potable_demand_l));

        addDetail(metrics, "Calculated shortage",
            litres(facility.shortage_l));

        addDetail(metrics, "Calculated surplus",
            litres(facility.surplus_l));

        addDetail(metrics, "Shortage as a share of demand",
            percentage(facility.shortage_percent));

        const reason = makeElement(
            "p",
            "facility-priority-reason",
            facility.priority_reason ||
                "No priority explanation provided."
        );

        card.append(
            heading,
            priority,
            review,
            score,
            metrics,
            reason
        );

        container.appendChild(card);
    });
}

// ---------- Explainable decision support ----------

function renderDecisionSupport(data) {
    const decision = data.decision_support;

    if (!decision) {
        setText(
            "decision-support-summary",
            "Decision-support information was not returned."
        );

        clearChildren(getElement("decision-findings"));
        clearChildren(getElement("decision-next-steps"));

        setText(
            "human-approval-note",
            "Verify all inputs and obtain human approval before acting."
        );

        return;
    }

    setText(
        "decision-support-summary",
        decision.summary || ""
    );

    const findings = getElement("decision-findings");

    if (findings) {
        clearChildren(findings);

        (decision.key_findings || []).forEach(item => {
            const listItem = document.createElement("li");

            const heading = makeElement(
                "strong",
                "",
                `${item.facility || "Facility"}: ${
                    item.priority_level || "Priority unavailable"
                }`
            );

            const explanation = makeElement(
                "p",
                "",
                item.reason || "No explanation provided."
            );

            const shortage = makeElement(
                "p",
                "",
                `Calculated shortage: ${litres(item.shortage_l)}`
            );

            listItem.append(
                heading,
                explanation,
                shortage
            );

            findings.appendChild(listItem);
        });

        if ((decision.key_findings || []).length === 0) {
            addTextItem(
                findings,
                "No findings were returned."
            );
        }
    }

    const nextSteps = getElement("decision-next-steps");

    if (nextSteps) {
        clearChildren(nextSteps);

        (decision.recommended_next_steps || []).forEach(step => {
            addTextItem(nextSteps, step);
        });
    }

    const approvalNote = getElement("human-approval-note");

    if (approvalNote) {
        approvalNote.textContent =
            decision.human_approval_required
                ? "Human approval required: verify the inputs, actual supply, water quality, and operational constraints before taking action."
                : "Review the scenario and verify the inputs before taking action.";
    }
}

// ---------- Full results rendering ----------

function renderAnalysis(data) {
    if (!data || typeof data !== "object" || Array.isArray(data)) {
        throw new Error(
            "The server returned an invalid analysis result."
        );
    }

    latestAnalysis = data;

    if (results) {
        results.hidden = false;
    }

    renderRisk(data);
    renderDetails(data);
    renderFacilities(data);
    renderActions(data);
    renderAssumptions(data);
    renderDecisionSupport(data);

    setText("diagnosis", data.diagnosis || "");
    setText("recommendation", data.recommendation || "");

    const warning = getElement("safety-warning");

    if (warning) {
        warning.textContent = data.safety_warning || "";
        warning.hidden = !data.safety_warning;
    }

    if (data.safety_warning) {
        showMessage(data.safety_warning, true);
    } else {
        clearMessage();
    }
}

// ---------- Send analysis request ----------

if (form) {
    form.addEventListener("submit", async event => {
        event.preventDefault();
        clearMessage();

        if (analyseButton) {
            analyseButton.disabled = true;
            analyseButton.textContent = "Analysing...";
        }

        try {
            const payload = buildPayload();

            const response = await fetch("/api/analyze", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Accept": "application/json"
                },
                body: JSON.stringify(payload)
            });

            let data;

            try {
                data = await response.json();
            } catch {
                throw new Error(
                    "The server did not return valid JSON. Check the Flask terminal for errors."
                );
            }

            if (!response.ok) {
                throw new Error(
                    data.error ||
                    `Analysis failed with HTTP status ${response.status}.`
                );
            }

            renderAnalysis(data);

        } catch (error) {
            console.error(
                "PotableShield analysis error:",
                error
            );

            showMessage(
                error.message ||
                "Something went wrong. Check that Flask is running and try again.",
                true
            );

        } finally {
            if (analyseButton) {
                analyseButton.disabled = false;
                analyseButton.textContent = "Analyse Scenario";
            }
        }
    });

} else {
    console.error(
        'PotableShield: Could not find the form with id="scenario".'
    );
}

/* =========================================================
   POTABLESHIELD — WATER SOURCE & DELIVERY PLANNER
   Fixed version: add, remove and generate delivery plans
   ========================================================= */

(() => {
    "use strict";

    const sourceContainer = document.getElementById("water-sources");
    const vehicleContainer = document.getElementById("delivery-vehicles");
    const addSourceButton = document.getElementById("add-source-button");
    const addVehicleButton = document.getElementById("add-vehicle-button");
    const planButton = document.getElementById("plan-deliveries-button");

    const deliveryMessage = document.getElementById("delivery-message");
    const deliveryResults = document.getElementById("delivery-results");
    const deliveryTotal = document.getElementById("delivery-total");
    const deliveryUnallocated = document.getElementById("delivery-unallocated");
    const deliveryPlanList = document.getElementById("delivery-plan-list");
    const deliveryNotes = document.getElementById("delivery-notes");

    function showDeliveryMessage(text, isError = false) {
        if (!deliveryMessage) {
            console.error("PotableShield delivery planner:", text);
            return;
        }

        deliveryMessage.textContent = text;
        deliveryMessage.hidden = false;
        deliveryMessage.classList.toggle("error-message", isError);
        deliveryMessage.classList.toggle("success-message", !isError);
    }

    // Report missing HTML IDs instead of silently disabling the planner.
    const requiredElements = {
        "water-sources": sourceContainer,
        "delivery-vehicles": vehicleContainer,
        "add-source-button": addSourceButton,
        "add-vehicle-button": addVehicleButton,
        "plan-deliveries-button": planButton,
        "delivery-message": deliveryMessage,
        "delivery-results": deliveryResults,
        "delivery-plan-list": deliveryPlanList,
        "delivery-notes": deliveryNotes
    };

    const missingElements = Object.entries(requiredElements)
        .filter(([, element]) => !element)
        .map(([id]) => `#${id}`);

    if (missingElements.length > 0) {
        console.error(
            "PotableShield: Missing delivery planner HTML elements:",
            missingElements.join(", ")
        );

        showDeliveryMessage(
            "Planner setup error. Missing HTML elements: " +
            missingElements.join(", "),
            true
        );
        return;
    }

    const formatLitres = value =>
        `${Number(value || 0).toLocaleString("en-IN", {
            maximumFractionDigits: 2
        })} L`;

    const formatMinutes = value =>
        `${Number(value || 0).toLocaleString("en-IN", {
            maximumFractionDigits: 1
        })} minutes`;

    function createInput(labelText, name, type, value, min = "0") {
        const label = document.createElement("label");
        label.appendChild(document.createTextNode(labelText));

        const input = document.createElement("input");
        input.type = type;
        input.name = name;
        input.required = true;

        if (type === "number") {
            input.min = min;
            input.step = "any";
            input.value = value;
        } else {
            input.placeholder = value;
            input.value = "";
        }

        label.appendChild(input);
        return label;
    }

    function createCheckbox(labelText, name, checked) {
        const label = document.createElement("label");
        label.className = "check";

        const input = document.createElement("input");
        input.type = "checkbox";
        input.name = name;
        input.checked = checked;

        const span = document.createElement("span");
        span.textContent = labelText;

        label.append(input, span);
        return label;
    }

    function createRemoveButton() {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "secondary-button remove-row-button";
        button.textContent = "Remove";
        return button;
    }

    function addSourceRow() {
        const row = document.createElement("div");
        row.className = "source-row";

        row.append(
            createInput(
                "Source name",
                "source_name",
                "text",
                "e.g. Municipal tanker depot"
            ),
            createInput(
                "Available potable water (L)",
                "source_available",
                "number",
                "10000"
            ),
            createCheckbox(
                "Potable water confirmed",
                "source_potable",
                true
            ),
            createRemoveButton()
        );

        sourceContainer.appendChild(row);
    }

    function addVehicleRow() {
        const row = document.createElement("div");
        row.className = "vehicle-row";

        row.append(
            createInput(
                "Vehicle name",
                "vehicle_name",
                "text",
                "e.g. Tanker 2"
            ),
            createInput(
                "Capacity (L)",
                "vehicle_capacity",
                "number",
                "5000",
                "0.01"
            ),
            createInput(
                "Estimated arrival time (minutes)",
                "vehicle_eta",
                "number",
                "30"
            ),
            createCheckbox(
                "Vehicle available",
                "vehicle_available",
                true
            ),
            createRemoveButton()
        );

        vehicleContainer.appendChild(row);
    }

    // One delegated handler supports both existing and newly added rows.
    function handleRemove(event, container, rowSelector, minimumMessage) {
        const button = event.target.closest(".remove-row-button");

        if (!button || !container.contains(button)) {
            return;
        }

        event.preventDefault();

        const row = button.closest(rowSelector);

        if (!row) {
            showDeliveryMessage(
                "Could not identify the row to remove.",
                true
            );
            return;
        }

        if (container.querySelectorAll(rowSelector).length <= 1) {
            showDeliveryMessage(minimumMessage, true);
            return;
        }

        row.remove();
        showDeliveryMessage("Row removed successfully.");
    }

    sourceContainer.addEventListener("click", event => {
        handleRemove(
            event,
            sourceContainer,
            ".source-row",
            "Keep at least one water source."
        );
    });

    vehicleContainer.addEventListener("click", event => {
        handleRemove(
            event,
            vehicleContainer,
            ".vehicle-row",
            "Keep at least one delivery vehicle."
        );
    });

    function readRows(container, type) {
        const isSource = type === "source";
        const selector = isSource ? ".source-row" : ".vehicle-row";
        const rows = Array.from(container.querySelectorAll(selector));

        if (rows.length === 0) {
            throw new Error(
                `Add at least one ${isSource ? "water source" : "delivery vehicle"}.`
            );
        }

        return rows.map((row, index) => {
            const input = name =>
                row.querySelector(`[name="${name}"]`);

            const nameField = input(
                isSource ? "source_name" : "vehicle_name"
            );

            const name = nameField?.value.trim();

            if (!name) {
                throw new Error(
                    `Enter a name for ${isSource ? "water source" : "vehicle"} ${index + 1}.`
                );
            }

            if (isSource) {
                const availableField = input("source_available");
                const available = Number(availableField?.value);

                if (
                    !availableField ||
                    availableField.value.trim() === "" ||
                    !Number.isFinite(available) ||
                    available < 0
                ) {
                    throw new Error(
                        `Enter a valid water quantity for "${name}".`
                    );
                }

                return {
                    source_id: `source-${index + 1}`,
                    name,
                    available_l: available,
                    potable_confirmed:
                        input("source_potable")?.checked === true
                };
            }

            const capacityField = input("vehicle_capacity");
            const etaField = input("vehicle_eta");
            const capacity = Number(capacityField?.value);
            const eta = Number(etaField?.value);

            if (
                !capacityField ||
                capacityField.value.trim() === "" ||
                !Number.isFinite(capacity) ||
                capacity <= 0
            ) {
                throw new Error(
                    `Enter a vehicle capacity greater than zero for "${name}".`
                );
            }

            if (
                !etaField ||
                etaField.value.trim() === "" ||
                !Number.isFinite(eta) ||
                eta < 0
            ) {
                throw new Error(
                    `Enter a valid arrival time for "${name}".`
                );
            }

            return {
                vehicle_id: `vehicle-${index + 1}`,
                name,
                capacity_l: capacity,
                eta_minutes: eta,
                available: input("vehicle_available")?.checked === true
            };
        });
    }

    function addText(parent, tag, text) {
        const element = document.createElement(tag);
        element.textContent = String(text ?? "");
        parent.appendChild(element);
        return element;
    }

    function renderDeliveryPlan(data) {
        deliveryPlanList.replaceChildren();
        deliveryNotes.replaceChildren();

        if (deliveryTotal) {
            deliveryTotal.textContent = formatLitres(data.total_planned_l);
        }

        if (deliveryUnallocated) {
            deliveryUnallocated.textContent =
                formatLitres(data.unallocated_shortage_l);
        }

        const deliveries = Array.isArray(data.delivery_plan)
            ? data.delivery_plan
            : [];

        if (deliveries.length === 0) {
            addText(
                deliveryPlanList,
                "p",
                "No deliveries could be proposed. Check the shortage, confirmed water sources, and available vehicles."
            );
        }

        deliveries.forEach((delivery, index) => {
            const card = document.createElement("article");
            card.className = "delivery-plan-card panel";

            addText(
                card,
                "h4",
                `${index + 1}. ${delivery.facility || "Facility"}`
            );

            const list = document.createElement("ul");

            const entries = [
                ["Priority", delivery.priority_level],
                ["Water source", delivery.source],
                ["Vehicle", delivery.vehicle],
                ["Quantity", formatLitres(delivery.quantity_l)],
                ["Estimated arrival", formatMinutes(delivery.eta_minutes)],
                ["Status", delivery.status]
            ];

            entries.forEach(([label, value]) => {
                if (value !== undefined && value !== null && value !== "") {
                    addText(list, "li", `${label}: ${value}`);
                }
            });

            card.appendChild(list);
            deliveryPlanList.appendChild(card);
        });

        (Array.isArray(data.source_notes) ? data.source_notes : [])
            .forEach(note => addText(deliveryNotes, "li", note));

        deliveryResults.hidden = false;
        deliveryResults.scrollIntoView({
            behavior: "smooth",
            block: "start"
        });
    }

    addSourceButton.addEventListener("click", event => {
        event.preventDefault();
        addSourceRow();
        showDeliveryMessage("New water source added.");
    });

    addVehicleButton.addEventListener("click", event => {
        event.preventDefault();
        addVehicleRow();
        showDeliveryMessage("New delivery vehicle added.");
    });

    planButton.addEventListener("click", async event => {
        event.preventDefault();

        // latestAnalysis is declared in the main section of app.js.
        if (
            !latestAnalysis ||
            !Array.isArray(latestAnalysis.facility_results)
        ) {
            showDeliveryMessage(
                "First click Analyse Scenario and wait for the analysis results. Then generate the delivery plan.",
                true
            );
            return;
        }

        let sources;
        let vehicles;

        try {
            sources = readRows(sourceContainer, "source");
            vehicles = readRows(vehicleContainer, "vehicle");
        } catch (error) {
            showDeliveryMessage(error.message, true);
            return;
        }

        if (!sources.some(source => source.potable_confirmed)) {
            showDeliveryMessage(
                "Confirm at least one potable-water source before generating the plan.",
                true
            );
            return;
        }

        if (!vehicles.some(vehicle => vehicle.available)) {
            showDeliveryMessage(
                "Mark at least one vehicle as available.",
                true
            );
            return;
        }

        planButton.disabled = true;
        planButton.textContent = "Generating delivery plan...";

        if (deliveryResults) {
            deliveryResults.hidden = true;
        }

        showDeliveryMessage("Generating proposed deliveries...");

        try {
            const response = await fetch("/api/plan-deliveries", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Accept": "application/json"
                },
                body: JSON.stringify({
                    analysis: latestAnalysis,
                    sources,
                    vehicles
                })
            });

            let data;

            try {
                data = await response.json();
            } catch {
                throw new Error(
                    "The server returned an invalid response. Check the Flask terminal."
                );
            }

            if (!response.ok) {
                throw new Error(
                    data.error ||
                    `Delivery planning failed (HTTP ${response.status}).`
                );
            }

            renderDeliveryPlan(data);

            showDeliveryMessage(
                "Delivery plan generated. Verify all details and obtain human approval before dispatch."
            );
        } catch (error) {
            console.error("PotableShield delivery planner error:", error);

            showDeliveryMessage(
                error.message || "Unable to generate the delivery plan.",
                true
            );
        } finally {
            planButton.disabled = false;
            planButton.textContent = "Generate proposed delivery plan →";
        }
    });

    console.log("PotableShield delivery planner initialized.");
})();
import frappe
from frappe import _

@frappe.whitelist()
def submit_travel_request_from_mobile(**kwargs):
    """
    Mobile API to create and submit Travel Request via Workflow.
    """

    allowed_travel_type = ["Domestic", "International"]
    allowed_purpose = ["Annual Leave", "Business Trip", "Unpaid Leave"]
    allowed_funding = [
        "Full Funding",
        "Fully Sponsored",
        "Partially Sponsored",
        "Require Partial Funding"
    ]
    allowed_mode = ["Flight", "Train", "Taxi", "Rented Car"]

    travel_type = kwargs.get("travel_type") or "Domestic"
    purpose_of_travel = kwargs.get("purpose_of_travel") or "Business Trip"
    travel_funding = kwargs.get("travel_funding") or "Full Funding"
    mode_of_travel = kwargs.get("mode_of_travel") or "Flight"

    # Prepare child table data for Itinerary
    itinerary_data = []
    itinerary_list = kwargs.get("itinerary") or []

    if isinstance(itinerary_list, list):
        for row in itinerary_list:
            itinerary_data.append({
                "doctype": "Travel Itinerary",
                "travel_from": row.get("travel_from"),
                "travel_to": row.get("travel_to"),
                "mode_of_travel": row.get("mode_of_travel", mode_of_travel),
                "departure_date": row.get("departure_date")
            })

    # Create Travel Request document
    doc = frappe.get_doc({
        "doctype": "Travel Request",
        "employee": kwargs.get("employee"),
        # "passport_number": kwargs.get("passport_number"),
        "personal_id_type": kwargs.get("personal_id_type", "Iqama"),
        "personal_id_number": kwargs.get("personal_id_number"),
        "travel_type": travel_type,
        "purpose_of_travel": purpose_of_travel,
        "travel_funding": travel_funding,
        "description": kwargs.get("description"),
        "itinerary": itinerary_data
    })

    # Insert draft
    doc.insert(ignore_permissions=True)

    # Submit via Workflow
    frappe.model.workflow.apply_workflow(doc, "Submit")

    doc.reload()

    return {
        "message": "Travel Request Submitted",
        "name": doc.name,
        "workflow_state": doc.workflow_state
    }

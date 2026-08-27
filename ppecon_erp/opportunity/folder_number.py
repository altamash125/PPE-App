import frappe

@frappe.whitelist()
def get_prospect_company_by_folder(folder_number):
    if not folder_number:
        return None

    opportunity = frappe.db.get_value(
        "Opportunity",
        {"custom_folder_no": folder_number},
        ["name", "opportunity_from", "party_name"],
        order_by="creation desc",
        as_dict=True,
    )
    if not opportunity:
        return None

    if opportunity.opportunity_from == "Lead":
        return frappe.db.get_value("Lead", opportunity.party_name, "company_name")
    elif opportunity.opportunity_from == "Customer":
        return frappe.db.get_value("Customer", opportunity.party_name, "customer_name")

    return None
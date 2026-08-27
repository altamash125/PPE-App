import frappe


@frappe.whitelist()
def get_prospect_company_by_folder(folder_number):
    if not folder_number:
        return None

    opportunity = frappe.db.get_value(
        "Opportunity",
        {"custom_folder_no": folder_number},
        ["name", "opportunity_from", "party_name", "industry", "transaction_date",
         "contact_person", "contact_email", "contact_mobile"],
        order_by="creation desc",
        as_dict=True,
    )
    if not opportunity:
        return None

    prospect_company = None
    if opportunity.opportunity_from == "Lead":
        prospect_company = frappe.db.get_value("Lead", opportunity.party_name, "company_name")
    elif opportunity.opportunity_from == "Customer":
        prospect_company = frappe.db.get_value("Customer", opportunity.party_name, "customer_name")

    return {
        "prospect_company": prospect_company,
        "industry": opportunity.industry,
        "transaction_date": opportunity.transaction_date,
        "contact_person": opportunity.contact_person,
        "contact_email": opportunity.contact_email,
        "contact_mobile": opportunity.contact_mobile,
    }
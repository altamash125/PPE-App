import frappe
from frappe import _
from frappe.utils import flt

@frappe.whitelist()
def update_items(mr_name, items):
    if not mr_name or not items:
        return

    if isinstance(items, str):
        items = frappe.parse_json(items)

    for updated_item in items:
        row_id = updated_item.get("name")
        
        if row_id:
            # Use db.set_value to bypass validation conflicts during submission
            frappe.db.set_value("Material Request Item", row_id, {
                "qty": flt(updated_item.get("qty")),
                "uom": updated_item.get("uom"),
                "schedule_date": updated_item.get("schedule_date")
            }, update_modified=True)

    # Finalize the database changes
    frappe.db.commit()
    
    # Clear cache so the user sees the new data immediately
    frappe.clear_document_cache("Material Request", mr_name)
    
    frappe.msgprint(_("Items updated successfully for {0}").format(mr_name))
    return True

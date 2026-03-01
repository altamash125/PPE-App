import frappe
from frappe import _

@frappe.whitelist()
def submit_leave_from_mobile(**kwargs):

    allowed_values = [
        "Yes (On Company)",
        "Yes (On Employee)",
        "No"
    ]

    ticket = kwargs.get("ticket")
    if ticket not in allowed_values:
        ticket = "No"

    employee = kwargs.get("employee")

    leave_approver = frappe.db.get_value(
        "Employee",
        employee,
        "leave_approver"
    )

    if not leave_approver:
        frappe.throw(_("Leave Approver not set for Employee"))

    doc = frappe.get_doc({
        "doctype": "Leave Application",
        "employee": employee,
        "leave_type": kwargs.get("leave_type"),
        "from_date": kwargs.get("from_date"),
        "to_date": kwargs.get("to_date"),
        "incharge_replacement": kwargs.get("incharge_replacement"),
        "ticket": ticket,
        "description": kwargs.get("description"),
        "leave_approver": leave_approver
    })

    # 1️⃣ Draft save (UI Save)
    doc.insert(ignore_permissions=True)

    # 2️⃣ Workflow action ONLY (UI Apply / Submit button)
    frappe.model.workflow.apply_workflow(
        doc,
        "Submit"   # EXACT workflow action name
    )

    doc.reload()

    return {
        "message": "Leave Applied Successfully",
        "name": doc.name,
        "docstatus": doc.docstatus,          # 0
        "status": doc.status,                # Pending Approval
        "workflow_state": doc.workflow_state,
        "leave_approver": doc.leave_approver
    }


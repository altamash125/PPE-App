import frappe
from frappe import _
from frappe.utils import flt, nowdate

@frappe.whitelist()
def submit_employee_advance_from_mobile(**kwargs):

    frappe.set_user("Administrator")  # important for API

    # ---------------- VALIDATION ----------------
    required = ["employee", "advance_amount", "purpose"]
    for f in required:
        if not kwargs.get(f):
            frappe.throw(_(f"{f} is required"))

    if not frappe.db.exists("Employee", kwargs["employee"]):
        frappe.throw(_("Employee not found"))

    advance_amount = flt(kwargs["advance_amount"])
    if advance_amount <= 0:
        frappe.throw(_("Advance amount must be greater than 0"))

    # ---------------- CREATE DOCUMENT ----------------
    doc = frappe.get_doc({
        "doctype": "Employee Advance",
        "employee": kwargs["employee"],
        "posting_date": kwargs.get("posting_date", nowdate()),
        "company": "Pioneer Projects Executer Company",
        "purpose": kwargs["purpose"],
        "advance_amount": advance_amount,
        "advance_account": kwargs.get(
            "advance_account",
            "1610 - Employee Advances - PPE"
        ),
        "mode_of_payment": kwargs.get("mode_of_payment"),
        "repay_unclaimed_amount_from_salary": int(
            kwargs.get("repay_unclaimed_amount_from_salary", 0)
        ),
        "exchange_rate": 1,   #  FIX (MANDATORY)
        "currency": "SAR"
    })

    doc.insert(ignore_permissions=True)

    # ---------------- SUBMIT ----------------
    try:
        if frappe.db.exists(
            "Workflow",
            {"document_type": "Employee Advance", "is_active": 1}
        ):
            frappe.model.workflow.apply_workflow(doc, "Submit")
        else:
            doc.submit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Employee Advance Submit Error")
        frappe.throw(_("Submit failed, check Error Log"))

    frappe.db.commit()  #  VERY IMPORTANT

    return {
        "success": True,
        "name": doc.name,
        "docstatus": doc.docstatus,
        "workflow_state": doc.workflow_state,
        "employee": doc.employee,
        "amount": doc.advance_amount
    }


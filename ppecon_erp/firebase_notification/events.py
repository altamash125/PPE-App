# =========================================================================
#  ppecon_erp/firebase_notification/events.py  (v2 — improved)
#  Push notifications on final submit (docstatus = 1)
#  Leave Application · Employee Advance · Travel Request · Attendance Request
#
#  hooks.py:
#  doc_events = {
#      "Leave Application":  {"on_submit": "ppecon_erp.firebase_notification.events.leave_application_submitted"},
#      "Employee Advance":   {"on_submit": "ppecon_erp.firebase_notification.events.employee_advance_submitted"},
#      "Travel Request":     {"on_submit": "ppecon_erp.firebase_notification.events.travel_request_submitted"},
#      "Attendance Request": {"on_submit": "ppecon_erp.firebase_notification.events.attendance_request_submitted"},
#  }
# =========================================================================
import frappe
from frappe.utils import formatdate, fmt_money
from ppecon_erp.firebase_notification.firebase import send_notification


# ---------------------------------------------------------------
#  SHARED HELPERS
# ---------------------------------------------------------------
def _user_of_employee(employee):
    if not employee:
        return None
    return frappe.db.get_value("Employee", employee, "user_id")


def _is_rejected(doc):
    """True if the doc's status/workflow_state contains 'reject'."""
    status = (doc.get("status") or doc.get("workflow_state") or "").lower()
    return "reject" in status


def _date_range(doc):
    """'10-08-2026' or '10-08-2026 to 12-08-2026'."""
    dates = formatdate(doc.from_date)
    if str(doc.from_date) != str(doc.to_date):
        dates += f" to {formatdate(doc.to_date)}"
    return dates


def _notify(user, title, message, ref_doctype=None, ref_name=None):
    """Send safely — a notification failure must NEVER block the submit."""
    if not user:
        return
    try:
        data = {}
        if ref_doctype and ref_name:
            data = {"doctype": ref_doctype, "name": ref_name}
        send_notification(user=user, title=title, message=message, data=data)
    except Exception:
        # keyword args: long traceback goes in message, short title stays <140
        frappe.log_error(title=f"FCM notify: {ref_doctype}",
                         message=frappe.get_traceback())


# ---------------------------------------------------------------
#  1. LEAVE APPLICATION
# ---------------------------------------------------------------
def leave_application_submitted(doc, method=None):
    user = _user_of_employee(doc.employee)
    if not user:
        return

    dates = _date_range(doc)

    if doc.status == "Approved":
        title = "Leave Approved ✅"
        message = f"Your {doc.leave_type} application ({dates}) has been approved."
    elif doc.status == "Rejected":
        title = "Leave Rejected ❌"
        message = f"Your {doc.leave_type} application ({dates}) has been rejected."
    else:
        return  # submitted with some other status — send nothing

    _notify(user, title, message, "Leave Application", doc.name)


# ---------------------------------------------------------------
#  2. EMPLOYEE ADVANCE
#     advance_account decides wording:
#     1611 - Employees Petty cash - PPE  -> "Petty Cash"
#     1610 - Employee Advances - PPE     -> "Employee Advance"
# ---------------------------------------------------------------
def employee_advance_submitted(doc, method=None):
    user = _user_of_employee(doc.employee)
    if not user:
        return

    account = (doc.get("advance_account") or "").lower()
    advance_type = "Petty Cash" if "petty" in account else "Employee Advance"

    amount = fmt_money(doc.advance_amount, currency=doc.get("currency") or "SAR")

    if _is_rejected(doc):
        title = f"{advance_type} Rejected ❌"
        message = f"Your {advance_type.lower()} request of {amount} has been rejected."
    else:
        title = f"{advance_type} Approved ✅"
        message = f"Your {advance_type.lower()} request of {amount} has been approved."

    _notify(user, title, message, "Employee Advance", doc.name)


# ---------------------------------------------------------------
#  3. TRAVEL REQUEST
# ---------------------------------------------------------------
def travel_request_submitted(doc, method=None):
    user = _user_of_employee(doc.employee)
    if not user:
        return

    if _is_rejected(doc):
        title = "Travel Request Rejected ❌"
        message = "Your Travel Request has been rejected."
    else:
        title = "Travel Request Approved ✅"
        message = "Your Travel Request has been approved."

    _notify(user, title, message, "Travel Request", doc.name)


# ---------------------------------------------------------------
#  4. ATTENDANCE REQUEST
# ---------------------------------------------------------------
def attendance_request_submitted(doc, method=None):
    user = _user_of_employee(doc.employee)
    if not user:
        return

    dates = _date_range(doc)
    reason = doc.get("reason") or ""
    reason_part = f" ({reason})" if reason else ""

    if _is_rejected(doc):
        title = "Attendance Request Rejected ❌"
        message = f"Your Attendance Request for {dates}{reason_part} has been rejected."
    else:
        title = "Attendance Request Approved ✅"
        message = f"Your Attendance Request for {dates}{reason_part} has been approved."

    _notify(user, title, message, "Attendance Request", doc.name)
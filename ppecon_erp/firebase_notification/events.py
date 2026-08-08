# =========================================================================
#  ppecon_erp/firebase_notification/events.py
#  Push notifications on final submit (docstatus = 1)
#  Leave Application · Employee Advance · Travel Request · Attendance Request
# =========================================================================
import frappe
from frappe.utils import formatdate
from ppecon_erp.firebase_notification.firebase import send_notification


def _user_of_employee(employee):
    if not employee:
        return None
    return frappe.db.get_value("Employee", employee, "user_id")


def _notify(user, title, message, ref_doctype=None, ref_name=None):
    if not user:
        return
    try:
        data = {}
        if ref_doctype and ref_name:
            data = {"doctype": ref_doctype, "name": ref_name}
        send_notification(user=user, title=title, message=message, data=data)
    except Exception:
        frappe.log_error(frappe.get_traceback(), f"FCM notify: {ref_doctype} {ref_name}")


# ---------------------------------------------------------------
#  1. LEAVE APPLICATION  (on_submit)
# ---------------------------------------------------------------
def leave_application_submitted(doc, method=None):
    user = _user_of_employee(doc.employee)
    if not user:
        return

    dates = formatdate(doc.from_date)
    if str(doc.from_date) != str(doc.to_date):
        dates += f" to {formatdate(doc.to_date)}"

    if doc.status == "Approved":
        title = "Leave Approved ✅"
        message = f"Your {doc.leave_type} application ({dates}) has been approved."
    elif doc.status == "Rejected":
        title = "Leave Rejected ❌"
        message = f"Your {doc.leave_type} application ({dates}) has been rejected."
    else:
        return  # submit hua lekin status kuch aur — kuch mat bhejo

    _notify(user, title, message, "Leave Application", doc.name)


# ---------------------------------------------------------------
#  2. EMPLOYEE ADVANCE  (on_submit)
#     advance_account se type decide hota hai:
#     1611 - Employees Petty cash - PPE  -> "Petty Cash"
#     1610 - Employee Advances - PPE     -> "Employee Advance"
# ---------------------------------------------------------------
# ---------------------------------------------------------------
#  2. EMPLOYEE ADVANCE  (on_submit)
# ---------------------------------------------------------------
def employee_advance_submitted(doc, method=None):
    user = _user_of_employee(doc.employee)
    if not user:
        return

    account = doc.get("advance_account") or ""
    advance_type = "Petty Cash" if "petty" in account.lower() else "Employee Advance"

    amount = frappe.utils.fmt_money(doc.advance_amount, currency=doc.get("currency") or "SAR")

    status = (doc.get("status") or doc.get("workflow_state") or "").lower()
    if "reject" in status:
        title = f"{advance_type} Rejected ❌"
        message = f"Your {advance_type.lower()} request of {amount} has been rejected."
    else:
        title = f"{advance_type} Approved ✅"
        message = f"Your {advance_type.lower()} request of {amount} has been approved."

    _notify(user, title, message, "Employee Advance", doc.name)


# ---------------------------------------------------------------
#  3. TRAVEL REQUEST  (on_submit)
# ---------------------------------------------------------------
def travel_request_submitted(doc, method=None):
    user = _user_of_employee(doc.employee)
    if not user:
        return

    status = (doc.get("status") or doc.get("workflow_state") or "").lower()
    if "reject" in status:
        title = "Travel Request Rejected ❌"
        message = "Your Travel Request has been rejected."
    else:
        title = "Travel Request Approved ✅"
        message = "Your Travel Request has been approved."

    _notify(user, title, message, "Travel Request", doc.name)


# ---------------------------------------------------------------
#  4. ATTENDANCE REQUEST  (on_submit)
# ---------------------------------------------------------------
def attendance_request_submitted(doc, method=None):
    user = _user_of_employee(doc.employee)
    if not user:
        return

    dates = formatdate(doc.from_date)
    if str(doc.from_date) != str(doc.to_date):
        dates += f" to {formatdate(doc.to_date)}"

    reason = doc.get("reason") or ""
    reason_part = f" ({reason})" if reason else ""

    status = (doc.get("status") or doc.get("workflow_state") or "").lower()
    if "reject" in status:
        title = "Attendance Request Rejected ❌"
        message = f"Your Attendance Request for {dates}{reason_part} has been rejected."
    else:
        title = "Attendance Request Approved ✅"
        message = f"Your Attendance Request for {dates}{reason_part} has been approved."

    _notify(user, title, message, "Attendance Request", doc.name)
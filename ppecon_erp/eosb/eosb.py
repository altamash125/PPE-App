import frappe
from frappe import _
from frappe.utils import getdate, date_diff, today, flt

@frappe.whitelist()
def get_my_eosb():
    user = frappe.session.user

    employee = frappe.db.get_value(
        "Employee",
        {"user_id": user},
        ["name", "date_of_joining", "ctc", "status", "relieving_date"],
        as_dict=True
    )

    if not employee:
        frappe.throw(_("Employee record not found."), frappe.DoesNotExistError)

    doj    = employee.date_of_joining
    salary = flt(employee.ctc)
    status = employee.status

    if not doj or not salary:
        frappe.throw(_("Date of joining or CTC not set."))

    is_final = False

    if status == "Left":
        if not employee.relieving_date:
            return {"success": False, "error": "relieving_date_missing"}
        end_date = getdate(employee.relieving_date)
        is_final = True
    else:
        end_date = getdate(today())

    service_days = date_diff(end_date, getdate(doj))

    if service_days <= 0:
        return {"success": False, "error": "invalid_dates"}

    years = service_days / 365

    if years <= 5:
        eosb = years * (salary / 2)
    else:
        eosb = (5 * (salary / 2)) + ((years - 5) * salary)

    eosb = round(eosb, 2)

    return {
        "success":    True,
        "eosb_amount": eosb,
        "is_final":   is_final,
    }
import frappe
from frappe.utils import getdate, flt

no_cache = 1


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/attendance-dashboard"
        raise frappe.Redirect
    context.no_cache = 1
    return context


def has_field(doctype, field):
    try:
        return frappe.get_meta(doctype).has_field(field)
    except Exception:
        return False


def overtime_field():
    for f in ("custom_overtime_", "overtime", "is_overtime"):
        if has_field("Attendance", f):
            return f
    return None


def job_number_field():
    for f in ("employee_number", "custom_job_number", "job_number"):
        if has_field("Employee", f):
            return f
    return None


@frappe.whitelist()
def get_attendance_data(from_date, to_date, department=None, employee=None):
    from_date = getdate(from_date)
    to_date = getdate(to_date)

    filters = {"attendance_date": ["between", [from_date, to_date]], "docstatus": ["<", 2]}
    if department:
        filters["department"] = department
    if employee:
        filters["employee"] = employee

    ot_field = overtime_field()
    jn_field = job_number_field()

    fields = [
        "employee", "employee_name", "attendance_date", "status",
        "shift", "in_time", "out_time", "working_hours",
        "late_entry", "early_exit", "department",
    ]
    if ot_field:
        fields.append(ot_field)

    rows = frappe.get_all(
        "Attendance", filters=filters, fields=fields,
        order_by="attendance_date asc, employee_name asc"
    )

    job_map = {}
    if jn_field:
        emp_names = list({r.employee for r in rows})
        if emp_names:
            for e in frappe.get_all("Employee", filters={"name": ["in", emp_names]},
                                    fields=["name", jn_field]):
                job_map[e.name] = e.get(jn_field)

    data = []
    summary = {"present": 0, "absent": 0, "on_leave": 0, "half_day": 0,
               "late_entry": 0, "early_exit": 0, "total_hours": 0.0}

    for r in rows:
        d = getdate(r.attendance_date)
        row = {
            "job_number": job_map.get(r.employee) or r.employee,
            "employee": r.employee,
            "employee_name": r.employee_name,
            "date": str(d),
            "day": d.strftime("%A"),
            "status": r.status,
            "shift": r.shift,
            "department": r.department,
            "in_time": r.in_time.strftime("%H:%M") if r.in_time else "-",
            "out_time": r.out_time.strftime("%H:%M") if r.out_time else "-",
            "working_hours": flt(r.working_hours, 2),
            "late_entry": bool(r.late_entry),
            "early_exit": bool(r.early_exit),
            "overtime": bool(r.get(ot_field)) if ot_field else False,
        }
        data.append(row)

        status_key = (r.status or "").lower().replace(" ", "_").replace("-", "_")
        if status_key in summary:
            summary[status_key] += 1
        if r.late_entry:
            summary["late_entry"] += 1
        if r.early_exit:
            summary["early_exit"] += 1
        summary["total_hours"] += flt(r.working_hours)

    summary["total_records"] = len(data)
    summary["total_hours"] = round(summary["total_hours"], 1)

    return {"rows": data, "summary": summary}


@frappe.whitelist()
def get_departments():
    return frappe.get_all("Department", filters={"disabled": 0}, pluck="name", order_by="name")
import frappe
from frappe.utils import getdate, flt, add_days

no_cache = 1

OVERTIME_THRESHOLD_HOURS = 9


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


def late_entry_field():
    for f in ("late_entry", "late_enty"):
        if has_field("Attendance", f):
            return f
    return None


def early_exit_field():
    for f in ("early_exit", "early_exti"):
        if has_field("Attendance", f):
            return f
    return None


def is_overtime_enabled(value):
    """Handles Check (1/0), Select (Yes/No), or Data ('Yes') field types."""
    if value in (1, True, "1"):
        return True
    if isinstance(value, str) and value.strip().lower() in ("yes", "true"):
        return True
    return False


@frappe.whitelist()
def get_attendance_data(from_date, to_date, department=None, employee=None):
    try:
        from_date = getdate(from_date)
        to_date = getdate(to_date)

        filters = {"attendance_date": ["between", [from_date, to_date]], "docstatus": ["<", 2]}
        if department:
            filters["department"] = department
        if employee:
            # allow searching by name OR id
            emp_ids = frappe.get_all(
                "Employee",
                filters={"employee_name": ["like", "%%%s%%" % employee]},
                pluck="name",
            )
            emp_ids.append(employee)
            filters["employee"] = ["in", list(set(emp_ids))]

        ot_field = overtime_field()
        late_field = late_entry_field()
        early_field = early_exit_field()

        fields = [
            "employee", "employee_name", "attendance_date", "status",
            "shift", "in_time", "out_time", "working_hours", "department",
        ]
        if late_field:
            fields.append(late_field)
        if early_field:
            fields.append(early_field)
        if ot_field:
            fields.append(ot_field)

        rows = frappe.get_all(
            "Attendance", filters=filters, fields=fields,
            order_by="attendance_date desc, employee_name asc"
        )

        data = []
        summary = {"present": 0, "absent": 0, "on_leave": 0, "half_day": 0,
                   "late_entry": 0, "early_exit": 0, "total_hours": 0.0,
                   "total_overtime_hours": 0.0, "overtime_days": 0}

        for r in rows:
            d = getdate(r.attendance_date)
            is_late = bool(r.get(late_field)) if late_field else False
            is_early = bool(r.get(early_field)) if early_field else False

            # overtime: only counted when the flag is enabled on this record,
            # and only the portion of working_hours beyond the threshold
            ot_enabled = bool(ot_field) and is_overtime_enabled(r.get(ot_field))
            ot_hours = round(max(flt(r.working_hours) - OVERTIME_THRESHOLD_HOURS, 0), 2) if ot_enabled else 0

            row = {
                "job_number": r.employee,          # full ERP Employee ID, e.g. HR-EMP-00089
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
                "late_entry": is_late,
                "early_exit": is_early,
                "overtime_enabled": ot_enabled,
                "overtime_hours": ot_hours,
            }
            data.append(row)

            status_key = (r.status or "").lower().replace(" ", "_").replace("-", "_")
            if status_key in summary:
                summary[status_key] += 1
            if is_late:
                summary["late_entry"] += 1
            if is_early:
                summary["early_exit"] += 1
            if ot_hours > 0:
                summary["overtime_days"] += 1
                summary["total_overtime_hours"] += ot_hours
            summary["total_hours"] += flt(r.working_hours)

        summary["total_records"] = len(data)
        summary["total_hours"] = round(summary["total_hours"], 1)
        summary["total_overtime_hours"] = round(summary["total_overtime_hours"], 1)
        marked = summary["present"] + summary["absent"] + summary["on_leave"] + summary["half_day"]
        summary["attendance_pct"] = round(
            (summary["present"] / marked) * 100, 1
        ) if marked else 0

        return {"rows": data, "summary": summary}

    except Exception:
        frappe.log_error(frappe.get_traceback(), "Attendance dashboard fetch")
        return {"rows": [], "summary": {}, "error": frappe.get_traceback().splitlines()[-1]}


@frappe.whitelist()
def get_departments():
    return frappe.get_all("Department", filters={"disabled": 0}, pluck="name", order_by="name")


@frappe.whitelist()
def get_latest_range():
    """Used by the frontend to default to a range that actually has data."""
    latest = frappe.db.get_value("Attendance", filters={}, fieldname="attendance_date",
                                 order_by="attendance_date desc")
    if not latest:
        return {"from_date": None, "to_date": None}
    latest = getdate(latest)
    return {"from_date": str(add_days(latest, -8)), "to_date": str(latest)}
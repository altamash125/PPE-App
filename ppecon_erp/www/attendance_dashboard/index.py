import frappe
from frappe.utils import getdate, flt, add_days, time_diff_in_seconds

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


def checkin_site_field():
    """Field on Employee Checkin that stores the site / location name."""
    for f in ("custom_site_name", "custom_location", "location"):
        if has_field("Employee Checkin", f):
            return f
    return None


def is_overtime_enabled(value):
    if value in (1, True, "1"):
        return True
    if isinstance(value, str) and value.strip().lower() in ("yes", "true"):
        return True
    return False


def is_truthy(value):
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

        ot_field = overtime_field()
        late_field = late_entry_field()
        early_field = early_exit_field()
        site_field = checkin_site_field()

        # ---- build extra Attendance columns dynamically ----
        extra_cols = []
        if late_field:
            extra_cols.append("a.`%s` AS late_entry_raw" % late_field)
        if early_field:
            extra_cols.append("a.`%s` AS early_exit_raw" % early_field)
        if ot_field:
            extra_cols.append("a.`%s` AS ot_raw" % ot_field)
        extra_select = (", " + ", ".join(extra_cols)) if extra_cols else ""

        # ---- checkin_summary CTE: first IN / last OUT time + site, per employee/day ----
        # NOTE: check_in_time / check_out_time are kept as real datetimes here
        # so we can compute ACTUAL hours worked (matches the "Attendance Detail
        # with Site" report), separate from Attendance.working_hours.
        if site_field:
            checkin_cte = """
                WITH checkin_summary AS (
                    SELECT
                        ec.employee,
                        DATE(ec.time) AS attendance_date,
                        MIN(CASE WHEN ec.log_type = 'IN' THEN ec.time END) AS check_in_time,
                        MIN(CASE WHEN ec.log_type = 'IN' THEN ec.`%s` END) AS check_in_from,
                        MAX(CASE WHEN ec.log_type = 'OUT' THEN ec.time END) AS check_out_time,
                        MAX(CASE WHEN ec.log_type = 'OUT' THEN ec.`%s` END) AS check_out_from
                    FROM `tabEmployee Checkin` ec
                    WHERE ec.docstatus < 2
                    GROUP BY ec.employee, DATE(ec.time)
                )
            """ % (site_field, site_field)
        else:
            checkin_cte = """
                WITH checkin_summary AS (
                    SELECT
                        ec.employee,
                        DATE(ec.time) AS attendance_date,
                        MIN(CASE WHEN ec.log_type = 'IN' THEN ec.time END) AS check_in_time,
                        NULL AS check_in_from,
                        MAX(CASE WHEN ec.log_type = 'OUT' THEN ec.time END) AS check_out_time,
                        NULL AS check_out_from
                    FROM `tabEmployee Checkin` ec
                    WHERE ec.docstatus < 2
                    GROUP BY ec.employee, DATE(ec.time)
                )
            """

        checkin_join = """
            LEFT JOIN checkin_summary cs
                ON cs.employee = a.employee
                AND cs.attendance_date = a.attendance_date
        """
        checkin_select = ", cs.check_in_time, cs.check_in_from, cs.check_out_time, cs.check_out_from"

        # ---- filters ----
        conditions = [
            "a.docstatus < 2",
            "a.attendance_date BETWEEN %(from_date)s AND %(to_date)s",
        ]
        params = {"from_date": from_date, "to_date": to_date}

        if department:
            conditions.append("a.department = %(department)s")
            params["department"] = department

        if employee:
            conditions.append("(a.employee_name LIKE %(employee_like)s OR a.employee = %(employee)s)")
            params["employee_like"] = "%%%s%%" % employee
            params["employee"] = employee

        where_clause = " AND ".join(conditions)

        sql = """
            {cte}
            SELECT
                a.employee, a.employee_name, a.attendance_date, a.status, a.shift,
                a.in_time, a.out_time, a.working_hours, a.department
                {extra_select}
                {checkin_select}
            FROM `tabAttendance` a
            {checkin_join}
            WHERE {where_clause}
            ORDER BY a.employee_name ASC, a.employee ASC, a.attendance_date DESC
        """.format(
            cte=checkin_cte, extra_select=extra_select, checkin_select=checkin_select,
            checkin_join=checkin_join, where_clause=where_clause,
        )

        rows = frappe.db.sql(sql, params, as_dict=True)

        data = []
        summary = {"present": 0, "absent": 0, "on_leave": 0, "half_day": 0,
                   "late_entry": 0, "early_exit": 0, "total_hours": 0.0,
                   "total_actual_hours": 0.0,
                   "total_overtime_hours": 0.0, "overtime_days": 0}

        for r in rows:
            d = getdate(r.attendance_date)
            is_late = is_truthy(r.get("late_entry_raw")) if late_field else False
            is_early = is_truthy(r.get("early_exit_raw")) if early_field else False

            # actual hours worked, computed from real check-in/check-out timestamps
            actual_seconds = 0
            if r.get("check_in_time") and r.get("check_out_time") and r.get("check_out_time") > r.get("check_in_time"):
                actual_seconds = time_diff_in_seconds(r.get("check_out_time"), r.get("check_in_time"))
            actual_hours = round(actual_seconds / 3600.0, 2)

            ot_enabled = bool(ot_field) and is_overtime_enabled(r.get("ot_raw"))
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
                "check_in_time": r.get("check_in_time").strftime("%H:%M") if r.get("check_in_time") else "-",
                "check_in_from": r.get("check_in_from") or "-",
                "check_out_time": r.get("check_out_time").strftime("%H:%M") if r.get("check_out_time") else "-",
                "check_out_from": r.get("check_out_from") or "-",
                "working_hours": flt(r.working_hours, 2),
                "actual_hours": actual_hours,
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
            summary["total_actual_hours"] += actual_hours

        summary["total_records"] = len(data)
        summary["total_hours"] = round(summary["total_hours"], 1)
        summary["total_actual_hours"] = round(summary["total_actual_hours"], 1)
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
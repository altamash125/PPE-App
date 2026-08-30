
import frappe
from frappe.utils import (
    getdate, flt, add_days, time_diff_in_seconds, nowdate, now_datetime
)

no_cache = 1

OVERTIME_THRESHOLD_HOURS = 9

STATE_KEY = {
    "Completed": "completed",
    "Incomplete": "incomplete",
    "Missing Check-in": "missing_checkin",
    "No Check-in": "no_checkin",
}


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


def completion_state(check_in, check_out):
    """Completed = both punches, Incomplete = checked in but never checked out."""
    if check_in and check_out:
        return "Completed"
    if check_in:
        return "Incomplete"
    if check_out:
        return "Missing Check-in"
    return "No Check-in"


def fmt_duration(seconds):
    seconds = int(seconds or 0)
    if seconds <= 0:
        return "-"
    return "%dh %02dm" % (seconds // 3600, (seconds % 3600) // 60)


def site_expr(site_field, log_type):
    """Site of the FIRST IN / LAST OUT (not just the alphabetically smallest one)."""
    if not site_field:
        return "NULL"
    agg = "MIN" if log_type == "IN" else "MAX"
    return (
        "SUBSTRING_INDEX(%s(CASE WHEN ec.log_type = '%s' "
        "THEN CONCAT(ec.time, '||', IFNULL(ec.`%s`, '')) END), '||', -1)"
        % (agg, log_type, site_field)
    )


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
        checkin_cte = """
            WITH checkin_summary AS (
                SELECT
                    ec.employee,
                    DATE(ec.time) AS attendance_date,
                    MIN(CASE WHEN ec.log_type = 'IN' THEN ec.time END) AS check_in_time,
                    {site_in} AS check_in_from,
                    MAX(CASE WHEN ec.log_type = 'OUT' THEN ec.time END) AS check_out_time,
                    {site_out} AS check_out_from,
                    COUNT(*) AS log_count
                FROM `tabEmployee Checkin` ec
                WHERE ec.docstatus < 2
                GROUP BY ec.employee, DATE(ec.time)
            )
        """.format(
            site_in=site_expr(site_field, "IN"),
            site_out=site_expr(site_field, "OUT"),
        )

        checkin_join = """
            LEFT JOIN checkin_summary cs
                ON cs.employee = a.employee
                AND cs.attendance_date = a.attendance_date
        """
        checkin_select = (
            ", cs.check_in_time, cs.check_in_from, cs.check_out_time, "
            "cs.check_out_from, cs.log_count"
        )

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
                   "total_overtime_hours": 0.0, "overtime_days": 0,
                   "completed": 0, "incomplete": 0,
                   "missing_checkin": 0, "no_checkin": 0}

        for r in rows:
            d = getdate(r.attendance_date)
            is_late = is_truthy(r.get("late_entry_raw")) if late_field else False
            is_early = is_truthy(r.get("early_exit_raw")) if early_field else False

            ci = r.get("check_in_time")
            co = r.get("check_out_time")

            # actual hours worked, computed from real check-in/check-out timestamps
            actual_seconds = 0
            if ci and co and co > ci:
                actual_seconds = time_diff_in_seconds(co, ci)
            actual_hours = round(actual_seconds / 3600.0, 2)

            state = completion_state(ci, co)

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
                "check_in_time": ci.strftime("%H:%M") if ci else "-",
                "check_in_from": r.get("check_in_from") or "-",
                "check_out_time": co.strftime("%H:%M") if co else "-",
                "check_out_from": r.get("check_out_from") or "-",
                "log_count": r.get("log_count") or 0,
                "completion": state,
                "working_hours": flt(r.working_hours, 2),
                "actual_hours": actual_hours,
                "late_entry": is_late,
                "early_exit": is_early,
                "overtime_enabled": ot_enabled,
                "overtime_hours": ot_hours,
            }
            data.append(row)

            status_key = (r.status or "").lower().replace(" ", "_").replace("-", "_")
            if status_key in ("present", "absent", "on_leave", "half_day"):
                summary[status_key] += 1
            summary[STATE_KEY[state]] += 1
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
def get_today_checkins(date=None, department=None, employee=None):
    """Live check-in / check-out log for one day, straight from Employee Checkin.

    Works even when Attendance for the day has not been marked yet, so HR can see
    who punched in, from which site, and who has not punched out (Incomplete).
    """
    try:
        d = getdate(date) if date else getdate(nowdate())
        site_field = checkin_site_field()

        conditions = ["ec.docstatus < 2", "DATE(ec.time) = %(d)s"]
        params = {"d": d}

        if department:
            conditions.append("emp.department = %(department)s")
            params["department"] = department

        if employee:
            conditions.append(
                "(emp.employee_name LIKE %(employee_like)s OR ec.employee = %(employee)s)"
            )
            params["employee_like"] = "%%%s%%" % employee
            params["employee"] = employee

        sql = """
            SELECT
                ec.employee,
                emp.employee_name,
                emp.department,
                emp.designation,
                MIN(CASE WHEN ec.log_type = 'IN' THEN ec.time END) AS check_in_time,
                {site_in} AS check_in_from,
                MAX(CASE WHEN ec.log_type = 'OUT' THEN ec.time END) AS check_out_time,
                {site_out} AS check_out_from,
                COUNT(*) AS log_count
            FROM `tabEmployee Checkin` ec
            LEFT JOIN `tabEmployee` emp ON emp.name = ec.employee
            WHERE {where}
            GROUP BY ec.employee, emp.employee_name, emp.department, emp.designation
            ORDER BY check_in_time ASC, emp.employee_name ASC
        """.format(
            site_in=site_expr(site_field, "IN"),
            site_out=site_expr(site_field, "OUT"),
            where=" AND ".join(conditions),
        )

        rows = frappe.db.sql(sql, params, as_dict=True)

        now = now_datetime()
        is_today = d == getdate(nowdate())

        data = []
        summary = {"total": 0, "completed": 0, "incomplete": 0,
                   "missing_checkin": 0, "sites": 0, "not_checked_in": 0}
        sites = set()

        for r in rows:
            ci = r.get("check_in_time")
            co = r.get("check_out_time")
            state = completion_state(ci, co)

            if ci and co and co > ci:
                secs = time_diff_in_seconds(co, ci)
            elif ci and not co and is_today and now > ci:
                secs = time_diff_in_seconds(now, ci)
            else:
                secs = 0

            for s in (r.get("check_in_from"), r.get("check_out_from")):
                if s:
                    sites.add(s)

            data.append({
                "job_number": r.employee,
                "employee": r.employee,
                "employee_name": r.employee_name or r.employee,
                "department": r.department or "-",
                "designation": r.designation or "-",
                "date": str(d),
                "check_in_time": ci.strftime("%H:%M") if ci else "-",
                "check_in_from": r.get("check_in_from") or "-",
                "check_out_time": co.strftime("%H:%M") if co else "-",
                "check_out_from": r.get("check_out_from") or "-",
                "log_count": r.get("log_count") or 0,
                "completion": state,
                "duration": fmt_duration(secs),
                "duration_hours": round(secs / 3600.0, 2),
                "running": bool(ci and not co and is_today),
            })

            summary[STATE_KEY[state]] = summary.get(STATE_KEY[state], 0) + 1

        summary["total"] = len(data)
        summary["sites"] = len(sites)

        total_active = frappe.db.count("Employee", {"status": "Active"})
        summary["not_checked_in"] = max(total_active - len(data), 0)
        summary["active_employees"] = total_active
        summary["date"] = str(d)
        summary["is_today"] = is_today
        summary["as_of"] = now.strftime("%H:%M")

        return {"rows": data, "summary": summary}

    except Exception:
        frappe.log_error(frappe.get_traceback(), "Attendance dashboard today checkins")
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













# import frappe
# from frappe.utils import getdate, flt, add_days, time_diff_in_seconds

# no_cache = 1

# OVERTIME_THRESHOLD_HOURS = 9


# def get_context(context):
#     if frappe.session.user == "Guest":
#         frappe.local.flags.redirect_location = "/login?redirect-to=/attendance-dashboard"
#         raise frappe.Redirect
#     context.no_cache = 1
#     return context


# def has_field(doctype, field):
#     try:
#         return frappe.get_meta(doctype).has_field(field)
#     except Exception:
#         return False


# def overtime_field():
#     for f in ("custom_overtime_", "overtime", "is_overtime"):
#         if has_field("Attendance", f):
#             return f
#     return None


# def late_entry_field():
#     for f in ("late_entry", "late_enty"):
#         if has_field("Attendance", f):
#             return f
#     return None


# def early_exit_field():
#     for f in ("early_exit", "early_exti"):
#         if has_field("Attendance", f):
#             return f
#     return None


# def checkin_site_field():
#     """Field on Employee Checkin that stores the site / location name."""
#     for f in ("custom_site_name", "custom_location", "location"):
#         if has_field("Employee Checkin", f):
#             return f
#     return None


# def is_overtime_enabled(value):
#     if value in (1, True, "1"):
#         return True
#     if isinstance(value, str) and value.strip().lower() in ("yes", "true"):
#         return True
#     return False


# def is_truthy(value):
#     if value in (1, True, "1"):
#         return True
#     if isinstance(value, str) and value.strip().lower() in ("yes", "true"):
#         return True
#     return False


# @frappe.whitelist()
# def get_attendance_data(from_date, to_date, department=None, employee=None):
#     try:
#         from_date = getdate(from_date)
#         to_date = getdate(to_date)

#         ot_field = overtime_field()
#         late_field = late_entry_field()
#         early_field = early_exit_field()
#         site_field = checkin_site_field()

#         # ---- build extra Attendance columns dynamically ----
#         extra_cols = []
#         if late_field:
#             extra_cols.append("a.`%s` AS late_entry_raw" % late_field)
#         if early_field:
#             extra_cols.append("a.`%s` AS early_exit_raw" % early_field)
#         if ot_field:
#             extra_cols.append("a.`%s` AS ot_raw" % ot_field)
#         extra_select = (", " + ", ".join(extra_cols)) if extra_cols else ""

#         # ---- checkin_summary CTE: first IN / last OUT time + site, per employee/day ----
#         # NOTE: check_in_time / check_out_time are kept as real datetimes here
#         # so we can compute ACTUAL hours worked (matches the "Attendance Detail
#         # with Site" report), separate from Attendance.working_hours.
#         if site_field:
#             checkin_cte = """
#                 WITH checkin_summary AS (
#                     SELECT
#                         ec.employee,
#                         DATE(ec.time) AS attendance_date,
#                         MIN(CASE WHEN ec.log_type = 'IN' THEN ec.time END) AS check_in_time,
#                         MIN(CASE WHEN ec.log_type = 'IN' THEN ec.`%s` END) AS check_in_from,
#                         MAX(CASE WHEN ec.log_type = 'OUT' THEN ec.time END) AS check_out_time,
#                         MAX(CASE WHEN ec.log_type = 'OUT' THEN ec.`%s` END) AS check_out_from
#                     FROM `tabEmployee Checkin` ec
#                     WHERE ec.docstatus < 2
#                     GROUP BY ec.employee, DATE(ec.time)
#                 )
#             """ % (site_field, site_field)
#         else:
#             checkin_cte = """
#                 WITH checkin_summary AS (
#                     SELECT
#                         ec.employee,
#                         DATE(ec.time) AS attendance_date,
#                         MIN(CASE WHEN ec.log_type = 'IN' THEN ec.time END) AS check_in_time,
#                         NULL AS check_in_from,
#                         MAX(CASE WHEN ec.log_type = 'OUT' THEN ec.time END) AS check_out_time,
#                         NULL AS check_out_from
#                     FROM `tabEmployee Checkin` ec
#                     WHERE ec.docstatus < 2
#                     GROUP BY ec.employee, DATE(ec.time)
#                 )
#             """

#         checkin_join = """
#             LEFT JOIN checkin_summary cs
#                 ON cs.employee = a.employee
#                 AND cs.attendance_date = a.attendance_date
#         """
#         checkin_select = ", cs.check_in_time, cs.check_in_from, cs.check_out_time, cs.check_out_from"

#         # ---- filters ----
#         conditions = [
#             "a.docstatus < 2",
#             "a.attendance_date BETWEEN %(from_date)s AND %(to_date)s",
#         ]
#         params = {"from_date": from_date, "to_date": to_date}

#         if department:
#             conditions.append("a.department = %(department)s")
#             params["department"] = department

#         if employee:
#             conditions.append("(a.employee_name LIKE %(employee_like)s OR a.employee = %(employee)s)")
#             params["employee_like"] = "%%%s%%" % employee
#             params["employee"] = employee

#         where_clause = " AND ".join(conditions)

#         sql = """
#             {cte}
#             SELECT
#                 a.employee, a.employee_name, a.attendance_date, a.status, a.shift,
#                 a.in_time, a.out_time, a.working_hours, a.department
#                 {extra_select}
#                 {checkin_select}
#             FROM `tabAttendance` a
#             {checkin_join}
#             WHERE {where_clause}
#             ORDER BY a.employee_name ASC, a.employee ASC, a.attendance_date DESC
#         """.format(
#             cte=checkin_cte, extra_select=extra_select, checkin_select=checkin_select,
#             checkin_join=checkin_join, where_clause=where_clause,
#         )

#         rows = frappe.db.sql(sql, params, as_dict=True)

#         data = []
#         summary = {"present": 0, "absent": 0, "on_leave": 0, "half_day": 0,
#                    "late_entry": 0, "early_exit": 0, "total_hours": 0.0,
#                    "total_actual_hours": 0.0,
#                    "total_overtime_hours": 0.0, "overtime_days": 0}

#         for r in rows:
#             d = getdate(r.attendance_date)
#             is_late = is_truthy(r.get("late_entry_raw")) if late_field else False
#             is_early = is_truthy(r.get("early_exit_raw")) if early_field else False

#             # actual hours worked, computed from real check-in/check-out timestamps
#             actual_seconds = 0
#             if r.get("check_in_time") and r.get("check_out_time") and r.get("check_out_time") > r.get("check_in_time"):
#                 actual_seconds = time_diff_in_seconds(r.get("check_out_time"), r.get("check_in_time"))
#             actual_hours = round(actual_seconds / 3600.0, 2)

#             ot_enabled = bool(ot_field) and is_overtime_enabled(r.get("ot_raw"))
#             ot_hours = round(max(flt(r.working_hours) - OVERTIME_THRESHOLD_HOURS, 0), 2) if ot_enabled else 0

#             row = {
#                 "job_number": r.employee,          # full ERP Employee ID, e.g. HR-EMP-00089
#                 "employee": r.employee,
#                 "employee_name": r.employee_name,
#                 "date": str(d),
#                 "day": d.strftime("%A"),
#                 "status": r.status,
#                 "shift": r.shift,
#                 "department": r.department,
#                 "in_time": r.in_time.strftime("%H:%M") if r.in_time else "-",
#                 "out_time": r.out_time.strftime("%H:%M") if r.out_time else "-",
#                 "check_in_time": r.get("check_in_time").strftime("%H:%M") if r.get("check_in_time") else "-",
#                 "check_in_from": r.get("check_in_from") or "-",
#                 "check_out_time": r.get("check_out_time").strftime("%H:%M") if r.get("check_out_time") else "-",
#                 "check_out_from": r.get("check_out_from") or "-",
#                 "working_hours": flt(r.working_hours, 2),
#                 "actual_hours": actual_hours,
#                 "late_entry": is_late,
#                 "early_exit": is_early,
#                 "overtime_enabled": ot_enabled,
#                 "overtime_hours": ot_hours,
#             }
#             data.append(row)

#             status_key = (r.status or "").lower().replace(" ", "_").replace("-", "_")
#             if status_key in summary:
#                 summary[status_key] += 1
#             if is_late:
#                 summary["late_entry"] += 1
#             if is_early:
#                 summary["early_exit"] += 1
#             if ot_hours > 0:
#                 summary["overtime_days"] += 1
#                 summary["total_overtime_hours"] += ot_hours
#             summary["total_hours"] += flt(r.working_hours)
#             summary["total_actual_hours"] += actual_hours

#         summary["total_records"] = len(data)
#         summary["total_hours"] = round(summary["total_hours"], 1)
#         summary["total_actual_hours"] = round(summary["total_actual_hours"], 1)
#         summary["total_overtime_hours"] = round(summary["total_overtime_hours"], 1)
#         marked = summary["present"] + summary["absent"] + summary["on_leave"] + summary["half_day"]
#         summary["attendance_pct"] = round(
#             (summary["present"] / marked) * 100, 1
#         ) if marked else 0

#         return {"rows": data, "summary": summary}

#     except Exception:
#         frappe.log_error(frappe.get_traceback(), "Attendance dashboard fetch")
#         return {"rows": [], "summary": {}, "error": frappe.get_traceback().splitlines()[-1]}


# @frappe.whitelist()
# def get_departments():
#     return frappe.get_all("Department", filters={"disabled": 0}, pluck="name", order_by="name")


# @frappe.whitelist()
# def get_latest_range():
#     """Used by the frontend to default to a range that actually has data."""
#     latest = frappe.db.get_value("Attendance", filters={}, fieldname="attendance_date",
#                                  order_by="attendance_date desc")
#     if not latest:
#         return {"from_date": None, "to_date": None}
#     latest = getdate(latest)
#     return {"from_date": str(add_days(latest, -8)), "to_date": str(latest)}
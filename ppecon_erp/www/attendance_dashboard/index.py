import frappe
from datetime import datetime, timedelta
from html import escape

from frappe import _
from frappe.utils import (
    getdate, flt, add_days, time_diff_in_seconds, nowdate, now_datetime
)
from frappe.utils.pdf import get_pdf

no_cache = 1

OVERTIME_THRESHOLD_HOURS = 9
WEEKLY_OFF_WEEKDAY = 4          # Monday=0 ... Friday=4 (Saudi weekly off) - only used for PDF highlighting
PDF_MAX_DAYS = 62               # safety limit for one PDF export

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


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _check_access(*doctypes):
    """Raw SQL below bypasses Frappe permissions, so check them explicitly.
    Access is allowed if the user can read ANY of the given doctypes."""
    doctypes = doctypes or ("Attendance",)
    if frappe.session.user == "Guest" or not any(frappe.has_permission(dt, "read") for dt in doctypes):
        frappe.throw(_("You are not permitted to view attendance data."), frappe.PermissionError)


def has_field(doctype, field):
    try:
        return frappe.get_meta(doctype).has_field(field)
    except Exception:
        return False


def _first_field(doctype, candidates):
    for f in candidates:
        if has_field(doctype, f):
            return f
    return None


def overtime_field():
    return _first_field("Attendance", ("custom_overtime_", "overtime", "is_overtime"))


def late_entry_field():
    return _first_field("Attendance", ("late_entry", "late_enty"))


def early_exit_field():
    return _first_field("Attendance", ("early_exit", "early_exti"))


def checkin_site_field():
    """Field on Employee Checkin that stores the site / location name."""
    return _first_field("Employee Checkin", ("custom_site_name", "custom_location", "location"))


def is_truthy(value):
    if value in (1, True, "1"):
        return True
    if isinstance(value, str) and value.strip().lower() in ("yes", "true"):
        return True
    return False


is_overtime_enabled = is_truthy


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


# --------------------------------------------------------------------------
# core query (shared by dashboard + PDF export)
# --------------------------------------------------------------------------
def _fetch_attendance(from_date, to_date, department=None, employee=None):
    from_date = getdate(from_date)
    to_date = getdate(to_date)
    if from_date > to_date:
        frappe.throw(_("From date cannot be after To date."))

    ot_field = overtime_field()
    late_field = late_entry_field()
    early_field = early_exit_field()
    site_field = checkin_site_field()

    extra_cols = []
    if late_field:
        extra_cols.append("a.`%s` AS late_entry_raw" % late_field)
    if early_field:
        extra_cols.append("a.`%s` AS early_exit_raw" % early_field)
    if ot_field:
        extra_cols.append("a.`%s` AS ot_raw" % ot_field)
    extra_select = (", " + ", ".join(extra_cols)) if extra_cols else ""

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
              AND DATE(ec.time) BETWEEN %(from_date)s AND %(to_date)s
            GROUP BY ec.employee, DATE(ec.time)
        )
    """.format(site_in=site_expr(site_field, "IN"), site_out=site_expr(site_field, "OUT"))

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

    sql = """
        {cte}
        SELECT
            a.employee, a.employee_name, a.attendance_date, a.status, a.shift,
            a.in_time, a.out_time, a.working_hours, a.department
            {extra_select},
            cs.check_in_time, cs.check_in_from, cs.check_out_time,
            cs.check_out_from, cs.log_count
        FROM `tabAttendance` a
        LEFT JOIN checkin_summary cs
            ON cs.employee = a.employee AND cs.attendance_date = a.attendance_date
        WHERE {where_clause}
        ORDER BY a.employee_name ASC, a.employee ASC, a.attendance_date DESC
    """.format(cte=checkin_cte, extra_select=extra_select, where_clause=" AND ".join(conditions))

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

        actual_seconds = 0
        if ci and co and co > ci:
            actual_seconds = time_diff_in_seconds(co, ci)
        actual_hours = round(actual_seconds / 3600.0, 2)

        state = completion_state(ci, co)

        ot_enabled = bool(ot_field) and is_overtime_enabled(r.get("ot_raw"))
        ot_hours = round(max(flt(r.working_hours) - OVERTIME_THRESHOLD_HOURS, 0), 2) if ot_enabled else 0

        data.append({
            "job_number": r.employee,
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
        })

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
    summary["attendance_pct"] = round((summary["present"] / marked) * 100, 1) if marked else 0

    return data, summary


# --------------------------------------------------------------------------
# whitelisted API - dashboard
# --------------------------------------------------------------------------
@frappe.whitelist()
def get_attendance_data(from_date, to_date, department=None, employee=None):
    try:
        _check_access("Attendance")
        data, summary = _fetch_attendance(from_date, to_date, department, employee)
        return {"rows": data, "summary": summary}
    except frappe.PermissionError:
        raise
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Attendance dashboard fetch")
        return {"rows": [], "summary": {}, "error": frappe.get_traceback().splitlines()[-1]}


@frappe.whitelist()
def get_today_checkins(date=None, department=None, employee=None):
    """Live check-in / check-out log for one day, straight from Employee Checkin."""
    try:
        _check_access("Employee Checkin", "Attendance")
        d = getdate(date) if date else getdate(nowdate())
        site_field = checkin_site_field()

        conditions = ["ec.docstatus < 2", "DATE(ec.time) = %(d)s"]
        params = {"d": d}

        if department:
            conditions.append("emp.department = %(department)s")
            params["department"] = department

        if employee:
            conditions.append("(emp.employee_name LIKE %(employee_like)s OR ec.employee = %(employee)s)")
            params["employee_like"] = "%%%s%%" % employee
            params["employee"] = employee

        sql = """
            SELECT
                ec.employee, emp.employee_name, emp.department, emp.designation,
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
        """.format(site_in=site_expr(site_field, "IN"), site_out=site_expr(site_field, "OUT"),
                   where=" AND ".join(conditions))

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

    except frappe.PermissionError:
        raise
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


# --------------------------------------------------------------------------
# PDF export (Arabic / English) - one landscape page per employee
# --------------------------------------------------------------------------
AR_DAYS = {"Saturday": "السبت", "Sunday": "الأحد", "Monday": "الاثنين", "Tuesday": "الثلاثاء",
           "Wednesday": "الأربعاء", "Thursday": "الخميس", "Friday": "الجمعة"}

PDF_LABELS = {
    "ar": {
        "head": ["الرقم الوظيفي", "الاسم", "التاريخ", "اليوم", "حالة الحضور", "ساعات الدوام",
                 "توقيت الحضور", "مكان الحضور", "توقيت الانصراف", "مكان الانصراف",
                 "ساعات الدوام الفعلي", "الساعات الكلية", "الساعات الاضافية", "الدقائق", "الإدارة"],
        "total": "المجموع", "title": "تقرير الحضور والانصراف", "summary": "الملخص",
        "absent": "أيام الغياب", "leave": "أيام الإجازة", "half": "نصف يوم", "present": "أيام الحضور",
        "late": "تأخير", "incomplete": "غير مكتملة", "rest": "راحة / بدون سجل",
        "extra": "إجمالي الإضافي (ساعة)",
        "status": {"Present": "مكتملة", "Absent": "غياب", "On Leave": "إجازة", "Half Day": "نصف يوم",
                   "Incomplete": "غير مكتملة", "NoPunch": "بدون بصمة", "none": "-"},
    },
    "en": {
        "head": ["Emp ID", "Name", "Date", "Day", "Status", "Shift Hrs", "Check-In", "Check-In From",
                 "Check-Out", "Check-Out From", "Actual Time", "Total Hrs", "Extra Hrs", "Minutes", "Dept."],
        "total": "Total", "title": "Attendance Report", "summary": "Summary",
        "absent": "Absent days", "leave": "Leave days", "half": "Half day", "present": "Present days",
        "late": "Late", "incomplete": "Incomplete punch", "rest": "Rest / no record",
        "extra": "Total extra (hrs)",
        "status": {"Present": "Complete", "Absent": "Absent", "On Leave": "Leave", "Half Day": "Half Day",
                   "Incomplete": "Incomplete", "NoPunch": "No punch", "none": "-"},
    },
}

PDF_CSS = """
@page { size: A4 landscape; margin: 6mm; }
body { font-family: "Noto Naskh Arabic","Noto Sans Arabic","DejaVu Sans",Arial,sans-serif; font-size: 7pt; color:#000; }
.page { page-break-after: always; }
.page:last-child { page-break-after: auto; }
.ttl { font-size: 8pt; color:#555; margin-bottom: 3px; }
table.wrap { width:100%; border-collapse:collapse; table-layout:fixed; }
table.wrap > tbody > tr > td { vertical-align:top; padding:0; }
table.wrap > tbody > tr > td.main { width:85%; }
td.side { width:15%; padding-left:6px !important; }
table.t { width:100%; border-collapse:collapse; table-layout:fixed; }
table.t th, table.t td { border:0.5px solid #000; text-align:center; padding:2px 1px; overflow:hidden;
    white-space:nowrap; font-size:6.5pt; height:13px; unicode-bidi:plaintext; }
table.t th { font-size:6.8pt; font-weight:bold; height:24px; white-space:normal; }
table.t td:nth-child(2) { white-space:normal; font-size:6pt; line-height:1.05; }
table.t thead { display: table-header-group; }
table.t tr { page-break-inside: avoid; }
.hl td { background:#ccd0ee; }
.h1 { background:#bdd7ee; } .h2 { background:#9dc3e6; }
.tot td { font-weight:bold; font-size:7.5pt; }
.box { border:1px solid #1b3a6b; }
.box .bt { background:#1b3a6b; color:#fff; font-weight:bold; text-align:center; padding:4px; font-size:8pt; }
.box .r { padding:4px 6px; border-bottom:0.5px solid #ccc; font-size:7.5pt; }
.box .r b { display:block; font-size:10pt; }
.box .r.red b { color:#c2402a; } .box .r.blue b { color:#1b6bc4; }
.box .yel { background:#ffff00; font-weight:bold; padding:5px; text-align:center; font-size:8pt; }
"""

PDF_COL_W = [8, 15.5, 7.5, 5.5, 6.5, 4, 5, 8, 5, 8, 6, 5, 5, 4.5, 6.5]


def _build_pdf_html(rows, from_date, to_date, lang="ar"):
    L = PDF_LABELS.get(lang) or PDF_LABELS["ar"]
    d0, d1 = getdate(from_date), getdate(to_date)
    dates = [d0 + timedelta(days=i) for i in range((d1 - d0).days + 1)]

    emps = {}
    for r in rows:
        emps.setdefault(r.get("employee"), []).append(r)
    ordered = sorted(emps.values(),
                     key=lambda g: (str(g[0].get("employee_name") or "").lower(), str(g[0].get("employee"))))

    cols = "".join('<col style="width:%s%%">' % w for w in PDF_COL_W)
    out = ["<html><head><meta charset='utf-8'><style>%s</style></head><body>" % PDF_CSS]

    for g in ordered:
        first = g[0]
        by_date = {str(r["date"]): r for r in g}
        cnt = dict(present=0, absent=0, leave=0, half=0, late=0, incomplete=0, rest=0)
        tot_h = tot_e = tot_m = 0
        body = []

        for d in dates:
            r = by_date.get(d.isoformat())
            hl = d.weekday() == WEEKLY_OFF_WEEKDAY
            if not r:
                key, hh, mm, tm = "none", 0, 0, 0
                tin = tout = pin = pout = dept = "-"
                hl = True
                cnt["rest"] += 1
            else:
                st = r.get("status") or ""
                state = r.get("completion")
                if st == "Absent":
                    key, hl = "Absent", True
                    cnt["absent"] += 1
                elif st == "On Leave":
                    key, hl = "On Leave", True
                    cnt["leave"] += 1
                elif state == "Incomplete":
                    key, hl = "Incomplete", True
                    cnt["incomplete"] += 1
                    if st == "Present":
                        cnt["present"] += 1
                    elif st == "Half Day":
                        cnt["half"] += 1
                elif st == "Half Day":
                    key = "Half Day"
                    cnt["half"] += 1
                elif state in ("No Check-in", "Missing Check-in"):
                    key, hl = "NoPunch", True
                    cnt["present"] += 1
                else:
                    key = "Present"
                    cnt["present"] += 1
                if r.get("late_entry"):
                    cnt["late"] += 1
                tin, tout = r.get("check_in_time") or "-", r.get("check_out_time") or "-"
                pin, pout = r.get("check_in_from") or "-", r.get("check_out_from") or "-"
                dept = r.get("department") or "-"
                tm = round(flt(r.get("actual_hours")) * 60)
                hh, mm = divmod(tm, 60)
                if key in ("Absent", "On Leave"):
                    hh = mm = tm = 0

            ex = max(0, hh - OVERTIME_THRESHOLD_HOURS)
            tot_h += hh
            tot_e += ex
            tot_m += mm
            day_txt = AR_DAYS[d.strftime("%A")] if lang == "ar" else d.strftime("%a")
            vals = [first.get("employee"), first.get("employee_name"), d.isoformat(), day_txt,
                    L["status"][key], "-", tin, pin, tout, pout,
                    "%02d:%02d" % (tm // 60, tm % 60), hh, ex, mm, dept]
            body.append('<tr class="%s">%s</tr>' % (
                "hl" if hl else "",
                "".join("<td>%s</td>" % escape(str(v if v is not None else "-")) for v in vals)))

        head = "".join('<th class="%s">%s</th>' % ("h1" if i in (11, 12) else "h2" if i == 13 else "", h)
                       for i, h in enumerate(L["head"]))
        total = ('<tr class="tot"><td>%s</td>' % L["total"] + "<td></td>" * 10
                 + "<td>%s</td><td>%s</td><td>%s</td><td></td></tr>" % (tot_h, tot_e, tot_m))

        rtl = ' dir="rtl"' if lang == "ar" else ""

        def row(label, val, cls=""):
            return '<div class="r %s">%s<b>%s</b></div>' % (cls, label, val)

        side = ('<div class="box"%s><div class="bt">%s</div>' % (rtl, L["summary"])
                + row(L["present"], cnt["present"]) + row(L["absent"], cnt["absent"], "red")
                + row(L["leave"], cnt["leave"], "blue") + row(L["half"], cnt["half"])
                + row(L["late"], cnt["late"]) + row(L["incomplete"], cnt["incomplete"])
                + row(L["rest"], cnt["rest"])
                + '<div class="yel">%s<br>%.2f</div></div>' % (L["extra"], tot_e + tot_m / 60.0))

        out.append(
            '<div class="page"><div class="ttl" dir="ltr">%s | %s → %s | %s</div>'
            '<table class="wrap"><tr><td class="main"><table class="t"><colgroup>%s</colgroup>'
            '<thead><tr>%s</tr></thead><tbody>%s%s</tbody></table></td><td class="side">%s</td></tr></table></div>'
            % (L["title"], from_date, to_date, escape(str(first.get("employee_name") or "")),
               cols, head, "".join(body), total, side))

    out.append("</body></html>")
    return "".join(out)


@frappe.whitelist()
def export_attendance_pdf(from_date, to_date, department=None, employee=None, lang="ar"):
    _check_access("Attendance")
    d0, d1 = getdate(from_date), getdate(to_date)
    if (d1 - d0).days + 1 > PDF_MAX_DAYS:
        frappe.throw(_("PDF export is limited to {0} days. Please choose a shorter range.").format(PDF_MAX_DAYS))

    rows, _summary = _fetch_attendance(from_date, to_date, department, employee)
    if not rows:
        frappe.throw(_("No attendance records found for this selection."))

    lang = lang if lang in PDF_LABELS else "ar"
    html = _build_pdf_html(rows, str(d0), str(d1), lang)
    frappe.local.response.filename = "attendance_%s_%s_%s.pdf" % (lang, d0, d1)
    frappe.local.response.filecontent = get_pdf(html, {
        "orientation": "Landscape", "page-size": "A4",
        "margin-top": "6mm", "margin-bottom": "6mm", "margin-left": "6mm", "margin-right": "6mm",
    })
    frappe.local.response.type = "pdf"


# import frappe
# from frappe.utils import (
#     getdate, flt, add_days, time_diff_in_seconds, nowdate, now_datetime
# )

# no_cache = 1

# OVERTIME_THRESHOLD_HOURS = 9

# STATE_KEY = {
#     "Completed": "completed",
#     "Incomplete": "incomplete",
#     "Missing Check-in": "missing_checkin",
#     "No Check-in": "no_checkin",
# }


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


# def completion_state(check_in, check_out):
#     """Completed = both punches, Incomplete = checked in but never checked out."""
#     if check_in and check_out:
#         return "Completed"
#     if check_in:
#         return "Incomplete"
#     if check_out:
#         return "Missing Check-in"
#     return "No Check-in"


# def fmt_duration(seconds):
#     seconds = int(seconds or 0)
#     if seconds <= 0:
#         return "-"
#     return "%dh %02dm" % (seconds // 3600, (seconds % 3600) // 60)


# def site_expr(site_field, log_type):
#     """Site of the FIRST IN / LAST OUT (not just the alphabetically smallest one)."""
#     if not site_field:
#         return "NULL"
#     agg = "MIN" if log_type == "IN" else "MAX"
#     return (
#         "SUBSTRING_INDEX(%s(CASE WHEN ec.log_type = '%s' "
#         "THEN CONCAT(ec.time, '||', IFNULL(ec.`%s`, '')) END), '||', -1)"
#         % (agg, log_type, site_field)
#     )


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
#         checkin_cte = """
#             WITH checkin_summary AS (
#                 SELECT
#                     ec.employee,
#                     DATE(ec.time) AS attendance_date,
#                     MIN(CASE WHEN ec.log_type = 'IN' THEN ec.time END) AS check_in_time,
#                     {site_in} AS check_in_from,
#                     MAX(CASE WHEN ec.log_type = 'OUT' THEN ec.time END) AS check_out_time,
#                     {site_out} AS check_out_from,
#                     COUNT(*) AS log_count
#                 FROM `tabEmployee Checkin` ec
#                 WHERE ec.docstatus < 2
#                 GROUP BY ec.employee, DATE(ec.time)
#             )
#         """.format(
#             site_in=site_expr(site_field, "IN"),
#             site_out=site_expr(site_field, "OUT"),
#         )

#         checkin_join = """
#             LEFT JOIN checkin_summary cs
#                 ON cs.employee = a.employee
#                 AND cs.attendance_date = a.attendance_date
#         """
#         checkin_select = (
#             ", cs.check_in_time, cs.check_in_from, cs.check_out_time, "
#             "cs.check_out_from, cs.log_count"
#         )

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
#                    "total_overtime_hours": 0.0, "overtime_days": 0,
#                    "completed": 0, "incomplete": 0,
#                    "missing_checkin": 0, "no_checkin": 0}

#         for r in rows:
#             d = getdate(r.attendance_date)
#             is_late = is_truthy(r.get("late_entry_raw")) if late_field else False
#             is_early = is_truthy(r.get("early_exit_raw")) if early_field else False

#             ci = r.get("check_in_time")
#             co = r.get("check_out_time")

#             # actual hours worked, computed from real check-in/check-out timestamps
#             actual_seconds = 0
#             if ci and co and co > ci:
#                 actual_seconds = time_diff_in_seconds(co, ci)
#             actual_hours = round(actual_seconds / 3600.0, 2)

#             state = completion_state(ci, co)

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
#                 "check_in_time": ci.strftime("%H:%M") if ci else "-",
#                 "check_in_from": r.get("check_in_from") or "-",
#                 "check_out_time": co.strftime("%H:%M") if co else "-",
#                 "check_out_from": r.get("check_out_from") or "-",
#                 "log_count": r.get("log_count") or 0,
#                 "completion": state,
#                 "working_hours": flt(r.working_hours, 2),
#                 "actual_hours": actual_hours,
#                 "late_entry": is_late,
#                 "early_exit": is_early,
#                 "overtime_enabled": ot_enabled,
#                 "overtime_hours": ot_hours,
#             }
#             data.append(row)

#             status_key = (r.status or "").lower().replace(" ", "_").replace("-", "_")
#             if status_key in ("present", "absent", "on_leave", "half_day"):
#                 summary[status_key] += 1
#             summary[STATE_KEY[state]] += 1
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
# def get_today_checkins(date=None, department=None, employee=None):
#     """Live check-in / check-out log for one day, straight from Employee Checkin.

#     Works even when Attendance for the day has not been marked yet, so HR can see
#     who punched in, from which site, and who has not punched out (Incomplete).
#     """
#     try:
#         d = getdate(date) if date else getdate(nowdate())
#         site_field = checkin_site_field()

#         conditions = ["ec.docstatus < 2", "DATE(ec.time) = %(d)s"]
#         params = {"d": d}

#         if department:
#             conditions.append("emp.department = %(department)s")
#             params["department"] = department

#         if employee:
#             conditions.append(
#                 "(emp.employee_name LIKE %(employee_like)s OR ec.employee = %(employee)s)"
#             )
#             params["employee_like"] = "%%%s%%" % employee
#             params["employee"] = employee

#         sql = """
#             SELECT
#                 ec.employee,
#                 emp.employee_name,
#                 emp.department,
#                 emp.designation,
#                 MIN(CASE WHEN ec.log_type = 'IN' THEN ec.time END) AS check_in_time,
#                 {site_in} AS check_in_from,
#                 MAX(CASE WHEN ec.log_type = 'OUT' THEN ec.time END) AS check_out_time,
#                 {site_out} AS check_out_from,
#                 COUNT(*) AS log_count
#             FROM `tabEmployee Checkin` ec
#             LEFT JOIN `tabEmployee` emp ON emp.name = ec.employee
#             WHERE {where}
#             GROUP BY ec.employee, emp.employee_name, emp.department, emp.designation
#             ORDER BY check_in_time ASC, emp.employee_name ASC
#         """.format(
#             site_in=site_expr(site_field, "IN"),
#             site_out=site_expr(site_field, "OUT"),
#             where=" AND ".join(conditions),
#         )

#         rows = frappe.db.sql(sql, params, as_dict=True)

#         now = now_datetime()
#         is_today = d == getdate(nowdate())

#         data = []
#         summary = {"total": 0, "completed": 0, "incomplete": 0,
#                    "missing_checkin": 0, "sites": 0, "not_checked_in": 0}
#         sites = set()

#         for r in rows:
#             ci = r.get("check_in_time")
#             co = r.get("check_out_time")
#             state = completion_state(ci, co)

#             if ci and co and co > ci:
#                 secs = time_diff_in_seconds(co, ci)
#             elif ci and not co and is_today and now > ci:
#                 secs = time_diff_in_seconds(now, ci)
#             else:
#                 secs = 0

#             for s in (r.get("check_in_from"), r.get("check_out_from")):
#                 if s:
#                     sites.add(s)

#             data.append({
#                 "job_number": r.employee,
#                 "employee": r.employee,
#                 "employee_name": r.employee_name or r.employee,
#                 "department": r.department or "-",
#                 "designation": r.designation or "-",
#                 "date": str(d),
#                 "check_in_time": ci.strftime("%H:%M") if ci else "-",
#                 "check_in_from": r.get("check_in_from") or "-",
#                 "check_out_time": co.strftime("%H:%M") if co else "-",
#                 "check_out_from": r.get("check_out_from") or "-",
#                 "log_count": r.get("log_count") or 0,
#                 "completion": state,
#                 "duration": fmt_duration(secs),
#                 "duration_hours": round(secs / 3600.0, 2),
#                 "running": bool(ci and not co and is_today),
#             })

#             summary[STATE_KEY[state]] = summary.get(STATE_KEY[state], 0) + 1

#         summary["total"] = len(data)
#         summary["sites"] = len(sites)

#         total_active = frappe.db.count("Employee", {"status": "Active"})
#         summary["not_checked_in"] = max(total_active - len(data), 0)
#         summary["active_employees"] = total_active
#         summary["date"] = str(d)
#         summary["is_today"] = is_today
#         summary["as_of"] = now.strftime("%H:%M")

#         return {"rows": data, "summary": summary}

#     except Exception:
#         frappe.log_error(frappe.get_traceback(), "Attendance dashboard today checkins")
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











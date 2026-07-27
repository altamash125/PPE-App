# Copyright (c) 2026, altamash and contributors
# For license information, please see license.txt

# import frappe


def execute(filters=None):
	columns, data = [], []
	return columns, data


import frappe
from frappe import _
from frappe.utils import getdate, flt


def execute(filters=None):
    columns = get_columns()
    data    = get_data(filters)
    return columns, data


def get_columns():
    return [
        {
            "label"    : _("SL No"),
            "fieldname": "sl_no",
            "fieldtype": "Int",
            "width"    : 60,
        },
        {
            "label"    : _("Employee ID"),
            "fieldname": "employee",
            "fieldtype": "Link",
            "options"  : "Employee",
            "width"    : 130,
        },
        {
            "label"    : _("Employee Name"),
            "fieldname": "employee_name",
            "fieldtype": "Data",
            "width"    : 180,
        },
        {
            "label"    : _("Department"),
            "fieldname": "department",
            "fieldtype": "Data",
            "width"    : 150,
        },
        {
            "label"    : _("Branch / Cost Center"),
            "fieldname": "branch",
            "fieldtype": "Data",
            "width"    : 130,
        },
        {
            "label"    : _("Basic (SAR)"),
            "fieldname": "basic",
            "fieldtype": "Currency",
            "width"    : 120,
        },
        {
            "label"    : _("Food Allowance (SAR)"),
            "fieldname": "food_allowance",
            "fieldtype": "Currency",
            "width"    : 150,
        },
        {
            "label"    : _("Living Allowance (SAR)"),
            "fieldname": "living_allowance",
            "fieldtype": "Currency",
            "width"    : 150,
        },
        {
            "label"    : _("Gross Salary (SAR)"),
            "fieldname": "gross_salary",
            "fieldtype": "Currency",
            "width"    : 140,
        },
        {
            "label"    : _("Working Days"),
            "fieldname": "working_days",
            "fieldtype": "Int",
            "width"    : 110,
        },
        {
            "label"    : _("OT Hours"),
            "fieldname": "overtime_hours",
            "fieldtype": "Float",
            "precision": 2,
            "width"    : 100,
        },
        {
            "label"    : _("OT Minutes"),
            "fieldname": "overtime_minutes",
            "fieldtype": "Int",
            "width"    : 100,
        },
        {
            "label"    : _("Overtime Wage (SAR)"),
            "fieldname": "overtime_amount",
            "fieldtype": "Currency",
            "width"    : 150,
        },
        {
            "label"    : _("Day Type"),
            "fieldname": "day_type",
            "fieldtype": "Data",
            "width"    : 100,
        },
        {
            "label"    : _("Date"),
            "fieldname": "attendance_date",
            "fieldtype": "Date",
            "width"    : 100,
        },
        {
            "label"    : _("In Time"),
            "fieldname": "in_time",
            "fieldtype": "Data",
            "width"    : 90,
        },
        {
            "label"    : _("Out Time"),
            "fieldname": "out_time",
            "fieldtype": "Data",
            "width"    : 90,
        },
        {
            "label"    : _("Working Hours"),
            "fieldname": "working_hours",
            "fieldtype": "Float",
            "precision": 2,
            "width"    : 120,
        },
    ]


def get_data(filters):
    if not filters:
        filters = {}

    from_date  = filters.get("from_date")
    to_date    = filters.get("to_date")
    employee   = filters.get("employee")
    department = filters.get("department")
    branch     = filters.get("branch")

    # ── Filters ───────────────────────────────────────────────────────────
    conditions = """
        a.docstatus = 1
        AND a.status = 'Present'
        AND a.custom_overtime_ = 'Yes'
    """
    if from_date  : conditions += f" AND a.attendance_date >= '{from_date}'"
    if to_date    : conditions += f" AND a.attendance_date <= '{to_date}'"
    if employee   : conditions += f" AND a.employee = '{employee}'"
    if department : conditions += f" AND a.department = '{department}'"

    # ── Attendance records ────────────────────────────────────────────────
    records = frappe.db.sql(f"""
        SELECT
            a.employee,
            a.employee_name,
            a.department,
            a.attendance_date,
            a.working_hours,
            a.in_time,
            a.out_time
        FROM `tabAttendance` a
        WHERE {conditions}
        ORDER BY a.employee, a.attendance_date
    """, as_dict=True)

    if not records:
        return []

    employees = list(set(r.employee for r in records))

    # ── Holiday dates ─────────────────────────────────────────────────────
    holiday_dates = get_holiday_dates(from_date, to_date)

    # ── Employee info: CTC + Branch ───────────────────────────────────────
    employee_info = get_employee_info(employees)

    # ── Salary Slip earnings per employee for the month ───────────────────
    salary_info = get_salary_slip_earnings(employees, from_date, to_date)

    # ── Process records ───────────────────────────────────────────────────
    OVERTIME_THRESHOLD = 9.0   # 9 ghante ke baad OT shuru hota hai

    data         = []
    sl_no        = 1
    total_ot_hrs = 0
    total_ot_min = 0
    total_ot_amt = 0

    for row in records:
        date        = getdate(row.attendance_date)
        day_name    = date.strftime("%A")
        is_friday   = day_name == "Friday"
        is_holiday  = str(row.attendance_date) in holiday_dates
        working_hrs = flt(row.working_hours)

        # ── Salary data ───────────────────────────────────────────────────
        emp_info  = employee_info.get(row.employee, {})
        sal_info  = salary_info.get(row.employee, {})

        gross_salary     = flt(emp_info.get("ctc", 0))   # Employee.ctc
        basic            = flt(sal_info.get("basic", 0))
        food_allowance   = flt(sal_info.get("food_allowance", 0))
        living_allowance = flt(sal_info.get("living_allowance", 0))
        branch_name      = emp_info.get("branch", "")

        # ── Overtime hours ────────────────────────────────────────────────
        if is_friday or is_holiday:
            # Friday / Holiday — pura din OT, koi threshold nahi
            ot_hours = working_hrs
            day_type = "Holiday" if is_holiday else "Friday"
        else:
            # Normal day — sirf 9 ghante ke baad ka time OT
            day_type = "Normal"
            ot_hours = max(0, working_hrs - OVERTIME_THRESHOLD)

        if ot_hours <= 0:
            continue

        ot_minutes = round(ot_hours * 60)

        # ── Saudi Labour Law Formula ──────────────────────────────────────
        #
        #   Formula sabke liye SAME hai (Normal / Friday / Holiday):
        #   OT Amount = (CTC/30/8 × OT_hrs) + (Basic/30/8 × 0.5 × OT_hrs)
        #
        #   Sirf OT_hrs change hota hai:
        #   Normal Day  → working_hours - 9  (9 ke baad ka time)
        #   Friday      → working_hours PURE (sare hours OT)
        #   Holiday     → working_hours PURE (sare hours OT)
        #
        ctc_per_hour   = gross_salary / 30 / 8 if gross_salary else 0
        basic_per_hour = basic        / 30 / 8 if basic        else 0

        ot_amount = (
            (ctc_per_hour   * ot_hours) +
            (basic_per_hour * 0.5 * ot_hours)
        )

        ot_amount = round(ot_amount, 2)

        total_ot_hrs += ot_hours
        total_ot_min += ot_minutes
        total_ot_amt += ot_amount

        data.append({
            "sl_no"           : sl_no,
            "employee"        : row.employee,
            "employee_name"   : row.employee_name,
            "department"      : row.department,
            "branch"          : branch_name,
            "basic"           : basic,
            "food_allowance"  : food_allowance,
            "living_allowance": living_allowance,
            "gross_salary"    : gross_salary,
            "working_days"    : 30,
            "overtime_hours"  : round(ot_hours, 2),
            "overtime_minutes": ot_minutes,
            "overtime_amount" : ot_amount,
            "day_type"        : day_type,
            "attendance_date" : row.attendance_date,
            "in_time"         : str(row.in_time)[11:16] if row.in_time else "-",
            "out_time"        : str(row.out_time)[11:16] if row.out_time else "-",
            "working_hours"   : round(working_hrs, 2),
        })

        sl_no += 1

    # ── Total row ─────────────────────────────────────────────────────────
    if data:
        data.append({
            "sl_no"           : "",
            "employee"        : "",
            "employee_name"   : "── TOTAL ──",
            "department"      : "",
            "branch"          : "",
            "basic"           : "",
            "food_allowance"  : "",
            "living_allowance": "",
            "gross_salary"    : "",
            "working_days"    : "",
            "overtime_hours"  : round(total_ot_hrs, 2),
            "overtime_minutes": total_ot_min,
            "overtime_amount" : round(total_ot_amt, 2),
            "day_type"        : "",
            "attendance_date" : "",
            "in_time"         : "",
            "out_time"        : "",
            "working_hours"   : "",
        })

    return data


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_holiday_dates(from_date, to_date):
    rows = frappe.db.sql("""
        SELECT h.holiday_date
        FROM `tabHoliday` h
        INNER JOIN `tabHoliday List` hl ON h.parent = hl.name
        WHERE h.holiday_date BETWEEN %s AND %s
    """, (from_date, to_date), as_dict=True)
    return set(str(r.holiday_date) for r in rows)


def get_employee_info(employees):
    """CTC aur Branch Employee doctype se"""
    result = {}
    if not employees:
        return result

    emp_list = ", ".join([f"'{e}'" for e in employees])
    rows = frappe.db.sql(f"""
        SELECT
            name,
            ctc,
            branch,
            department
        FROM `tabEmployee`
        WHERE name IN ({emp_list})
    """, as_dict=True)

    for r in rows:
        result[r.name] = {
            "ctc"       : flt(r.ctc),
            "branch"    : r.branch or "",
            "department": r.department or "",
        }
    return result


def get_salary_slip_earnings(employees, from_date, to_date):
    """
    Salary Slip se Basic, Food, Living nikalo — us month ka slip
    Agar multiple slips hain to latest lo
    """
    result = {}
    if not employees:
        return result

    # Month determine karo from_date se
    date_obj   = getdate(from_date)
    month_year = f"{date_obj.year}-{str(date_obj.month).zfill(2)}"

    emp_list = ", ".join([f"'{e}'" for e in employees])

    # Salary Slip jo us month mein submitted ho
    slips = frappe.db.sql(f"""
        SELECT
            ss.employee,
            ss.name AS slip_name
        FROM `tabSalary Slip` ss
        WHERE
            ss.employee IN ({emp_list})
            AND ss.docstatus = 1
            AND DATE_FORMAT(ss.start_date, '%Y-%m') = '{month_year}'
        ORDER BY ss.start_date DESC
    """, as_dict=True)

    if not slips:
        return result

    # Har employee ka latest slip
    slip_map = {}
    for s in slips:
        if s.employee not in slip_map:
            slip_map[s.employee] = s.slip_name

    # Earnings details nikalo
    slip_names = ", ".join([f"'{v}'" for v in slip_map.values()])

    earnings = frappe.db.sql(f"""
        SELECT
            ssd.parent AS slip_name,
            ssd.salary_component,
            ssd.amount
        FROM `tabSalary Detail` ssd
        WHERE
            ssd.parent IN ({slip_names})
            AND ssd.parentfield = 'earnings'
    """, as_dict=True)

    # Map: employee → {basic, food, living}
    # Slip name → employee reverse map
    slip_to_emp = {v: k for k, v in slip_map.items()}

    for row in earnings:
        emp   = slip_to_emp.get(row.slip_name)
        if not emp:
            continue
        if emp not in result:
            result[emp] = {
                "basic"           : 0,
                "food_allowance"  : 0,
                "living_allowance": 0,
            }

        comp = (row.salary_component or "").lower()

        if "basic" in comp:
            result[emp]["basic"] = flt(row.amount)
        elif "food" in comp:
            result[emp]["food_allowance"] = flt(row.amount)
        elif "living" in comp or "house" in comp or "accommodation" in comp:
            result[emp]["living_allowance"] = flt(row.amount)

    return result
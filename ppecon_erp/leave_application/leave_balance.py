import frappe
from frappe.utils import flt, getdate, today

@frappe.whitelist()
def get_my_leave_balance():
    user = frappe.session.user

    if user == "Guest":
        frappe.throw("User not logged in", frappe.AuthenticationError)

    employee = frappe.db.get_value("Employee", {"user_id": user}, "name")

    if not employee:
        frappe.throw("No employee linked to this user")

    today_date = getdate(today())
    leave_types = ["Annual Leave", "Sick Leave"]
    result = {}

    for leave_type in leave_types:
        # Credited — to_date filter nahi, sirf from_date <= today
        credited = frappe.db.sql("""
            SELECT COALESCE(SUM(leaves), 0) as total
            FROM `tabLeave Ledger Entry`
            WHERE employee = %s
              AND leave_type = %s
              AND leaves > 0
              AND is_expired = 0
              AND from_date <= %s
        """, (employee, leave_type, today_date), as_dict=1)[0].total

        # Debited — leave taken
        debited = frappe.db.sql("""
            SELECT COALESCE(SUM(leaves), 0) as total
            FROM `tabLeave Ledger Entry`
            WHERE employee = %s
              AND leave_type = %s
              AND leaves < 0
              AND is_expired = 0
              AND from_date <= %s
        """, (employee, leave_type, today_date), as_dict=1)[0].total

        balance = round(flt(credited) + flt(debited), 2)

        key = "annual_leave" if leave_type == "Annual Leave" else "sick_leave"
        result[key] = float(balance)

    return result



#Leave Balance API
import frappe
from frappe.utils import today, getdate, add_months, flt
from datetime import date
import calendar


def update_monthly_leave_allocations():
    today_date = getdate(today())
    first_of_last_month = add_months(today_date, -1)

    last_month_total_days = calendar.monthrange(
        first_of_last_month.year,
        first_of_last_month.month
    )[1]

    last_month_start = date(first_of_last_month.year, first_of_last_month.month, 1)
    last_month_end = date(first_of_last_month.year, first_of_last_month.month, last_month_total_days)

    print(f"Processing month: {last_month_start} to {last_month_end}")

    employees = frappe.get_all(
        "Employee",
        filters={"status": "Active"},
        fields=["name", "employee_name", "date_of_joining", "custom_contract_period"]
    )

    print(f"Total active employees: {len(employees)}")

    for emp in employees:
        try:
            process_employee(emp, last_month_start, last_month_end, last_month_total_days)
        except Exception as e:
            frappe.log_error(
                f"Leave Scheduler Error for {emp.name}: {str(e)}",
                "Monthly Leave Accrual"
            )
            print(f"ERROR {emp.name}: {str(e)}")
            continue

    frappe.db.commit()
    print("Done. All committed.")


def process_employee(emp, month_start, month_end, total_days_in_month):
    contract = str(emp.get("custom_contract_period") or "").strip().lower()

    if contract in ["two years", "two year", "2 years", "2 year"]:
        annual_days = 45.0
        contract_months = 24
    else:
        annual_days = 30.0
        contract_months = 12

    full_month_accrual = round(annual_days / contract_months, 4)

    if not emp.date_of_joining:
        print(f"SKIP {emp.name}: no joining date")
        return

    joining_date = getdate(emp.date_of_joining)

    if joining_date > month_end:
        print(f"SKIP {emp.name}: joining date {joining_date} is after month end")
        return

    effective_start = max(joining_date, month_start)

    approved_leaves = frappe.db.sql("""
        SELECT from_date, to_date, total_leave_days
        FROM `tabLeave Application`
        WHERE employee = %s
          AND leave_type = 'Annual Leave'
          AND status = 'Approved'
          AND docstatus = 1
          AND from_date <= %s
          AND to_date >= %s
        ORDER BY from_date ASC
    """, (emp.name, month_end, month_start), as_dict=1)

    eligible_days = calculate_eligible_days(effective_start, month_end, approved_leaves)
    total_days = (month_end - effective_start).days + 1

    if eligible_days <= 0:
        print(f"SKIP {emp.name}: 0 eligible days (all on leave this month)")
        return

    accrual_amount = round((eligible_days / total_days) * full_month_accrual, 4)

    print(f"{emp.employee_name} | contract={contract} | "
          f"eligible={eligible_days}/{total_days} days | "
          f"accrual=+{accrual_amount}")

    update_leave_allocation(emp, accrual_amount, month_start, month_end)


def calculate_eligible_days(start, end, approved_leaves):
    total_days = (end - start).days + 1
    leave_days = 0

    for leave in approved_leaves:
        leave_from = getdate(leave.from_date)
        leave_to = getdate(leave.to_date)
        overlap_start = max(leave_from, start)
        overlap_end = min(leave_to, end)
        if overlap_start <= overlap_end:
            leave_days += (overlap_end - overlap_start).days + 1

    return max(0, total_days - leave_days)


def update_leave_allocation(emp, accrual_amount, month_start, month_end):
    leave_type = "Annual Leave"

    fiscal_year = frappe.db.get_value(
        "Fiscal Year",
        filters={
            "year_start_date": ("<=", month_end),
            "year_end_date": (">=", month_start)
        },
        fieldname="name"
    )

    if not fiscal_year:
        print(f"SKIP {emp.name}: no fiscal year found")
        return

    # FIX: also fetch to_date and carry forwarded count
    allocation = frappe.db.get_value(
        "Leave Allocation",
        filters={
            "employee": emp.name,
            "leave_type": leave_type,
            "docstatus": 1,
            "from_date": ("<=", month_end),
            "to_date": (">=", month_start)
        },
        fieldname=["name", "new_leaves_allocated", "total_leaves_allocated",
                   "to_date", "carry_forwarded_leaves_count"],
        as_dict=1
    )

    if not allocation:
        create_new_allocation(emp, leave_type, accrual_amount, fiscal_year)
        return

    # FIX: duplicate check FIRST — if the ledger entry for this month
    # already exists, skip BOTH ledger and allocation update.
    # Uniqueness key = allocation + from_date (month_start).
    existing = frappe.db.exists("Leave Ledger Entry", {
        "employee": emp.name,
        "leave_type": leave_type,
        "transaction_type": "Leave Allocation",
        "transaction_name": allocation.name,
        "from_date": month_start
    })

    if existing:
        print(f"  → Accrual for {month_start} already posted, skipping {emp.name}")
        return

    # Update the allocation document
    new_leaves = round(flt(allocation.new_leaves_allocated) + accrual_amount, 4)
    new_total = round(new_leaves + flt(allocation.carry_forwarded_leaves_count), 4)

    frappe.db.set_value(
        "Leave Allocation",
        allocation.name,
        {
            "new_leaves_allocated": new_leaves,
            "total_leaves_allocated": new_total
        }
    )

    # FIX: to_date must be the allocation's to_date (fiscal year end),
    # NOT month_end. ERPNext's get_leave_balance_on only counts allocation
    # ledger entries where from_date <= today AND to_date >= today.
    ledger = frappe.get_doc({
        "doctype": "Leave Ledger Entry",
        "employee": emp.name,
        "leave_type": leave_type,
        "transaction_type": "Leave Allocation",
        "transaction_name": allocation.name,
        "leaves": accrual_amount,
        "from_date": month_start,
        "to_date": allocation.to_date,   # ← the critical fix
        "is_carry_forward": 0,
        "is_expired": 0,
        "is_lwp": 0
    })
    ledger.insert(ignore_permissions=True)
    ledger.submit()

    print(f"  → Updated allocation {allocation.name} | ledger +{accrual_amount} | new total: {new_total}")


def create_new_allocation(emp, leave_type, accrual_amount, fiscal_year):
    fy_dates = frappe.db.get_value(
        "Fiscal Year", fiscal_year,
        ["year_start_date", "year_end_date"],
        as_dict=1
    )

    alloc = frappe.get_doc({
        "doctype": "Leave Allocation",
        "employee": emp.name,
        "employee_name": emp.employee_name,
        "leave_type": leave_type,
        "from_date": fy_dates.year_start_date,
        "to_date": fy_dates.year_end_date,
        "new_leaves_allocated": accrual_amount,
        "total_leaves_allocated": accrual_amount,
        "carry_forward": 0
    })
    alloc.insert(ignore_permissions=True)
    alloc.submit()  # submit auto-creates the ledger entry with correct dates
    print(f"  → New allocation created: {accrual_amount} days")


def fix_old_ledger_entries():
    """
    One-time patch: repair ledger entries already created by the old scheduler
    with wrong to_date (= month end). Sets to_date = allocation's to_date so
    ERPNext starts counting them in the balance.
    Run once via bench console: 
        from your_app.your_module import fix_old_ledger_entries
        fix_old_ledger_entries()
    """
    entries = frappe.db.sql("""
        SELECT lle.name, lle.transaction_name, la.to_date AS alloc_to_date
        FROM `tabLeave Ledger Entry` lle
        JOIN `tabLeave Allocation` la ON la.name = lle.transaction_name
        WHERE lle.transaction_type = 'Leave Allocation'
          AND lle.leaves > 0
          AND lle.to_date < la.to_date
    """, as_dict=1)

    for e in entries:
        frappe.db.set_value("Leave Ledger Entry", e.name, "to_date", e.alloc_to_date)
        print(f"Fixed {e.name}: to_date → {e.alloc_to_date}")

    frappe.db.commit()
    print(f"Done. {len(entries)} entries fixed.")
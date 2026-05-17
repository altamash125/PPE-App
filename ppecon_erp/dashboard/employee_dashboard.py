import frappe
from frappe import _
from frappe.utils import today, getdate, now

@frappe.whitelist()
def get_hr_dashboard_data():
    """
    HR Dashboard API - Clean & Optimized
    """

    # ✅ FETCH DATA (NO SQL BUGS, FULL FIELD CONTROL)
    employees = frappe.get_all("Employee",
        fields=[
            "name as employee_id",
            "employee_name",
            "gender",
            "designation",
            "branch",
            "custom_nationality as nationality",
            "status",
            "date_of_joining",
            "date_of_birth",

            # Probation / HR fields
            "custom_probation_status as probation_status",
            "custom_hiring_type as hiring_type",
            "custom_contract_period as contract_period",
            "custom_contract_status as contract_status",

            # ✅ IMPORTANT FIXED FIELDS (your issue)
            "id_iqama as id_iqama",
            "iqama_occupation as iqama_occupation",
            "custom_expire_date as iqama_expire_date",

            # Passport
            "valid_upto as passport_valid_upto"
        ],
        order_by="date_of_joining desc"
    )

    # =========================
    # DATE CONVERSION SAFETY
    # =========================
    for emp in employees:
        for key in [
            "date_of_joining",
            "date_of_birth",
            "iqama_expire_date",
            "passport_valid_upto"
        ]:
            if emp.get(key):
                emp[key] = str(emp[key])

    # =========================
    # BASIC COUNTS
    # =========================
    total_employees = len(employees)
    active_employees = len([e for e in employees if e.get("status") == "Active"])

    current_date = getdate(today())
    current_year = current_date.year
    current_month = current_date.month

    # =========================
    # NEW HIRES
    # =========================
    new_hires_year = len([
        e for e in employees
        if e.get("date_of_joining") and
        getdate(e["date_of_joining"]).year == current_year
    ])

    new_hires_month = len([
        e for e in employees
        if e.get("date_of_joining") and
        getdate(e["date_of_joining"]).year == current_year and
        getdate(e["date_of_joining"]).month == current_month
    ])

    # =========================
    # PROBATION
    # =========================
    probation_employees = len([
        e for e in employees
        if e.get("probation_status")
        and "under" in e["probation_status"].lower()
        and e.get("status") == "Active"
    ])

    # =========================
    # IQAMA EXPIRY (30 DAYS)
    # =========================
    expiring_iqama = len([
        e for e in employees
        if e.get("iqama_expire_date") and
        getdate(e["iqama_expire_date"]) >= current_date and
        (getdate(e["iqama_expire_date"]) - current_date).days <= 30
    ])

    # =========================
    # PASSPORT EXPIRY THIS MONTH
    # =========================
    passport_expiring_this_month = len([
        e for e in employees
        if e.get("passport_valid_upto") and
        getdate(e["passport_valid_upto"]).year == current_year and
        getdate(e["passport_valid_upto"]).month == current_month
    ])

    # =========================
    # DISTRIBUTIONS
    # =========================
    gender_distribution = {
        "male": len([e for e in employees if e.get("gender") == "Male"]),
        "female": len([e for e in employees if e.get("gender") == "Female"]),
        "other": len([e for e in employees if e.get("gender") not in ["Male", "Female"]])
    }

    designation_distribution = {}
    branch_distribution = {}
    nationality_distribution = {}

    for emp in employees:
        designation_distribution[emp.get("designation", "Unknown")] = \
            designation_distribution.get(emp.get("designation", "Unknown"), 0) + 1

        branch_distribution[emp.get("branch", "Unknown")] = \
            branch_distribution.get(emp.get("branch", "Unknown"), 0) + 1

        nationality_distribution[emp.get("nationality", "Unknown")] = \
            nationality_distribution.get(emp.get("nationality", "Unknown"), 0) + 1

    # =========================
    # RESPONSE
    # =========================
    return {
        "employees": employees,
        "summary": {
            "total_employees": total_employees,
            "active_employees": active_employees,
            "new_hires_year": new_hires_year,
            "new_hires_month": new_hires_month,
            "probation_employees": probation_employees,
            "iqama_expiring_next_30_days": expiring_iqama,
            "passport_expiring_this_month": passport_expiring_this_month
        },
        "distributions": {
            "gender": gender_distribution,
            "designation": designation_distribution,
            "branch": branch_distribution,
            "nationality": nationality_distribution
        },
        "status": "success",
        "last_updated": str(now())
    }


# =========================
# PAGINATED API
# =========================
@frappe.whitelist()
def get_employees(limit_start=0, page_length=10):

    employees = frappe.get_all("Employee",
        fields=[
            "name as employee_id",
            "employee_name",
            "gender",
            "designation",
            "branch",
            "custom_nationality as nationality",
            "status",
            "date_of_joining",
            "date_of_birth",
            "custom_probation_status as probation_status",
            "custom_hiring_type as hiring_type",
            "custom_contract_period as contract_period",
            "custom_contract_status as contract_status",
            "id_iqama",
            "iqama_occupation",
            "custom_expire_date as iqama_expire_date",
            "valid_upto as passport_valid_upto"
        ],
        filters={"status": "Active"},
        order_by="date_of_joining desc",
        limit_start=int(limit_start),
        limit_page_length=int(page_length)
    )

    # Convert dates to string
    for emp in employees:
        for key in [
            "date_of_joining",
            "date_of_birth",
            "iqama_expire_date",
            "passport_valid_upto"
        ]:
            if emp.get(key):
                emp[key] = str(emp[key])

    return employees
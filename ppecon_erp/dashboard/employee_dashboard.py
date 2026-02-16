import frappe
from frappe import _
from frappe.utils import today, getdate

@frappe.whitelist()
def get_hr_dashboard_data():
    """
    API endpoint to fetch HR dashboard data
    Returns employee data and analytics
    """

    employees = frappe.db.sql("""
        SELECT
            name AS employee_id,
            employee_name,
            gender,
            designation,
            branch,
            custom_nationality AS nationality,
            status,
            date_of_joining,
            date_of_birth,
            custom_probation_status AS probation_status,
            custom_hiring_type AS hiring_type,
            custom_contract_period AS contract_period,
            custom_contract_status AS contract_status,
            custom_expire_date AS iqama_expire_date,
            valid_upto AS passport_valid_upto
        FROM `tabEmployee`
        ORDER BY date_of_joining DESC
    """, as_dict=True)

    # Convert dates to string
    for emp in employees:
        if emp.get('date_of_joining'):
            emp['date_of_joining'] = str(emp['date_of_joining'])
        if emp.get('date_of_birth'):
            emp['date_of_birth'] = str(emp['date_of_birth'])
        if emp.get('iqama_expire_date'):
            emp['iqama_expire_date'] = str(emp['iqama_expire_date'])
        if emp.get('passport_valid_upto'):
            emp['passport_valid_upto'] = str(emp['passport_valid_upto'])

    total_employees = len(employees)
    active_employees = len([e for e in employees if e.get('status') == 'Active'])

    current_date = getdate(today())
    current_year = current_date.year
    current_month = current_date.month

    # New hires this year
    new_hires_year = len([
        e for e in employees
        if e.get('date_of_joining') and
        getdate(e.get('date_of_joining')).year == current_year
    ])

    # New hires this month
    new_hires_month = len([
        e for e in employees
        if e.get('date_of_joining') and
        getdate(e.get('date_of_joining')).year == current_year and
        getdate(e.get('date_of_joining')).month == current_month
    ])

    # Probation employees
    probation_employees = len([
        e for e in employees
        if e.get('probation_status') == 'Under Probation' and
        e.get('status') == 'Active'
    ])

    # Iqama Expiring in Next 30 Days
    expiring_contracts = len([
        e for e in employees
        if e.get('iqama_expire_date') and
        getdate(e.get('iqama_expire_date')) >= current_date and
        (getdate(e.get('iqama_expire_date')) - current_date).days <= 30
    ])

    # ✅ Passport Expiring This Month
    passport_expiring_this_month = len([
        e for e in employees
        if e.get('passport_valid_upto') and
        getdate(e.get('passport_valid_upto')).year == current_year and
        getdate(e.get('passport_valid_upto')).month == current_month
    ])

    # Gender Distribution
    gender_distribution = {
        'male': len([e for e in employees if e.get('gender') == 'Male']),
        'female': len([e for e in employees if e.get('gender') == 'Female']),
        'other': len([e for e in employees if e.get('gender') not in ['Male', 'Female']])
    }

    designation_distribution = {}
    branch_distribution = {}
    nationality_distribution = {}

    for emp in employees:
        if emp.get('designation'):
            designation_distribution[emp['designation']] = \
                designation_distribution.get(emp['designation'], 0) + 1

        if emp.get('branch'):
            branch_distribution[emp['branch']] = \
                branch_distribution.get(emp['branch'], 0) + 1

        if emp.get('nationality'):
            nationality_distribution[emp['nationality']] = \
                nationality_distribution.get(emp['nationality'], 0) + 1

    return {
        'employees': employees,
        'summary': {
            'total_employees': total_employees,
            'active_employees': active_employees,
            'new_hires_year': new_hires_year,
            'new_hires_month': new_hires_month,
            'probation_employees': probation_employees,
            'expiring_contracts_next_30_days': expiring_contracts,
            'passport_expiring_this_month': passport_expiring_this_month
        },
        'distributions': {
            'gender': gender_distribution,
            'designation': designation_distribution,
            'branch': branch_distribution,
            'nationality': nationality_distribution
        },
        'status': 'success',
        'last_updated': str(frappe.utils.now())
    }


@frappe.whitelist()
def get_employees(limit_start=0, page_length=10):

    employees = frappe.db.sql("""
        SELECT
            name,
            employee_name,
            gender,
            designation,
            branch,
            custom_nationality,
            status,
            date_of_joining,
            date_of_birth,
            custom_probation_status,
            custom_hiring_type,
            custom_contract_period,
            custom_contract_status,
            custom_expire_date,
            valid_upto
        FROM `tabEmployee`
        WHERE status = 'Active'
        ORDER BY date_of_joining DESC
        LIMIT %s, %s
    """, (int(limit_start), int(page_length)), as_dict=True)

    for emp in employees:
        if emp.get('date_of_joining'):
            emp['date_of_joining'] = str(emp['date_of_joining'])
        if emp.get('date_of_birth'):
            emp['date_of_birth'] = str(emp['date_of_birth'])
        if emp.get('custom_expire_date'):
            emp['custom_expire_date'] = str(emp['custom_expire_date'])
        if emp.get('valid_upto'):
            emp['valid_upto'] = str(emp['valid_upto'])

    return employees

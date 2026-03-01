import frappe
from frappe.utils import flt

@frappe.whitelist()
def get_my_leave_balance():
    # Get logged-in user
    user = frappe.session.user

    if user == "Guest":
        frappe.throw("User not logged in")

    # Get employee linked to user
    employee = frappe.get_value("Employee", {"user_id": user}, "name")

    if not employee:
        frappe.throw("Employee not linked to this user")

    # Get all submitted Leave Allocations
    allocations = frappe.get_all(
        "Leave Allocation",
        filters={
            "employee": employee,
            "docstatus": 1
        },
        fields=[
            "name",
            "leave_type",
            "total_leaves_allocated",
            "from_date",
            "to_date"
        ]
    )

    result = []

    for alloc in allocations:

        # Calculate approved leaves taken
        leaves_taken = frappe.db.sql("""
            SELECT SUM(total_leave_days)
            FROM `tabLeave Application`
            WHERE employee = %s
            AND leave_type = %s
            AND status = 'Approved'
        """, (employee, alloc.leave_type))[0][0] or 0

        leaves_taken = flt(leaves_taken)
        allocated = flt(alloc.total_leaves_allocated)
        remaining = allocated - leaves_taken

        result.append({
            "leave_type": alloc.leave_type,
            "from_date": alloc.from_date,
            "to_date": alloc.to_date,
            "allocated": allocated,
            "taken": leaves_taken,
            "remaining": remaining
        })

    return {
        "employee": employee,
        "data": result
    }
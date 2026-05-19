import frappe
from frappe import _
from frappe.utils import getdate, date_diff


# ─────────────────────────────────────────────────────────────
#  API Endpoint
#  Method : POST
#  URL    : /api/method/<app_name>.api.leave.submit_leave_from_mobile
#  Auth   : Bearer token  (Authorization: token <api_key>:<api_secret>)
#
#  Request Body (JSON or form-data):
#  {
#      "employee"              : "EMP-0001",           # required
#      "leave_type"            : "Annual Leave",        # required
#      "from_date"             : "2025-06-01",          # required  YYYY-MM-DD
#      "to_date"               : "2025-06-03",          # required  YYYY-MM-DD
#      "incharge_replacement"  : "EMP-0002",            # optional
#      "ticket"                : "Provide By Company",  # optional  see TICKET_OPTIONS
#      "exit_reentry"          : "Provide By Company",  # optional  see EXIT_REENTRY_OPTIONS
#      "description"           : "Family event"         # optional
#  }
#
#  Success Response 200:
#  {
#      "message"        : "Leave Applied Successfully",
#      "name"           : "HR-LAP-2025-00001",
#      "docstatus"      : 0,
#      "status"         : "Open",
#      "workflow_state" : "Pending Approval",
#      "leave_approver" : "jane.doe@company.com",
#      "total_days"     : 3
#  }
#
#  Error Response 4xx / 5xx:
#  { "exc_type": "ValidationError", "exception": "...", "message": "..." }
# ─────────────────────────────────────────────────────────────

# Ticket options — who covers the employee's travel ticket cost
TICKET_OPTIONS = frozenset([
    "Provide By Company",   # company pays for the flight ticket
    "Self (Employee)",      # employee pays personally
    "Not Required",         # no travel involved
])

# Exit/Re-entry visa options — Saudi Arabia requires employees to hold
# an exit/re-entry visa when leaving KSA during vacation.
# "Provide By Company" : company arranges and covers the visa
# "Self (Employee)"    : employee arranges it personally
# "Not Required"       : employee is not leaving KSA (local/domestic leave)
EXIT_REENTRY_OPTIONS = frozenset([
    "Provide By Company",
    "Self (Employee)",
    "Not Required",
])

WORKFLOW_ACTION = "Submit"   # must match the exact action name in your workflow


@frappe.whitelist()
def submit_leave_from_mobile(**kwargs):
    """
    Create a Leave Application and trigger the workflow Submit action.

    The document is saved in Draft state first (docstatus = 0), then
    apply_workflow() fires the configured workflow transition — it does NOT
    call doc.submit() directly.  The mobile client receives the resulting
    workflow_state so it can display the correct status badge.
    """

    # ── 1. Validate required fields ──────────────────────────────────────
    required = ["employee", "leave_type", "from_date", "to_date"]
    missing = [f for f in required if not kwargs.get(f)]
    if missing:
        frappe.throw(
            _("Missing required field(s): {0}").format(", ".join(missing)),
            exc=frappe.MandatoryError,
        )

    employee   = kwargs["employee"]
    leave_type = kwargs["leave_type"]
    from_date  = kwargs["from_date"]
    to_date    = kwargs["to_date"]

    # ── 2. Validate employee exists ───────────────────────────────────────
    if not frappe.db.exists("Employee", employee):
        frappe.throw(
            _("Employee '{0}' not found").format(employee),
            exc=frappe.DoesNotExistError,
        )

    # ── 3. Validate leave type exists ─────────────────────────────────────
    if not frappe.db.exists("Leave Type", leave_type):
        frappe.throw(
            _("Leave Type '{0}' not found").format(leave_type),
            exc=frappe.DoesNotExistError,
        )

    # ── 4. Validate dates ─────────────────────────────────────────────────
    try:
        from_dt = getdate(from_date)
        to_dt   = getdate(to_date)
    except Exception:
        frappe.throw(_("Invalid date format. Use YYYY-MM-DD."))

    if to_dt < from_dt:
        frappe.throw(_("'to_date' cannot be earlier than 'from_date'."))

    total_days = date_diff(to_dt, from_dt) + 1

    # ── 5. Sanitise ticket value ──────────────────────────────────────────
    # Defaults to "Not Required" if an unrecognised value is sent.
    ticket = kwargs.get("ticket")
    if ticket not in TICKET_OPTIONS:
        ticket = "Not Required"

    # ── 6. Sanitise exit/re-entry value ──────────────────────────────────
    # In Saudi Arabia, expatriate employees need an exit/re-entry visa to
    # leave the country and return.  This field records whether the company
    # provides the visa, the employee arranges it, or it is not needed
    # (e.g. the employee is taking local leave and staying inside KSA).
    # Defaults to "Not Required" if an unrecognised value is sent.
    exit_reentry = kwargs.get("exit_reentry")
    if exit_reentry not in EXIT_REENTRY_OPTIONS:
        exit_reentry = "Not Required"

    # ── 7. Resolve leave approver from Employee master ────────────────────
    leave_approver = frappe.db.get_value("Employee", employee, "leave_approver")
    if not leave_approver:
        frappe.throw(
            _("Leave Approver is not set for Employee '{0}'. "
              "Please update the Employee record before applying.").format(employee)
        )

    # ── 8. Build and insert the document (Draft / UI-Save) ────────────────
    doc = frappe.get_doc({
        "doctype"              : "Leave Application",
        "employee"             : employee,
        "leave_type"           : leave_type,
        "from_date"            : from_date,
        "to_date"              : to_date,
        "incharge_replacement" : kwargs.get("incharge_replacement"),
        "ticket"               : ticket,
        "exit_rentry"          : exit_reentry,   # fieldname in DocType kept as-is
        "description"          : kwargs.get("description"),
        "leave_approver"       : leave_approver,
    })

    doc.insert(ignore_permissions=True)

    # ── 9. Fire workflow action only (NOT doc.submit()) ───────────────────
    try:
        frappe.model.workflow.apply_workflow(doc, WORKFLOW_ACTION)
    except frappe.exceptions.WorkflowTransitionError as e:
        # Roll back the inserted doc so mobile gets a clean error
        frappe.db.rollback()
        frappe.throw(
            _("Workflow action '{0}' could not be applied: {1}").format(
                WORKFLOW_ACTION, str(e)
            )
        )

    doc.reload()

    # ── 10. Return a clean, mobile-friendly payload ───────────────────────
    return {
        "message"        : _("Leave Applied Successfully"),
        "name"           : doc.name,
        "docstatus"      : doc.docstatus,        # 0 = Draft (workflow pending)
        "status"         : doc.status,
        "workflow_state" : doc.workflow_state,   # e.g. "Pending Approval"
        "leave_approver" : doc.leave_approver,
        "total_days"     : total_days,
    }
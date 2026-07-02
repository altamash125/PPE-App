#Leave Application API with attachment support
import os
import base64

import frappe
from frappe import _
from frappe.utils import getdate, date_diff
from frappe.utils.file_manager import save_file


# ─────────────────────────────────────────────────────────────
#  API Endpoint
#  Method : POST
#  URL    : /api/method/ppecon_erp.leave_application.leave.submit_leave_from_mobile
#  Auth   : Bearer token  (Authorization: token <api_key>:<api_secret>)
# ─────────────────────────────────────────────────────────────

TICKET_OPTIONS = frozenset([
    "Provide By Company",
    "Self (Employee)",
    "Not Required",
])

EXIT_REENTRY_OPTIONS = frozenset([
    "Provide By Company",
    "Self (Employee)",
    "Not Required",
])

ALLOWED_EXTENSIONS = frozenset([".pdf", ".jpg", ".jpeg", ".png"])
MAX_FILE_SIZE_MB   = 5
WORKFLOW_ACTION    = "Submit"


@frappe.whitelist()
def submit_leave_from_mobile(**kwargs):

    # ── 1. Validate required fields ──────────────────────────────────────
    required = ["employee", "leave_type", "from_date", "to_date"]
    missing  = [f for f in required if not kwargs.get(f)]
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
    ticket = kwargs.get("ticket")
    if ticket not in TICKET_OPTIONS:
        ticket = "Not Required"

    # ── 6. Sanitise exit/re-entry value ──────────────────────────────────
    exit_reentry = kwargs.get("exit_reentry")
    if exit_reentry not in EXIT_REENTRY_OPTIONS:
        exit_reentry = "Not Required"

    # ── 7. Resolve leave approver ─────────────────────────────────────────
    leave_approver = frappe.db.get_value("Employee", employee, "leave_approver")
    if not leave_approver:
        frappe.throw(
            _("Leave Approver is not set for Employee '{0}'. "
              "Please update the Employee record before applying.").format(employee)
        )

    # ── 8. Validate attachment early (before DB insert) ───────────────────
    attachment     = kwargs.get("attachment")
    attachment_url = None

    if attachment:
        # kwargs se string aayi ho toh parse karo
        if isinstance(attachment, str):
            import json
            attachment = json.loads(attachment)
        _validate_attachment(attachment)

    # ── 9. Insert Leave Application (Draft) ──────────────────────────────
    # frappe.flags.ignore_permissions = True  →  HRMS ke validate() ke andar
    frappe.flags.ignore_permissions = True

    doc = frappe.get_doc({
        "doctype"              : "Leave Application",
        "employee"             : employee,
        "leave_type"           : leave_type,
        "from_date"            : from_date,
        "to_date"              : to_date,
        "incharge_replacement" : kwargs.get("incharge_replacement"),
        "ticket"               : ticket,
        "exit_rentry"          : exit_reentry,
        "description"          : kwargs.get("description"),
        "leave_approver"       : leave_approver,
    })

    doc.insert(ignore_permissions=True)

    frappe.flags.ignore_permissions = False   

    # ── 10. Attach file if provided ───────────────────────────────────────
    if attachment:
        attachment_url = _save_attachment(
            attachment = attachment,
            doctype    = "Leave Application",
            docname    = doc.name,
        )

    # ── 11. Fire workflow action (NOT doc.submit()) ───────────────────────
    try:
        frappe.model.workflow.apply_workflow(doc, WORKFLOW_ACTION)
    except frappe.exceptions.WorkflowTransitionError as e:
        frappe.db.rollback()
        frappe.throw(
            _("Workflow action '{0}' could not be applied: {1}").format(
                WORKFLOW_ACTION, str(e)
            )
        )

    doc.reload()

    # ── 12. Return mobile-friendly payload ───────────────────────────────
    return {
        "message"        : _("Leave Applied Successfully"),
        "name"           : doc.name,
        "docstatus"      : doc.docstatus,
        "status"         : doc.status,
        "workflow_state" : doc.workflow_state,
        "leave_approver" : doc.leave_approver,
        "total_days"     : total_days,
        "attachment_url" : attachment_url,
    }


# ── Private helpers ───────────────────────────────────────────────────────────

def _validate_attachment(attachment: dict):
    file_name = attachment.get("file_name", "").strip()
    file_data = attachment.get("file_data", "").strip()

    if not file_name:
        frappe.throw(_("attachment.file_name is required."))

    if not file_data:
        frappe.throw(_("attachment.file_data (base64) is required."))

    ext = os.path.splitext(file_name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        frappe.throw(
            _("Invalid file type '{0}'. Allowed: PDF, JPG, JPEG, PNG.").format(ext)
        )

    try:
        decoded = base64.b64decode(file_data, validate=True)
    except Exception:
        frappe.throw(_("attachment.file_data is not valid base64."))

    size_mb = len(decoded) / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        frappe.throw(
            _("File size {0:.2f} MB exceeds the maximum allowed {1} MB.").format(
                size_mb, MAX_FILE_SIZE_MB
            )
        )


def _save_attachment(attachment: dict, doctype: str, docname: str) -> str:
    file_name     = attachment["file_name"].strip()
    file_data     = attachment["file_data"].strip()
    decoded_bytes = base64.b64decode(file_data)

    file_doc = save_file(
        fname      = file_name,
        content    = decoded_bytes,
        dt         = doctype,
        dn         = docname,
        is_private = 0,
    )

    return file_doc.file_url

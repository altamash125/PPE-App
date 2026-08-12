import frappe
from frappe.utils import get_url


# ---------------------------------------------------------------- helpers

REQUIRED_2ND_PARTY = {
    "corrective_action": "Corrective Action",
    "preventive_action": "Preventive Action",
    "actions_taken": "Describe the actions taken",   # apna exact fieldname daalo
}


def _full_name(user):
    """User ID se full name, fallback email"""
    if not user:
        return ""
    return frappe.db.get_value("User", user, "full_name") or user


def _nc_url(doc):
    return f"{get_url()}/app/non-conformance/{doc.name}"


def _send(doc, recipients, subject, message=None, template=None):
    """Wrapper — mail fail ho to document save block na ho"""
    recipients = [r for r in frappe.utils.cstr(recipients).split(",") if r] \
        if isinstance(recipients, str) else [r for r in (recipients or []) if r]

    if not recipients:
        return

    try:
        kwargs = {
            "recipients": recipients,
            "subject": subject,
            "reference_doctype": doc.doctype,
            "reference_name": doc.name,
            "delayed": False,
        }
        if template:
            kwargs["template"] = template
            kwargs["args"] = {"doc": doc, "issuer": _full_name(doc.owner), "url": _nc_url(doc)}
        else:
            kwargs["message"] = message

        frappe.sendmail(**kwargs)
    except Exception:
        frappe.log_error(
            title=f"NCR mail failed: {doc.name}",
            message=frappe.get_traceback(),
        )


# ---------------------------------------------------------------- hooks

def set_issuer(doc, method=None):
    """before_insert — issuer hamesha logged-in user"""
    doc.issuer_name = _full_name(frappe.session.user)


def validate_nc_workflow(doc, method=None):
    """validate + before_update_after_submit"""

    # Apne aap ko NC issue nahi kar sakte
    if doc.issued_to and doc.issued_to == doc.owner:
        frappe.throw("You cannot issue a Non Conformance to yourself.")

    if not doc.has_value_changed("workflow_state"):
        return

    state = doc.workflow_state
    me = frappe.session.user
    is_admin = me == "Administrator"

    # --- Jon response submit kar raha hai ---
    if state == "Pending Review":
        if not is_admin and me != doc.issued_to:
            frappe.throw("Only the person this NCR is issued to can submit the response.")

        missing = [
            label for field, label in REQUIRED_2ND_PARTY.items()
            if not frappe.utils.strip_html(doc.get(field) or "").strip()
        ]
        if missing:
            frappe.throw(
                "Please fill the following before submitting your response:<br><br><b>{}</b>"
                .format("<br>".join(missing)),
                title="Incomplete Response",
            )

    # --- Altamash close ya revision bhej raha hai ---
    elif state in ("Closed", "Revision Required"):
        if not is_admin and me != doc.owner:
            frappe.throw("Only the person who raised this NCR can review or close it.")


def send_nc_review_email(doc, method=None):
    """on_update / on_change — har workflow state pe sahi banda notify ho"""

    if not doc.has_value_changed("workflow_state"):
        return

    state = doc.workflow_state
    issuer = _full_name(doc.owner)
    receiver = doc.issued_to_name or _full_name(doc.issued_to)
    url = _nc_url(doc)

    # 1. NCR issue hua → Jon ko
    if state == "Pending Response":
        _send(
            doc,
            recipients=[doc.issued_to],
            subject=f"NCR {doc.name} — Action Required: {doc.subject}",
            template="nc_review_request",
        )

    # 2. Response aaya → Altamash ko
    elif state == "Pending Review":
        _send(
            doc,
            recipients=[doc.owner],
            subject=f"NCR {doc.name} — Response Submitted by {receiver}",
            message=f"""
                <p>Dear {issuer},</p>
                <p><b>{receiver}</b> has submitted the response for NCR <b>{doc.name}</b>
                &mdash; {doc.subject}</p>
                <p>Please review the Corrective &amp; Preventive actions, then either
                <b>Close</b> the NCR or <b>Send for Revision</b>.</p>
                <p><a href="{url}"
                   style="background:#b91c1c;color:#fff;padding:10px 24px;
                          text-decoration:none;border-radius:5px;">Review NCR</a></p>
            """,
        )

    # 3. Revision maanga → Jon ko
    elif state == "Revision Required":
        _send(
            doc,
            recipients=[doc.issued_to],
            subject=f"NCR {doc.name} — Revision Required",
            message=f"""
                <p>Dear {receiver},</p>
                <p><b>{issuer}</b> has reviewed your response on NCR <b>{doc.name}</b>
                and requested a <b>revision</b>.</p>
                <p>Please update your Root Cause / Corrective / Preventive actions and resubmit.</p>
                <p><a href="{url}"
                   style="background:#b45309;color:#fff;padding:10px 24px;
                          text-decoration:none;border-radius:5px;">Update Response</a></p>
            """,
        )

    # 4. Close hua → Jon ko (cc issuer)
    elif state == "Closed":
        _send(
            doc,
            recipients=[doc.issued_to],
            subject=f"NCR {doc.name} — Closed",
            message=f"""
                <p>Dear {receiver},</p>
                <p>NCR <b>{doc.name}</b> &mdash; {doc.subject} has been reviewed and
                <b style="color:#15803d;">closed</b> by {issuer}.</p>
                <p>No further action is required. Thank you.</p>
                <p><a href="{url}"
                   style="background:#15803d;color:#fff;padding:10px 24px;
                          text-decoration:none;border-radius:5px;">View NCR</a></p>
            """,
        )
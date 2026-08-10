import frappe

def send_nc_review_email(doc, method=None):
    """NCR review email — sirf issued_to ko, jab state Pending Approval ho"""

    
    if not doc.has_value_changed("workflow_state"):
        return

    # Condition:  Pending Approval  mail
    if doc.workflow_state != "Pending Approval":
        return

    if not doc.issued_to:
        return

    frappe.sendmail(
        recipients=[doc.issued_to],          
        subject=f"NCR {doc.name} — Action Required: {doc.subject}",
        template="nc_review_request",        
        args={"doc": doc},
        reference_doctype=doc.doctype,
        reference_name=doc.name,
        delayed=False,
    )
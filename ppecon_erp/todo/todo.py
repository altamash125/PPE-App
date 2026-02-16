
import frappe

def notify_assigned_user(doc, method):
    """
    Sends email + ERPNext notification when a ToDo is assigned.
    Only triggers if 'allocated_to' changed.
    Logs debug info to Error Log for troubleshooting.
    """

    # Log debug info
    frappe.log_error(message=f"ToDo Hook Triggered: {doc.name}\nAllocated To: {doc.allocated_to}\nLast Allocated: {doc.get('__last_allocated_to')}\nMethod: {method}", 
                     title="ToDo Notification Debug")

    # Only proceed if allocated_to is set and changed
    last_allocated = doc.get("__last_allocated_to")
    if doc.allocated_to and doc.allocated_to != last_allocated:

        # Get full name of the assigner
        assigned_by_full_name = frappe.get_value("User", doc.owner, "full_name") or doc.owner

        # Priority color
        priority_colors = {"High": "#dc3545", "Medium": "#ffc107", "Low": "#198754"}
        priority_color = priority_colors.get(doc.priority, "#6c757d")

        # Status color
        status_colors = {"Open": "#0d6efd", "Working": "#fd7e14", "Completed": "#198754", "Closed": "#6c757d"}
        status_color = status_colors.get(doc.status, "#6c757d")

        # Email HTML
        email_html = f"""
        <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #333; line-height: 1.5;">
            <div style="background: #f8f9fa; padding: 20px; border-radius: 10px;">
                <h2 style="color: #0d6efd; margin-bottom: 10px;">📝 New ToDo Assigned</h2>
                <p>Hello <b>{doc.allocated_to}</b>,</p>
                <p>You have been assigned a new task in ERPNext. Here are the details:</p>
                <table style="width: 100%; border-collapse: collapse; margin-top: 15px;">
                    <tr><td style="padding: 10px; font-weight: bold;">Description</td><td style="padding: 10px;">{doc.description}</td></tr>
                    <tr><td style="padding: 10px; font-weight: bold;">Priority</td><td style="padding: 10px;"><span style='background:{priority_color};color:white;padding:3px 8px;border-radius:5px;font-weight:bold;'>{doc.priority}</span></td></tr>
                    <tr><td style="padding: 10px; font-weight: bold;">Status</td><td style="padding: 10px;"><span style='background:{status_color};color:white;padding:3px 8px;border-radius:5px;font-weight:bold;'>{doc.status}</span></td></tr>
                    <tr><td style="padding: 10px; font-weight: bold;">Assigned By</td><td style="padding: 10px;">{assigned_by_full_name}</td></tr>
                    <tr><td style="padding: 10px; font-weight: bold;">Reference Type</td><td style="padding: 10px;">{doc.reference_type or '-'}</td></tr>
                    <tr><td style="padding: 10px; font-weight: bold;">Reference Name</td><td style="padding: 10px;">{doc.reference_name or '-'}</td></tr>
                </table>
                <div style="text-align: center; margin-top: 20px;">
<a href="{frappe.utils.get_url(f'/desk#Form/ToDo/{doc.name}')}"
   style="background-color:#0d6efd;
          color:white;
          padding:10px 25px;
          text-decoration:none;
          border-radius:6px;
          font-weight:bold;
          display:inline-block;">
   View ToDo
</a>
                </div>
                <p style="margin-top: 20px; color: #6c757d; font-size: 13px;">This is an automated notification from ERPNext.</p>
            </div>
        </div>
        """

        # Send Email
        frappe.sendmail(
            recipients=[doc.allocated_to],
            subject=f"New ToDo Assigned: {doc.description}",
            message=email_html,
            reference_doctype="ToDo",
            reference_name=doc.name
        )

        # ERPNext Notification
        frappe.get_doc({
            "doctype": "Notification Log",
            "subject": f"New ToDo Assigned: {doc.description}",
            "document_type": "ToDo",
            "document_name": doc.name,
            "for_user": doc.allocated_to,
            "type": "Assignment"
        }).insert(ignore_permissions=True)

        # Log that email/notification was sent
        frappe.log_error(message=f"Notification sent for ToDo: {doc.name} to {doc.allocated_to}", title="ToDo Notification Debug")






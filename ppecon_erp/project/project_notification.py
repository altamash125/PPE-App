import frappe

def notify_design_representative(doc, method):
    # Sirf tab chale jab "YES" ho
    if doc.custom_design_representative_req_ != "YES":
        return

    if not doc.custom_assigned_to:
        return

    recipients = []
    for row in doc.custom_assigned_to:
        if row.user:
            recipients.append(row.user)

    if not recipients:
        return

    # Sirf tab bhejo jab assigned_to list ya requirement field change hui ho
    if doc.has_value_changed("custom_assigned_to") or doc.has_value_changed("custom_design_representative_req_"):
        send_project_assignment_mail(doc, recipients)


def send_project_assignment_mail(doc, recipients):
    project_link = frappe.utils.get_url_to_form("Project", doc.name)

    subject = f"Design Representative Required: {doc.project_name or doc.name}"

    message = f"""
    <div style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 620px; margin: auto; border: 1px solid #e0e0e0; border-radius: 8px; overflow: hidden;">
        <div style="background-color: #1a3c6e; padding: 20px; text-align: center;">
            <h2 style="color: #ffffff; margin: 0;">📐 Design Representative Assignment</h2>
        </div>
        <div style="padding: 25px; background-color: #ffffff;">
            <p style="font-size: 15px; color: #333;">Hi,</p>
            <p style="font-size: 15px; color: #333;">
                You have been assigned as a <b>Design Representative</b> for the following project.
                Please review the details below.
            </p>
            <table style="width: 100%; border-collapse: collapse; margin-top: 15px;">
                <tr>
                    <td style="padding: 10px; background-color: #f8f9fa; font-weight: bold; border: 1px solid #e0e0e0; width: 40%;">Project Name</td>
                    <td style="padding: 10px; border: 1px solid #e0e0e0;">{doc.project_name or "-"}</td>
                </tr>
                <tr>
                    <td style="padding: 10px; background-color: #f8f9fa; font-weight: bold; border: 1px solid #e0e0e0;">Status</td>
                    <td style="padding: 10px; border: 1px solid #e0e0e0;">
                        <span style="background-color: #d4edda; color: #155724; padding: 3px 10px; border-radius: 12px; font-size: 13px;">
                            {doc.status or "-"}
                        </span>
                    </td>
                </tr>
                <tr>
                    <td style="padding: 10px; background-color: #f8f9fa; font-weight: bold; border: 1px solid #e0e0e0;">Project Type</td>
                    <td style="padding: 10px; border: 1px solid #e0e0e0;">{doc.project_type or "-"}</td>
                </tr>
                <tr>
                    <td style="padding: 10px; background-color: #f8f9fa; font-weight: bold; border: 1px solid #e0e0e0;">Priority</td>
                    <td style="padding: 10px; border: 1px solid #e0e0e0;">{doc.priority or "-"}</td>
                </tr>
                <tr>
                    <td style="padding: 10px; background-color: #f8f9fa; font-weight: bold; border: 1px solid #e0e0e0;">Department</td>
                    <td style="padding: 10px; border: 1px solid #e0e0e0;">{doc.department or "-"}</td>
                </tr>
                <tr>
                    <td style="padding: 10px; background-color: #f8f9fa; font-weight: bold; border: 1px solid #e0e0e0;">Expected Start Date</td>
                    <td style="padding: 10px; border: 1px solid #e0e0e0;">{doc.expected_start_date or "-"}</td>
                </tr>
                <tr>
                    <td style="padding: 10px; background-color: #f8f9fa; font-weight: bold; border: 1px solid #e0e0e0;">Expected End Date</td>
                    <td style="padding: 10px; border: 1px solid #e0e0e0;">{doc.expected_end_date or "-"}</td>
                </tr>
                <tr>
                    <td style="padding: 10px; background-color: #f8f9fa; font-weight: bold; border: 1px solid #e0e0e0;">Design Rep Required</td>
                    <td style="padding: 10px; border: 1px solid #e0e0e0; color: #c0392b; font-weight: bold;">{doc.custom_design_representative_req_}</td>
                </tr>
            </table>
            <div style="text-align: center; margin-top: 25px;">
                <a href="{project_link}" style="background-color: #2c7be5; color: #ffffff; padding: 10px 25px; text-decoration: none; border-radius: 5px; font-size: 14px;">
                    View Project
                </a>
            </div>
        </div>
        <div style="background-color: #f8f9fa; padding: 12px; text-align: center; font-size: 12px; color: #888;">
            This is an automated notification from your ERP system.
        </div>
    </div>
    """

    frappe.sendmail(
        recipients=recipients,
        subject=subject,
        message=message,
        now=True
    )
import frappe
from frappe.utils import getdate, nowdate


def get_notify_emails(opp_name):
    """Fetch emails from the custom_notify_to Table MultiSelect field."""
    doc = frappe.get_doc("Opportunity", opp_name)
    rows = doc.get("custom_notify_to") or []

    if not rows:
        return []

    # child table ka jo bhi fieldname User ko link karta hai (usually 'user')
    user_field = None
    child_doctype = doc.meta.get_field("custom_notify_to").options
    for df in frappe.get_meta(child_doctype).fields:
        if df.fieldtype == "Link" and df.options == "User":
            user_field = df.fieldname
            break

    if not user_field:
        frappe.log_error(f"No User link field found in {child_doctype}", "Opportunity Notify To")
        return []

    users = [row.get(user_field) for row in rows if row.get(user_field)]
    if not users:
        return []

    emails = frappe.get_all(
        "User",
        filters={"name": ["in", users]},
        pluck="email"
    )
    return [e for e in emails if e]


def send_opportunity_followup_reminders():
    today = getdate(nowdate())

    opportunities = frappe.get_all(
        "Opportunity",
        filters={
            "custom_followup_date": today,
            "status": "Open"
        },
        fields=["name", "custom_followup_date", "status",
                "party_name", "opportunity_owner", "customer_name"]
    )

    for opp in opportunities:
        recipients = get_notify_emails(opp.name)
        if not recipients:
            continue
        send_followup_email(opp, recipients)


def notify_on_followup_set(doc, method):
    """Triggered on save — sends immediate mail when follow-up date is set/changed."""
    if doc.custom_followup_date and doc.has_value_changed("custom_followup_date"):
        recipients = get_notify_emails(doc.name)
        if recipients:
            send_followup_email(doc, recipients)


def send_followup_email(opp, recipients):
    opportunity_link = frappe.utils.get_url_to_form("Opportunity", opp.name)

    subject = f"Follow-up Reminder: {opp.name} — Due Today"

    message = f"""
    <div style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 600px; margin: auto; border: 1px solid #e0e0e0; border-radius: 8px; overflow: hidden;">
        <div style="background-color: #2c3e50; padding: 20px; text-align: center;">
            <h2 style="color: #ffffff; margin: 0;">🔔 Opportunity Follow-Up Reminder</h2>
        </div>
        <div style="padding: 25px; background-color: #ffffff;">
            <p style="font-size: 15px; color: #333;">Hi Team,</p>
            <p style="font-size: 15px; color: #333;">
                This is a reminder that the following opportunity has a <b>follow-up scheduled for today</b>.
                Please take the necessary action.
            </p>
            <table style="width: 100%; border-collapse: collapse; margin-top: 15px;">
                <tr>
                    <td style="padding: 10px; background-color: #f8f9fa; font-weight: bold; border: 1px solid #e0e0e0; width: 40%;">Opportunity</td>
                    <td style="padding: 10px; border: 1px solid #e0e0e0;">{opp.name}</td>
                </tr>
                <tr>
                    <td style="padding: 10px; background-color: #f8f9fa; font-weight: bold; border: 1px solid #e0e0e0;">Customer</td>
                    <td style="padding: 10px; border: 1px solid #e0e0e0;">{opp.customer_name or opp.party_name or "-"}</td>
                </tr>
                <tr>
                    <td style="padding: 10px; background-color: #f8f9fa; font-weight: bold; border: 1px solid #e0e0e0;">Follow-Up Date</td>
                    <td style="padding: 10px; border: 1px solid #e0e0e0; color: #c0392b; font-weight: bold;">{opp.custom_followup_date}</td>
                </tr>
                <tr>
                    <td style="padding: 10px; background-color: #f8f9fa; font-weight: bold; border: 1px solid #e0e0e0;">Status</td>
                    <td style="padding: 10px; border: 1px solid #e0e0e0;">
                        <span style="background-color: #d4edda; color: #155724; padding: 3px 10px; border-radius: 12px; font-size: 13px;">
                            {opp.status}
                        </span>
                    </td>
                </tr>
            </table>
            <div style="text-align: center; margin-top: 25px;">
                <a href="{opportunity_link}" style="background-color: #2c7be5; color: #ffffff; padding: 10px 25px; text-decoration: none; border-radius: 5px; font-size: 14px;">
                    View Opportunity
                </a>
            </div>
        </div>
        <div style="background-color: #f8f9fa; padding: 12px; text-align: center; font-size: 12px; color: #888;">
            This is an automated reminder from your ERP system.
        </div>
    </div>
    """

    frappe.sendmail(
        recipients=recipients,
        subject=subject,
        message=message,
        now=True
    )
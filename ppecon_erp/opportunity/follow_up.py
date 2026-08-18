import frappe
from frappe.utils import getdate, nowdate

def send_opportunity_followup_reminders():
    today = getdate(nowdate())

    opportunities = frappe.get_all(
        "Opportunity",
        filters={
            "custom_followup_date": today,
            "status": "Open"
        },
        fields=["name", "custom_notify_to", "custom_followup_date", "status",
                "party_name", "opportunity_owner", "customer_name"]
    )

    for opp in opportunities:
        if not opp.custom_notify_to:
            continue

        recipients = [email.strip() for email in opp.custom_notify_to.split(",") if email.strip()]

        if not recipients:
            continue

        send_followup_email(opp, recipients)


def send_followup_email(opp, recipients):
    opportunity_link = frappe.utils.get_url_to_form("Opportunity", opp.name)

    subject = f"Follow-up Reminder: {opp.name} — Due Today"

    message = f"""
    <div style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 600px; margin: auto; border: 1px solid #e0e0e0; border-radius: 8px; overflow: hidden;">
        <div style="background-color: #2c3e50; padding: 20px; text-align: center;">
            <h2 style="color: #ffffff; margin: 0;">🔔 Opportunity Follow-Up Reminder</h2>
        </div>
        <div style="padding: 25px; background-color: #ffffff;">
            <p style="font-size: 15px; color: #333;">
                Hi Team,
            </p>
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
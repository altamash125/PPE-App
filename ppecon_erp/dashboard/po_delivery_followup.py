import frappe
from frappe.utils import today, date_diff, now

def run_po_followup():
    pos = frappe.get_all("Purchase Order",
        filters={
            "docstatus": 1,
            "status": ["not in", ["Completed", "Cancelled"]]
        },
        fields=["name", "supplier", "supplier_name", "custom_delivery_status"]
    )

    for po in pos:
        try:
            doc = frappe.get_doc("Purchase Order", po.name)

            for milestone in doc.custom_po_delivery_milestones:
                if milestone.milestone_status in ["Delivered", "Overdue"]:
                    continue

                if not milestone.expected_delivery_date:
                    continue

                days_left = date_diff(milestone.expected_delivery_date, today())

                if days_left < 0:
                    milestone.milestone_status = "Overdue"
                    doc.custom_delivery_status = "Delayed"
                    doc.flags.ignore_validate_update_after_submit = True
                    doc.save(ignore_permissions=True)
                    continue

                if days_left <= 5 and not milestone.vendor_confirmed:
                    send_vendor_reminder(doc, milestone, days_left)

                if milestone.reminder_sent_date:
                    days_since = date_diff(today(), str(milestone.reminder_sent_date)[:10])
                    if days_since >= 3 and not milestone.vendor_confirmed:
                        if not doc.custom_escalation_triggered:
                            trigger_escalation(doc, milestone)

        except Exception as e:
            frappe.log_error(frappe.get_traceback(), f"PO Followup Error — {po.name}")

    frappe.db.commit()


def send_vendor_reminder(doc, milestone, days_left):
    supplier = frappe.get_doc("Supplier", doc.supplier)
    supplier_email = supplier.get("custom_supplier_email") or supplier.get("email_id")

    if not supplier_email:
        frappe.log_error(f"No email for supplier {doc.supplier}", "PO Followup")
        return

    reminder_num = (milestone.reminder_count or 0) + 1

    html = """
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;">
        <div style="background:#185FA5;padding:16px 20px;">
            <h2 style="color:#ffffff;margin:0;font-size:18px;">Delivery Reminder — {po_name}</h2>
        </div>
        <div style="padding:20px;background:#ffffff;border:1px solid #e0e0e0;">
            <p>Dear <b>{supplier_name}</b>,</p>
            <p>This is reminder <b>#{reminder_num}</b> regarding the upcoming delivery for Purchase Order <b>{po_name}</b>.</p>
            <table border="1" cellpadding="10" cellspacing="0" style="border-collapse:collapse;font-size:14px;width:100%;margin:16px 0;">
                <tr style="background:#E6F1FB;">
                    <td style="color:#185FA5;"><b>PO Number</b></td>
                    <td><b>{po_name}</b></td>
                </tr>
                <tr>
                    <td style="color:#185FA5;"><b>Milestone</b></td>
                    <td>{milestone_desc}</td>
                </tr>
                <tr style="background:#E6F1FB;">
                    <td style="color:#185FA5;"><b>Expected Delivery</b></td>
                    <td>{expected_date}</td>
                </tr>
                <tr>
                    <td style="color:#185FA5;"><b>Days Remaining</b></td>
                    <td><b style="color:{days_color};">{days_left} days</b></td>
                </tr>
                <tr style="background:#E6F1FB;">
                    <td style="color:#185FA5;"><b>Reminder No.</b></td>
                    <td>#{reminder_num}</td>
                </tr>
            </table>
            <p>Please confirm your delivery schedule by replying to this email. If there are any delays, kindly inform us immediately.</p>
            <hr style="border:none;border-top:1px solid #e0e0e0;margin:20px 0;">
            <div style="direction:rtl;text-align:right;background:#f9f9f9;padding:14px;border-radius:4px;">
                <p style="color:#444;font-size:13px;margin:0;">
                    عزيزي المورد <b>{supplier_name}</b>،<br><br>
                    هذا تذكير رقم <b>#{reminder_num}</b> بشأن موعد التسليم لأمر الشراء <b>{po_name}</b>.<br>
                    الموعد المتوقع للتسليم: <b>{expected_date}</b><br>
                    الأيام المتبقية: <b>{days_left} أيام</b><br><br>
                    يرجى تأكيد الجدول الزمني للتسليم أو إعلامنا بأي تأخير في أقرب وقت ممكن.
                </p>
            </div>
        </div>
        <div style="background:#f5f5f5;padding:10px 20px;text-align:center;">
            <p style="font-size:11px;color:#888;margin:0;">This is an automated message from ppecon ERP. Please do not reply directly.</p>
        </div>
    </div>
    """.format(
        po_name=doc.name,
        supplier_name=doc.supplier_name,
        milestone_desc=milestone.milestone_description or "—",
        expected_date=str(milestone.expected_delivery_date),
        days_left=days_left,
        days_color="#A32D2D" if days_left <= 2 else "#854F0B" if days_left <= 4 else "#185FA5",
        reminder_num=reminder_num
    )

    frappe.sendmail(
        recipients=[supplier_email],
        cc=["altamash@ppecon.com", "m.farhan@ppecon.com"],
        subject=f"Delivery Reminder #{reminder_num} — {doc.name} | Due: {milestone.expected_delivery_date}",
        message=html
    )

    milestone.reminder_count = reminder_num
    milestone.reminder_sent_date = now()
    milestone.milestone_status = "Reminded"
    doc.custom_last_reminder_sent = now()
    doc.custom_reminder_count = (doc.custom_reminder_count or 0) + 1
    doc.custom_delivery_status = "At Risk" if days_left <= 3 else "On Track"
    doc.flags.ignore_validate_update_after_submit = True
    doc.save(ignore_permissions=True)


def trigger_escalation(doc, milestone):
    html = """
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;">
        <div style="background:#A32D2D;padding:16px 20px;">
            <h2 style="color:#ffffff;margin:0;font-size:18px;">Escalation Alert — No Vendor Response</h2>
        </div>
        <div style="padding:20px;background:#ffffff;border:1px solid #e0e0e0;">
            <p>Dear Purchase Officer / Shared Services Manager,</p>
            <p>Vendor <b>{supplier_name}</b> has <b>not responded</b> to delivery reminders for the past <b>3 days</b>. Immediate action required.</p>
            <div style="background:#FCEBEB;border-left:4px solid #E24B4A;padding:16px;margin:16px 0;">
                <table border="1" cellpadding="10" cellspacing="0" style="border-collapse:collapse;font-size:14px;width:100%;">
                    <tr style="background:#f9d0d0;">
                        <td style="color:#A32D2D;"><b>PO Number</b></td>
                        <td><b>{po_name}</b></td>
                    </tr>
                    <tr>
                        <td style="color:#A32D2D;"><b>Vendor</b></td>
                        <td>{supplier_name}</td>
                    </tr>
                    <tr style="background:#f9d0d0;">
                        <td style="color:#A32D2D;"><b>Milestone</b></td>
                        <td>{milestone_desc}</td>
                    </tr>
                    <tr>
                        <td style="color:#A32D2D;"><b>Delivery Due</b></td>
                        <td>{expected_date}</td>
                    </tr>
                    <tr style="background:#f9d0d0;">
                        <td style="color:#A32D2D;"><b>Reminders Sent</b></td>
                        <td>{reminder_count}</td>
                    </tr>
                    <tr>
                        <td style="color:#A32D2D;"><b>PO Status</b></td>
                        <td>{po_status}</td>
                    </tr>
                </table>
            </div>
            <div style="background:#FAEEDA;padding:14px;border-radius:4px;">
                <b style="color:#633806;">Recommended Action:</b><br>
                <span style="color:#633806;">Call the vendor directly, escalate to supplier account manager, or issue a formal notice. Update PO status in ERPNext once resolved.</span>
            </div>
            <hr style="border:none;border-top:1px solid #e0e0e0;margin:20px 0;">
            <div style="direction:rtl;text-align:right;background:#f9f9f9;padding:14px;border-radius:4px;">
                <p style="color:#444;font-size:13px;margin:0;">
                    تنبيه تصعيد: لم يستجب المورد <b>{supplier_name}</b> خلال 3 أيام.<br>
                    أمر الشراء: <b>{po_name}</b> — يرجى اتخاذ الإجراء اللازم فوراً.
                </p>
            </div>
        </div>
        <div style="background:#f5f5f5;padding:10px 20px;text-align:center;">
            <p style="font-size:11px;color:#888;margin:0;">Automated escalation from ppecon ERP system.</p>
        </div>
    </div>
    """.format(
        po_name=doc.name,
        supplier_name=doc.supplier_name,
        milestone_desc=milestone.milestone_description or "—",
        expected_date=str(milestone.expected_delivery_date),
        reminder_count=milestone.reminder_count or 0,
        po_status=doc.custom_delivery_status or doc.status
    )

    frappe.sendmail(
        recipients=["m.farhan@ppecon.com", "altamash@ppecon.com"],
        subject=f"Escalation Alert — No response from {doc.supplier_name} ({doc.name})",
        message=html
    )

    doc.custom_escalation_triggered = 1
    doc.custom_escalation_date = now()
    doc.custom_delivery_status = "At Risk"
    doc.flags.ignore_validate_update_after_submit = True
    doc.save(ignore_permissions=True)
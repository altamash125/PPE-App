import frappe
# from frappe.utils import now_datetime,add_to_date,today
from frappe.utils import now_datetime, get_datetime, convert_utc_to_system_timezone
from datetime import timedelta


@frappe.whitelist()
def get_unread_notifications():
    """Fetch unread notifications for the logged-in user."""
    user = frappe.session.user

    # Get unread notifications for the current user
    notifications = frappe.get_all('Notification Log',
                                   filters={'read': 0, 'for_user': user},
                                   fields=['name', 'subject', 'email_content', 'document_type', 'document_name', 'creation'])

    return notifications

@frappe.whitelist()
def mark_notification_as_read(notification_name):
    """Mark the notification as read."""
    frappe.db.set_value('Notification Log', notification_name, 'read', 1)
    frappe.db.commit()
    return {'status': 'success', 'notification_name': notification_name}


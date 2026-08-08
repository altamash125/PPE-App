import frappe
from frappe.model.document import Document
from ppecon_erp.firebase_notification.firebase import send_notification


class FirebaseNotification(Document):
    def after_insert(self):
        self.send_fcm_notification()

    def send_fcm_notification(self):
        if not self.user:
            self.server_response = "No user selected"
            self.save(ignore_permissions=True)
            return

        result = send_notification(
            user=self.user,
            title=self.title,
            message=self.body
        )

        self.server_response = str(result)
        self.save(ignore_permissions=True)
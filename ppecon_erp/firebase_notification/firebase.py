import frappe
import requests
import google.auth.transport.requests
from google.oauth2 import service_account


def get_access_token():
    SERVICE_ACCOUNT_FILE = frappe.get_site_path(
        'private', 'files', 'ppecon-erp-c9058209434b.json'
    )
    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=['https://www.googleapis.com/auth/firebase.messaging']
    )
    request = google.auth.transport.requests.Request()
    credentials.refresh(request)
    return credentials.token


def send_notification(user, title, message, data=None):
    """Send FCM push to ALL devices of a user. Cleans up dead tokens."""
    devices = frappe.get_all(
        "User Device",
        filters={"user": user},
        fields=["name", "device_id"],
    )

    if not devices:
        frappe.log_error(f"No device found for user: {user}", "FCM Error")
        return {"status": "error", "message": "No device registered"}

    access_token = get_access_token()
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    # data payload: FCM requires ALL values to be strings
    data_payload = {"title": str(title), "body": str(message)}
    if data:
        for k, v in data.items():
            data_payload[str(k)] = str(v)

    results = []
    for d in devices:
        payload = {
            "message": {
                "token": d.device_id,
                "notification": {"title": title, "body": message},
                "data": data_payload,
                "android": {"notification": {"sound": "default"}},
                "apns": {"payload": {"aps": {"sound": "default"}}},
            }
        }
        try:
            response = requests.post(
                "https://fcm.googleapis.com/v1/projects/ppecon-erp/messages:send",
                json=payload, headers=headers, timeout=10,
            )
            result = response.json()
        except Exception as e:
            result = {"error": {"status": "REQUEST_FAILED", "message": str(e)}}

        results.append({"device": d.name, "result": result})

        # dead token cleanup
        err = (result.get("error") or {}).get("status")
        if err in ("UNREGISTERED", "INVALID_ARGUMENT"):
            frappe.delete_doc("User Device", d.name,
                              ignore_permissions=True, force=True)
            frappe.log_error(f"Deleted dead token device {d.name} for {user}",
                             "FCM Cleanup")

    frappe.log_error(str(results), "FCM Response")
    return results


@frappe.whitelist()
def test_notification(user, title, message):
    frappe.only_for("System Manager")   # sirf admin test kar sake
    return send_notification(user, title, message)
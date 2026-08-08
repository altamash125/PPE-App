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


def send_notification(user, title, message):
    # User ka FCM token fetch karo
    device_id = frappe.db.get_value(
        "User Device",
        {"user": user},
        "device_id"
    )

    if not device_id:
        frappe.log_error(f"No device found for user: {user}", "FCM Error")
        return {"status": "error", "message": "No device registered"}

    # Access token lo
    access_token = get_access_token()

    # V1 API payload
    payload = {
        "message": {
            "token": device_id,
            "notification": {
                "title": title,
                "body": message
            },
            "data": {
                "title": title,
                "body": message
            },
            "android": {
                "notification": {
                    "sound": "default"
                }
            },
            "apns": {
                "payload": {
                    "aps": {
                        "sound": "default"
                    }
                }
            }
        }
    }

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    response = requests.post(
        "https://fcm.googleapis.com/v1/projects/ppecon-erp/messages:send",
        json=payload,
        headers=headers
    )

    result = response.json()
    frappe.log_error(str(result), "FCM Response")
    return result


@frappe.whitelist()
def test_notification(user, title, message):
    return send_notification(user, title, message)
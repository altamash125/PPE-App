# =========================================================================
#  ppecon_erp/firebase_notification/firebase.py
#  FCM v1 push notifications  (v2 — improved)
#
#  Fixes / improvements over v1:
#  - Dead-token detection FIXED: FCM returns status NOT_FOUND with
#    errorCode UNREGISTERED in details[] — old check never matched,
#    so dead devices were never deleted.
#  - log_error() called with keyword args (title max 140 chars crash fixed)
#  - Only real failures are logged, not every successful send
#  - Access token cached ~50 min (frappe.cache) instead of a Google
#    round-trip on every notification
#  - send_to_all() broadcast + register_device() API for the mobile app
# =========================================================================
import frappe
import requests
import google.auth.transport.requests
from google.oauth2 import service_account

FCM_URL = "https://fcm.googleapis.com/v1/projects/ppecon-erp/messages:send"
TOKEN_CACHE_KEY = "fcm_access_token"


def get_access_token():
    """OAuth token for FCM, cached ~50 minutes (Google tokens last 60)."""
    cached = frappe.cache().get_value(TOKEN_CACHE_KEY)
    if cached:
        return cached

    service_account_file = frappe.get_site_path(
        "private", "files", "ppecon-erp-c9058209434b.json"
    )
    credentials = service_account.Credentials.from_service_account_file(
        service_account_file,
        scopes=["https://www.googleapis.com/auth/firebase.messaging"],
    )
    request = google.auth.transport.requests.Request()
    credentials.refresh(request)

    frappe.cache().set_value(TOKEN_CACHE_KEY, credentials.token, expires_in_sec=3000)
    return credentials.token


def _is_dead_token(result):
    """
    True when FCM says this token will never work again.
    FCM v1 puts UNREGISTERED inside error.details[].errorCode
    while error.status is NOT_FOUND — check both places.
    """
    error = result.get("error") or {}
    if error.get("status") in ("UNREGISTERED", "INVALID_ARGUMENT"):
        return True
    for detail in error.get("details") or []:
        if detail.get("errorCode") in ("UNREGISTERED", "INVALID_ARGUMENT"):
            return True
    return False


def send_notification(user, title, message, data=None):
    """Send FCM push to ALL devices of a user. Cleans up dead tokens."""
    devices = frappe.get_all(
        "User Device",
        filters={"user": user},
        fields=["name", "device_id"],
    )

    if not devices:
        # not an error worth spamming the log — most users simply
        # haven't installed the app; return quietly
        return {"status": "skipped", "message": f"No device registered for {user}"}

    try:
        access_token = get_access_token()
    except Exception:
        frappe.log_error(title="FCM Auth Failed", message=frappe.get_traceback())
        return {"status": "error", "message": "Could not get FCM access token"}

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    # FCM data payload: ALL values must be strings
    data_payload = {"title": str(title), "body": str(message)}
    if data:
        for k, v in data.items():
            data_payload[str(k)] = str(v)

    results = []
    real_failures = []

    for d in devices:
        payload = {
            "message": {
                "token": d.device_id,
                "notification": {"title": title, "body": message},
                "data": data_payload,
                "android": {
                    "priority": "high",
                    "notification": {"sound": "default"},
                },
                "apns": {"payload": {"aps": {"sound": "default"}}},
            }
        }
        try:
            response = requests.post(FCM_URL, json=payload, headers=headers, timeout=10)
            result = response.json()
        except Exception as e:
            result = {"error": {"status": "REQUEST_FAILED", "message": str(e)}}

        results.append({"device": d.name, "result": result})

        if _is_dead_token(result):
            # token expired / app uninstalled — expected, delete silently
            try:
                frappe.delete_doc("User Device", d.name,
                                  ignore_permissions=True, force=True)
            except Exception:
                pass
        elif result.get("error"):
            # a REAL failure (auth, quota, network, bad payload)
            real_failures.append({"device": d.name, "result": result})

    if real_failures:
        frappe.log_error(title="FCM Send Failures",
                         message=frappe.as_json(real_failures))

    return results


def send_to_all(title, message, data=None):
    """Broadcast to every user with a registered device (internal use)."""
    users = frappe.get_all("User Device", distinct=True, pluck="user")
    results = {}
    for user in users:
        try:
            results[user] = send_notification(user, title, message, data)
        except Exception:
            frappe.log_error(title=f"FCM Broadcast: {user}",
                             message=frappe.get_traceback())
            results[user] = {"status": "error"}
    return results


# =========================================================================
#  WHITELISTED APIs
# =========================================================================
@frappe.whitelist()
def test_notification(user, title, message):
    """Admin-only test endpoint."""
    frappe.only_for("System Manager")
    return send_notification(user, title, message)


@frappe.whitelist()
def broadcast(title, message):
    """Admin-only broadcast to everyone."""
    frappe.only_for(("System Manager", "HR Manager"))
    return send_to_all(title, message)


@frappe.whitelist()
def register_device(device_id, device_name=None):
    """
    Called by the mobile app after login / token refresh.
    Upserts the token for the logged-in user, and steals it from any
    other user (same phone, different login).
    """
    user = frappe.session.user
    if user == "Guest" or not device_id:
        frappe.throw("Not permitted")

    existing = frappe.db.get_value("User Device", {"device_id": device_id},
                                   ["name", "user"], as_dict=True)
    if existing:
        if existing.user != user:
            frappe.db.set_value("User Device", existing.name, "user", user)
        return {"status": "ok", "device": existing.name}

    doc = frappe.get_doc({
        "doctype": "User Device",
        "user": user,
        "device_id": device_id,
        "device_name": device_name or "",
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return {"status": "ok", "device": doc.name}
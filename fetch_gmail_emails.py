from google.auth.transport.requests import Request as GoogleAuthTransportRequest
import base64
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
import re

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
creds = Credentials.from_authorized_user_file('token.json')


def get_email_details(service, history_id):
    # Fetch the history
    history = service.users().history().list(
        userId="me", startHistoryId=history_id).execute()
    messages = history.get("history", [])

    if not messages:
        return None, None, None, None

    # Extract message ID
    message_id = messages[0]["messages"][0]["id"]

    # Get message details
    message = service.users().messages().get(
        userId="me", id=message_id, format="full").execute()

    # Extract sender information
    headers = message["payload"]["headers"]
    from_header = next(header["value"]
                       for header in headers if header["name"] == "From")

    # Parse sender's name and email
    match = re.match(r'(.*)<(.+)>', from_header)
    if match:
        sender_name = match.group(1).strip('" ')
        sender_email = match.group(2).strip()
    else:
        sender_name = None
        sender_email = from_header.strip()

    # Extract subject
    subject = next(header["value"]
                   for header in headers if header["name"] == "Subject")

    # Extract body
    parts = message["payload"].get("parts", [])
    body = ""

    for part in parts:
        if part["mimeType"] == "text/plain":
            body = base64.urlsafe_b64decode(
                part["body"]["data"]).decode("utf-8")
            break

    if not body and not parts:
        body = base64.urlsafe_b64decode(
            message["payload"]["body"]["data"]).decode("utf-8")

    # Truncate body if it exceeds 4096 characters
    body = truncate_string_with_ellipsis(body)

    return sender_name, sender_email, subject, body


def truncate_string_with_ellipsis(s: str, max_length: int = 4096) -> str:
    ellipsis = "..."
    if len(s) > max_length:
        # Calculate the maximum length for the truncated string
        truncated_length = max_length - len(ellipsis)
        return s[:truncated_length] + ellipsis
    return s


# service = build("gmail", "v1", credentials=creds)

# history_id = "1754371"

# sender_name, sender_email, subject, body = get_email_details(
#     service, history_id)

# print("Sender name:", sender_name)
# print("Sender email:", sender_email)

# print("Subject:", subject)
# print("Body:", body)

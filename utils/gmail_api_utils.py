from google.auth.transport.requests import Request as GoogleAuthTransportRequest
import base64
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
import re

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
creds = Credentials.from_authorized_user_file('token.json')


def get_email_details(service, history_id):
    # Fetch the history
    history = service.users().history().list(
        userId="me", startHistoryId=history_id).execute()
    messages = history.get("history", [])

    if not messages:
        return None, None, None, None, None, None

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

    body, attachments = extract_body_and_attachments(message)

    # Truncate body if it exceeds 4096 characters
    body = truncate_string_with_ellipsis(body)

    return sender_name, sender_email, subject, body, attachments, message_id


def extract_body_and_attachments(message):
    body = ""
    attachments = []

    # Check the parts of the message
    parts = message["payload"].get("parts", [])
    for part in parts:
        mime_type = part.get("mimeType")
        if mime_type == "text/plain":
            body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8")
        elif mime_type.startswith("image/") or mime_type == "application/pdf":
            # For images or other files, store them as attachments
           
            if 'attachmentId' in part['body']:
                attachment = {
                    "filename": part["filename"],
                    "mimeType": mime_type,
                    "id": part['body']['attachmentId'],
                }
                attachments.append(attachment)
    
    # If no body in parts, check the main body
    if not body and not parts:
        body = base64.urlsafe_b64decode(
            message["payload"]["body"]["data"]).decode("utf-8")

    return body, attachments


def truncate_string_with_ellipsis(s: str, max_length: int = 4096) -> str:
    ellipsis = "..."
    if len(s) > max_length:
        # Calculate the maximum length for the truncated string
        truncated_length = max_length - len(ellipsis)
        return s[:truncated_length] + ellipsis
    return s

def mark_unmark_message_as_read(service, message_id, mark_as_read: bool):
    """Mark the message as read by removing the 'UNREAD' label."""
    if mark_as_read:
        service.users().messages().modify(
            userId="me",
            id=message_id,
            body={"removeLabelIds": ["UNREAD"]}
        ).execute()

        print(f"Message with ID: {message_id} marked as read.")
    else:
        msg_labels = {'addLabelIds': ['UNREAD']}
        service.users().messages().modify(userId="me", id=message_id, body=msg_labels).execute()
        print(f"Message with ID: {message_id} marked as unread.")
        


if __name__ == "__main__":
    # mark_unmark_message_as_read(service, '193796d389183e23', False)

    service = build("gmail", "v1", credentials=creds)
    message = service.users().messages().get(userId="me", id='1937aa0b5d6837e2', format="full").execute()
    body, attachments = extract_body_and_attachments(message)
    attachment = service.users().messages().attachments().get(
                    userId='me', messageId='1937aa0b5d6837e2', id=attachments[0]['id']
                ).execute()
    # history_id = "1758602"

    # sender_name, sender_email, subject, body, attachments, message_id = get_email_details(
    #     service, history_id)

    # print("Sender name:", sender_name)
    # print("Sender email:", sender_email)

    # print("Subject:", subject)
    # print("Body:", body)
    print("Attachments:", attachment.keys())

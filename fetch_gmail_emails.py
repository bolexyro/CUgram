from google.auth.transport.requests import Request as GoogleAuthTransportRequest
import base64
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
import re

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
creds = Credentials(token="ya29.a0AeDClZB73sR68We_24lhX1WYYFRkBUaLRMdR9gdXoDAD2y1bm2mt-O4SZxhqPLewcCLwUJCmSsgoAiKlQ0R5drHLlit-AZuNXRG8yquRJJ4YAwGS_pV7lX1bIDnzPX53ZH09pxA1GpJniU3_CQ6XGJVZpCkeuXD3iwgNmZh6aCgYKAZkSARESFQHGX2MiMFWcxbbx4pOTjfBU61YE0w0175", refresh_token="1//06hMwzeE2mmmGCgYIARAAGAYSNwF-L9IrTjI_tI_SAc6lCZWzYXnAd-rjRGyH0XUtvLNffJJXUtX7XbujZvkrRC3SG5xFTgg1184",
                    token_uri="https://oauth2.googleapis.com/token", client_id="69480551867-1gn7jtlktl381i04cuuageqlo8sqm6ol.apps.googleusercontent.com", client_secret="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", granted_scopes=["https://www.googleapis.com/auth/gmail.readonly"],)


def get_email_subject_and_body(service, history_id):
    history = service.users().history().list(
        userId="me", startHistoryId=history_id).execute()
    messages = history.get("history", [])

    if not messages:
        return None, None

    # Step 2: Extract message ID
    message_id = messages[0]["messages"][0]["id"]

    # Step 3: Get message details
    message = service.users().messages().get(
        userId="me", id=message_id, format="full").execute()

    # Step 4: Extract subject
    headers = message["payload"]["headers"]
    subject = next(header["value"]
                   for header in headers if header["name"] == "Subject")

    # Step 5: Extract body
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

    body_with_links = convert_urls_to_hyperlinks(body)

    return subject, truncate_string_with_ellipsis(body_with_links)

def convert_urls_to_hyperlinks(text):
    """Convert URLs in the text to HTML-style hyperlinks."""
    # Regex to find URLs
    url_pattern = r'(https?://\S+)'
    alt_text_pattern = r'(.*?)\s?\(?https?://\S+\)?'
    
    # Replace URLs with <a> tags
    def replace_match(match):
        url = match.group(1)
        # Attempt to find alt text before the URL
        alt_match = re.search(alt_text_pattern, match.string)
        alt_text = alt_match.group(1).strip() if alt_match else url
        return f'<a href="{url}">{alt_text}</a>'

    return re.sub(url_pattern, replace_match, text)


def truncate_string_with_ellipsis(s: str, max_length: int = 4096) -> str:
    ellipsis = "..."
    if len(s) > max_length:
        # Calculate the maximum length for the truncated string
        truncated_length = max_length - len(ellipsis)
        return s[:truncated_length] + ellipsis
    return s


def get_sender_details(service, history_id):
    history = service.users().history().list(
        userId="me", startHistoryId=history_id).execute()
    messages = history.get("history", [])

    if not messages:
        return None, None

    # Step 2: Extract message ID
    message_id = messages[0]["messages"][0]["id"]

    # Step 3: Get message details
    message = service.users().messages().get(
        userId="me", id=message_id, format="full").execute()

    # Step 4: Extract "From" header
    headers = message["payload"]["headers"]
    from_header = next(header["value"]
                       for header in headers if header["name"] == "From")

    # Step 5: Parse sender's name and email
    match = re.match(r'(.*)<(.+)>', from_header)
    if match:
        name = match.group(1).strip('" ')
        email = match.group(2).strip()
    else:
        name = None
        email = from_header.strip()

    return name, email

# service = build("gmail", "v1", credentials=creds)

# history_id = "1754371"

# sender_name, sender_email = get_sender_details(service, history_id)

# print("Sender name:", sender_name)
# print("Sender email:", sender_email)

# subject, body = get_email_subject_and_body(service, history_id)

# print("Subject:", subject)
# print("Body:", body)

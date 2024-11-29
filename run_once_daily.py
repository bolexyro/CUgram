from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
import firebase_admin
from firebase_admin import credentials, firestore
import os
from dotenv import load_dotenv

load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
SERVICE_ACCOUNT_KEY_PATH = os.getenv("SERVICE_ACCOUNT_KEY_PATH")

firebase_cred = credentials.Certificate(SERVICE_ACCOUNT_KEY_PATH)
firebase_admin.initialize_app(firebase_cred)
db = firestore.client()

creds = Credentials.from_authorized_user_file("token.json", SCOPES)

# Renewing mailbox watch
# You must re-call watch at least every 7 days or else you will stop receiving updates for the user.
# We recommend calling watch once per day.
# The watch response also has an expiration field with the timestamp for the watch expiration.


def watch():
    docs = db.collection("cities").stream()
    request = {
        'labelIds': ['INBOX'],
        'topicName': 'projects/cugram-442817/topics/EmailService',
        'labelFilterBehavior': 'INCLUDE',
    }
    for doc in docs:
        doc_dict: dict = doc.to_dict()
        doc_credential = doc_dict['credential']
        creds = Credentials(
            token=doc_credential['token'],
            refresh_token=doc_credential['refresh_token'],
            token_uri=doc_credential['token_uri'],
            client_id=doc_credential['client_id'],
            client_secret=doc_credential['client_secret'],
            granted_scopes=doc_credential['granted_scopes'],
        )
        service = build("gmail", "v1", credentials=creds)

        service.users().watch(userId='me', body=request).execute()


watch()
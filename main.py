from fastapi import FastAPI, Request, status
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
import os
from dotenv import load_dotenv
import google_auth_oauthlib


load_dotenv()

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'


SECRET_KEY = os.getenv('SECRET_KEY')
CLIENT_SECRETS_FILE = "client_secret.json"
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

app = FastAPI()
print(SECRET_KEY)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)


@app.get(path='/')
def index():
    return 'welcome'


@app.get(path='/mail')
def mail_api_request(request: Request):
    if 'credentials' not in request.session:
        return RedirectResponse(request.url_for('authorize'), status_code=status.HTTP_303_SEE_OTHER)

    features: dict = request.session.get('features', {})
    if features.get('mail', False):
        return request.session.get('credentials')
    return 'Mail is not enabled'


@app.get("/authorize")
async def authorize(request: Request):
    print(request.url_for('oauth2callback'))

    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE, scopes=SCOPES)

    flow.redirect_uri = request.url_for('oauth2callback')

    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        login_hint='hint@example.com',
        prompt='consent')

    request.session['state'] = state
    return RedirectResponse(authorization_url, status_code=status.HTTP_303_SEE_OTHER)


@app.get(path='/oauth2callback')
def oauth2callback(request: Request):
    state = request.session.get('state', "No state set")
    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(CLIENT_SECRETS_FILE,
                                                                   scopes=SCOPES, state=state)

    flow.redirect_uri = request.url_for('oauth2callback')
    authorization_response = str(request.url)
    flow.fetch_token(authorization_response=authorization_response)

    # Store the credentials in the session.
    # ACTION ITEM for developers:
    #     Store user's access and refresh tokens in your data store if
    #     incorporating this code into your real app.
    credentials = flow.credentials
    credentials = {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'granted_scopes': credentials.granted_scopes}
    request.session['credentials'] = credentials
    features = check_granted_scopes(credentials)
    request.session['features'] = features
    return RedirectResponse('/', status_code=status.HTTP_303_SEE_OTHER)


def check_granted_scopes(credentials):
    features = {}
    if 'https://www.googleapis.com/auth/gmail.readonly' in credentials['granted_scopes']:
        features['mail'] = True
    else:
        features['drive'] = False
    return features

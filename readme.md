# Project Setup Instructions

## 1. Get Bot Tokens
Obtain **two** Telegram bot tokens from [BotFather](https://t.me/BotFather):
- One for the **Student Bot**
- One for the **DSA Bot**

## 2. Set Up Firebase
- Create a new project on [Firebase Console](https://console.firebase.google.com/)
- Create a **Firestore Database** in the project
- Navigate to **Project Settings > Service accounts**, and click **"Generate new private key"**
- Save the downloaded file as `service-account-key.json`

## 3. Set Up Google OAuth
- Go to [Google Cloud Console](https://console.cloud.google.com/)
- Create a new project (or use an existing one)
- Navigate to **APIs & Services > OAuth consent screen**
  - Set up the consent screen
- Navigate to **Credentials**, and create an **OAuth 2.0 Client ID**
- Download the `client_secret.json` file

## 4. Create a `.env` File
Create a `.env` file in your project root with the following content (replace placeholders with actual values):

```env
CLIENT_SECRETS_PATH=<path to client_secret.json>
SERVICE_ACCOUNT_KEY_PATH=<path to service-account-key.json>
FASTAPI_SESSION_SECRET_KEY=<secret key for your session>
JWT_SIGNING_SECRET_KEY=<jwt signing key>
DSA_BOT_TOKEN=<token gotten from bot father for the dsa bot>
STUDENT_BOT_TOKEN=<token gottten from bot father for the student bot>
SERVER_URL_BASE=https://lively-helpful-monarch.ngrok-free.app
OFFICIAL_EMAILS=["odufuwa.adebola@stu.cu.edu.ng","dsa@cu.edu.ng","seald@covenantuniversity.edu.ng"]
SCOPES=["https://www.googleapis.com/auth/userinfo.email","openid","https://www.googleapis.com/auth/userinfo.profile"]
```
## 🔧 Project Setup

Follow the steps below to set up the project locally:

```bash
# Clone the repository
git clone https://github.com/bolexyro/CUgram.git
```

```bash
# Navigate into the project directory
cd Cugram
```

```bash
# Create a virtual environment
python -m venv .venv
```

```bash
# Activate the virtual environment
# On Windows
. .venv/Scripts/activate
```

```bash
# On macOS/Linux
source .venv/bin/activate
```

```bash
# Install the required dependencies
pip install -r requirements.txt
```

```bash
# Start the FastAPI development server
fastapi dev
```
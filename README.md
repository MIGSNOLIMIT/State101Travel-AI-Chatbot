# State101Travel-AI-Chatbot

An AI-powered Streamlit app for State101 Travel that:

- Answers US/Canada visa questions using Groq.
- Collects applicant details via an Application Form.
- Requires at least 2 uploaded files under “Upload your Requirements.”
- On submit, performs three backups in parallel:
	1) Sends an email with all form details and the uploaded files as attachments.
	2) Appends a row to a Google Sheet.
	3) Creates a subfolder in Google Drive with a text file of the form data and all uploaded files.

Live app: state101-aichatbot.streamlit.app

## Prerequisites

- Windows 10/11 with PowerShell.
- Python 3.10–3.12 recommended (other versions may work, but 3.14 can be too new for some libs).
- A Gmail account with an App Password (for SMTP). Two‑Step Verification must be enabled on the account.
- A Google Cloud project with a Service Account that has Drive and Sheets API enabled.

## Quickstart (PowerShell)

```powershell
# 1) Clone and open the folder
cd "D:\Github Cloned Repo\State101Travel-AI-Chatbot"

# 2) Create and activate a virtual environment
python -m venv .venv
. .\.venv\Scripts\Activate.ps1
# If activation is blocked, run once:
# Set-ExecutionPolicy -Scope CurrentUser RemoteSigned -Force

# 3) Install dependencies
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

# 4) Run the app
python -m streamlit run app.py
```

Then open http://localhost:8501 in your browser.

## Configure secrets

Create a file at `./.streamlit/secrets.toml` with the following keys. Do not commit this file.

```toml
# Groq
GROQ_API_KEY = "your_groq_api_key"

# Google Service Account JSON (copy the JSON fields here)
[GCP_SERVICE_ACCOUNT]
type = "service_account"
project_id = "your_project_id"
private_key_id = "..."
private_key = """-----BEGIN PRIVATE KEY-----
...your private key...
-----END PRIVATE KEY-----"""
client_email = "your-service-account@your-project.iam.gserviceaccount.com"
client_id = "..."
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "https://www.googleapis.com/robot/v1/metadata/x509/your%40serviceaccount"
universe_domain = "googleapis.com"

# Email (SMTP)
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465        # 465 = implicit SSL; use 587 for STARTTLS
SMTP_USER = "your_gmail@gmail.com"
SMTP_PASS = "your_gmail_app_password"  # App Password, not your normal password
FROM_EMAIL = "your_gmail@gmail.com"
MAIL_TO = "destination_inbox@example.com"  # Where submissions are sent

# Google Drive backup
# Share the parent folder with the service account client_email as Editor/Manager
DRIVE_PARENT_FOLDER_ID = "your_drive_parent_folder_id"
```

### Where to find DRIVE_PARENT_FOLDER_ID

- Open your parent folder in Google Drive and copy the ID from the URL.
- Example: https://drive.google.com/drive/folders/123qx... → ID is `123qx...`.
- The app creates a subfolder per submission: `YYYYMMDD-HHMM - Full Name`.

### Google Sheets setup

- Create a spreadsheet named `state101application` in Google Sheets.
- Share it with your service account’s `client_email` from secrets.
- Each submission appends a row with: Full Name, Email, Phone, Age, Address, Visa Type, Preferred Day, Available Time, Timestamp, DriveFolderLink.

## What happens on Submit

Validation:
- Required fields: Full Name, Email, Phone, Age, Address, Visa Type, Preferred Day, Available Time.
- Phone validation: Philippine format `09XXXXXXXXX` (11 digits).
- File uploads: at least 2 files are required.

Actions:
- Email: Sends the form details and attaches all uploaded files.
- Google Sheet: Appends a new row with the submission and Drive folder link.
- Google Drive: Creates a new subfolder under the configured parent folder, saves `application.txt` with the form details, and uploads all files.

If one action fails (e.g., email), the others can still succeed. The UI will tell the user which steps succeeded/failed so nothing is silently lost.

## Troubleshooting

- `pip is not recognized`
	- Use `python -m pip ...` instead.

- Activation script blocked in PowerShell
	- Run: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned -Force`

- `No secrets found` in Streamlit
	- Ensure `.streamlit/secrets.toml` exists and is spelled exactly `secrets.toml`.

- SMTP 535 or auth errors
	- Use a Gmail App Password (requires 2‑Step Verification). Confirm correct `SMTP_PORT` (465 or 587).

- `googleapiclient` not found
	- Re‑install requirements: `python -m pip install -r requirements.txt`.

- Google Sheets 403 / not found
	- Ensure spreadsheet `state101application` exists and is shared with the service account `client_email`.

- Google Drive 403 / cannot create folder
	- Share the parent folder with the service account as Editor, or use a Shared Drive with proper permissions.

- Upload too large for email
	- Gmail limits total message size (~25MB). Drive backup will still work. Consider restricting file types/sizes if needed.

## Customization

- Restrict file types: we can limit uploads (e.g., `pdf`, `jpg`, `png`, `docx`).
- Confirmation email: CC/BCC a copy to the applicant.
- Save `application.json` in Drive instead of (or in addition to) `application.txt`.

## Deployment notes

- Streamlit Community Cloud: put the values in the app’s “Secrets” (not in the repo). The same keys in this README apply.
- Self‑hosting: keep `.streamlit/secrets.toml` out of version control.

---

Questions or errors? Share the console output from PowerShell and I’ll help debug.

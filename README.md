# State101 Travel — Visa Assistant (Streamlit)

A branded Streamlit app that answers State101 Travel’s US/Canada visa inquiries and collects initial assessment submissions. It’s code‑grounded (no hallucinated facts), branded with your logo, and backs up each submission to Email, Google Sheets, and Google Drive.

---

## What it does

- Chat assistant (code‑first answers)
  - Returns hardcoded, canonical info for: location/map/TikTok link, hours, contact, services, legitimacy, program details, visa type, qualifications, age/gender/graduates, requirements, appointment, status, price/fees guidance.
  - Covers natural phrasing via synonyms and a fuzzy matcher (e.g., “steps,” “procedure,” “timeline,” “how to apply,” “cost/charges/pricing,” etc.).
  - If phrasing is still unknown, a facts‑backed LLM fallback replies using a compact FACTS snapshot generated from this code. It selects the closest relevant fact or provides official contact + a form hint—never inventing branches or prices.

- Application form (with validation)
  - Fields: Full name, Email, Phone (PH 11‑digit 09xxxxxxxxx), Age (1–120), Complete address, Visa type, Preferred day (Mon–Sun), Available time, and file uploads (min 2 files).
  - Submission flow:
    1) Google Drive: creates “YYYYMMDD‑HHMM – Full Name” subfolder; uploads application.txt + all uploaded files.
    2) Email: sends all details + attachments; includes Drive folder link when available.
    3) Google Sheets: appends a row including the Drive link.
  - End‑user messages are simple (“Application submitted!”); dev diagnostics are available behind a flag.

- Branding & UX
  - Uses images/state101-logo.png as page favicon and header logo.
  - Theme toggle (Light/Dark); radio labels styled with State101 dark‑blue gradient.
  - Terms & Conditions gate shown on first load.

---

## How answers are produced (routing pipeline)

1) Normalize input (lowercase, punctuation stripped; language detection for non‑EN).
2) Intent match (strict, no LLM): maps rich synonym lists to hardcoded responses.
3) Fuzzy match (still no LLM): lightweight keyword overlap picks the nearest intent for unusual phrasing.
4) Facts‑backed LLM fallback (controlled):
   - Model: Groq llama‑3.3‑70b‑versatile.
   - Receives only a small FACTS object (address/map/TikTok, hours, phones, email, services, legitimacy, program details, qualifications, policies, price note, requirements, contact block).
   - Must use only FACTS; if a detail is not explicit, it uses the closest relevant item or returns the official contact block + form hint (never “not available”).
5) Output guardrails:
   - Location sanitizer triggers only for true location intent.
   - Contact/location strings are forced to canonical values.
6) Off‑topic guard:
   - Polite policy message if the question isn’t about State101 Travel visa services.

Feature flags (in secrets.toml):
- STRICT_MODE=true (default) — Known intents never use the LLM.
- SMART_FACTS_MODE=true (default) — Facts‑backed fallback enabled.
- DEBUG_SUBMISSION=false (default) — When true, show a Diagnostics expander after form submission.

---

## Requirements

- Windows 10/11 with PowerShell
- Python 3.12.x
- Google Cloud service account (JSON content placed in secrets)
- Drive API and Sheets API enabled on that GCP project
- A Google Sheet named state101application shared with the service account
- A Google Drive parent folder shared with the service account (Editor)
- Gmail App Password for SMTP (2‑Step Verification required)

---

## Setup

1) Create and activate a virtual environment (Windows PowerShell)
```powershell
cd "D:\Github Cloned Repo\State101Travel-AI-Chatbot"
py -3.12 -m venv .venv
. .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

2) Place your logo
- Save your round logo as images/state101-logo.png (transparent PNG recommended).

3) Configure secrets (.streamlit/secrets.toml)
- Keep these keys at the TOP LEVEL (not inside [GCP_SERVICE_ACCOUNT]).
- Quote strings; booleans are true/false without quotes.
```toml
# === LLM ===
GROQ_API_KEY = "your_groq_key"

# === Email (Gmail SMTP App Password) ===
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465               # 465 (SSL) or 587 (STARTTLS)
SMTP_USER = "yourgmail@gmail.com"
SMTP_PASS = "your_gmail_app_password"
FROM_EMAIL = "yourgmail@gmail.com"
MAIL_TO = "destination@example.com"

# === Google Drive backup ===
DRIVE_PARENT_FOLDER_ID = "your_drive_folder_id"

# === Feature toggles ===
STRICT_MODE = true
SMART_FACTS_MODE = true
DEBUG_SUBMISSION = false

# === Google Service Account ===
[GCP_SERVICE_ACCOUNT]
type = "service_account"
project_id = "your_project_id"
private_key_id = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
private_key = """-----BEGIN PRIVATE KEY-----
...key...
-----END PRIVATE KEY-----"""
client_email = "your-sa@your-project.iam.gserviceaccount.com"
client_id = "1234567890"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "https://www.googleapis.com/robot/v1/metadata/x509/your-sa%40your-project.iam.gserviceaccount.com"
```

Notes:
- Share the Drive parent folder and the state101application Google Sheet with the service account email as Editor.
- To get DRIVE_PARENT_FOLDER_ID: open the Drive folder and copy the ID from the URL.

4) Run
```powershell
python -m streamlit run app.py
```

---

## Where things live (for developers)

- Hardcoded facts: HARDCODED_RESPONSES in app.py
- Intent synonyms and routing: VisaAssistant.intent_synonyms, match_intent(), fuzzy_fact_match()
- Facts snapshot for fallback: VisaAssistant.pack_facts()
- Email: send_application_email()
- Drive backup: upload_to_drive()
- Sheets backup: save_to_sheet()
- UI tabs and form: show_application_form(), show_requirements(), main()
- Theme & CSS: apply_theme()
- Logo/Favicon: images/state101-logo.png (used in st.set_page_config and header)

---

## Troubleshooting

- No module named streamlit
  - Activate the venv and install requirements:
    - . .\.venv\Scripts\Activate.ps1
    - python -m pip install -r requirements.txt

- TOML parsing error (“Invalid date or number”)
  - All strings must be quoted.
  - Booleans (true/false) must not be quoted.
  - SMTP_* and DRIVE_PARENT_FOLDER_ID must be top‑level (not under [GCP_SERVICE_ACCOUNT]).

- Email fails
  - Use a Gmail App Password (not your account password).
  - Total attachment size must be under ~25 MB.
  - The app auto‑fallbacks between ports 465 and 587 if one fails.

- Drive fails
  - Ensure Drive API is enabled.
  - Confirm DRIVE_PARENT_FOLDER_ID from the URL.
  - Share the parent folder with the service account as Editor.
  - App uses supportsAllDrives=True.

- Sheets fails
  - Sheet named exactly state101application with Sheet1 present.
  - Shared with the service account.

- Diagnostics
  - Set DEBUG_SUBMISSION=true to show a “Diagnostics (for developers)” expander after submit.

---

## Security & data notes

- Terms & Conditions gate appears before app use.
- Data is sent via email and uploaded to a Drive folder you control; a row is added to a Google Sheet for tracking.
- The chatbot does not expose secrets and is hardened against prompt injection for core facts (no invented branches or contacts).

---

## Tech stack

- Streamlit, Python 3.12
- Groq LLM (llama‑3.3‑70b‑versatile)
- Google APIs: Drive v3, Sheets (gspread)
- SMTP (Gmail) for email
- langdetect + deep_translator for multilingual input handling
- tenacity/ratelimit for stability

---

## License

MIT (or your preferred license)

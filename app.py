import streamlit as st
import time
import re
import gspread
from groq import Groq
from tenacity import retry, stop_after_attempt, wait_exponential
from google.oauth2.service_account import Credentials
from ratelimit import limits, sleep_and_retry
from pathlib import Path
from langdetect import detect
from deep_translator import GoogleTranslator
import smtplib
from email.message import EmailMessage
import mimetypes
import ssl
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io
from datetime import datetime

# ========== SYSTEM PROMPT ==========
SYSTEM_PROMPT = """You are the State101 Chatbot, the official AI assistant for State101Travel specializing in US/Canada visa assistance. Your role is to:

1. **Information Provider**:
   - Clearly explain Canadian Visa  and American visa processes
   - Provide hardcoded requirements when asked
   - Share business hours (Mon-Sat 9AM-5PM), location, and contact details

2. **Form Collector**:
   - Direct users to complete the application form with these fields:
     *Full Name, Email, Phone, Age, Address, Visa Type (Canadian/American), Available Time*

3. **Response Rules**:
   - For requirements/questions in HARDCODED_RESPONSES, use ONLY those exact answers
   - For complex queries (case-specific, application status, urgent matters):
     "🔍 For detailed advice, please contact us directly:
      📞 +63 905-804-4426 or +63 969-251-0672
      📧 state101ortigasbranch@gmail.com
      ⏰ Mon-Sat 9AM-5PM"

4. **Key Talking Points**:
   - Always emphasize: "We recommend an appointment before walking in."

5. **Style Guide**:
   - Use bullet points for requirements
   - Include emojis for readability (🛂 ✈️ 📝)
   - Never speculate - defer to official contacts when uncertain

6. **Data Handling**:
   - Remind users: "Your information is secure and will only be used for visa assessment"

7. **Error Handling**:
   - If unsure: "I specialize in visa assistance. For this question, please contact our specialists during business hours."
8. **Be Very Informative always use the hardcoded response for information basis to especially the location and other informations like numbers and also for location send this 
google map link: https://maps.app.goo.gl/o2rvHLBcUZhpDJfp8 ."
 
9. Strict Answer Policy (additive, do not override earlier rules):
    - Always use HARDCODED_RESPONSES first for factual queries (location/address/map, contact/phones/email, hours, services, legitimacy, program details, qualifications, age, gender, graduates, requirements, appointment, status, price).
    - For questions that are "fees related" or "process related", reply exactly: "All the details about our program will be discussed during the initial briefing and assessment at our office".
    - When providing the office location, include BOTH the Google Maps link and the TikTok location guide link from the hardcoded responses.
    - Never invent or rename branches/locations. Use exactly the strings in the hardcoded responses.
    - If requested information is not present in HARDCODED_RESPONSES, reply that the information isn't available and direct the user to contact via the official phones/email or submit the Application Form.
"""

# ========== HARDCODED RESPONSES ==========
HARDCODED_RESPONSES = {
"requirements": """🛂 **Visa Requirements**:\n- Valid passport (Photocopy)\n- 2x2 photo (white background)\n- Training Certificate(if available)\n- Diploma(Photocopy if available)\n- Updated Resume""",
    "appointment": "⏰ Strictly by appointment only. Please submit the application form first.",
    
    "hours": "🕘 Open Mon-Sat 9AM-5PM",
    "opportunities": "💼 B1 Visa Includes 6-month care-giving training program with our Partner homecare facilities in US.",
    "business hours": "🕘 We're open Monday to Saturday, 9:00 AM to 5:00 PM.",
    "located": "📍 2F Unit 223, One Oasis Hub B, Ortigas Ext, Pasig City\n\n🗺️ Find us here: https://maps.app.goo.gl/o2rvHLBcUZhpDJfp8\n\n🎥 Location guide video: https://vt.tiktok.com/ZSyuUpdN6/",
    "map": "📍 2F Unit 223, One Oasis Hub B, Ortigas Ext, Pasig City\n\n🗺️ Find us here: https://maps.app.goo.gl/o2rvHLBcUZhpDJfp8\n\n🎥 Location guide video: https://vt.tiktok.com/ZSyuUpdN6/",
    "location": "📍 2F Unit 223, One Oasis Hub B, Ortigas Ext, Pasig City\n\n🗺️ Find us here: https://maps.app.goo.gl/o2rvHLBcUZhpDJfp8\n\n🎥 Location guide video: https://vt.tiktok.com/ZSyuUpdN6/",
    "processing time": "⏳ Standard processing takes 2-4 weeks. Expedited services may be available.",
    "complex": "🔍 For case-specific advice, please contact our specialists directly:\n📞 0961 084 2538\n📧 state101ortigasbranch@gmail.com",
    "status": "🔄 For application status updates, please email us with your reference number.",
    "urgent": "⏰ For urgent concerns, call us at +63 905-804-4426 or +63 969-251-0672 during business hours.",
    "how much": "💰 For pricing information, please proceed to the Application Form for Initial Assessment and expect a phone call within 24 hours.\n\n📞 You may also contact us directly:\n+63 905-804-4426 or +63 969-251-0672\n📧 state101ortigasbranch@gmail.com\n⏰ Mon-Sat 9AM-5PM",
    "price": "💰 For pricing information, please proceed to the Application Form for Initial Assessment and expect a phone call within 24 hours.\n\n📞 You may also contact us directly:\n+63 905-804-4426 or +63 969-251-0672\n📧 state101ortigasbranch@gmail.com\n⏰ Mon-Sat 9AM-5PM",
    "cost": "💰 For pricing information, please proceed to the Application Form for Initial Assessment and expect a phone call within 24 hours.\n\n📞 You may also contact us directly:\n+63 905-804-4426 or +63 969-251-0672\n📧 state101ortigasbranch@gmail.com\n⏰ Mon-Sat 9AM-5PM",
    "fee": "💰 For pricing information, please proceed to the Application Form for Initial Assessment and expect a phone call within 24 hours.\n\n📞 You may also contact us directly:\n+63 905-804-4426 or +63 969-251-0672\n📧 state101ortigasbranch@gmail.com\n⏰ Mon-Sat 9AM-5PM",
    "payment": "💳 For payment options and pricing details, please contact us directly:\n\n📞 +63 905-804-4426 or +63 969-251-0672\n📧 state101ortigasbranch@gmail.com\n⏰ Mon-Sat 9AM-5PM\n\n✅ Services are by appointment only. Please complete the Application Form for initial assessment.",
    "payment options": "💳 For payment options and pricing details, please contact us directly:\n\n📞 +63 905-804-4426 or +63 969-251-0672\n📧 state101ortigasbranch@gmail.com\n⏰ Mon-Sat 9AM-5PM\n\n✅ Services are by appointment only. Please complete the Application Form for initial assessment.",
    "pay": "💳 For payment options and pricing details, please contact us directly:\n\n📞 +63 905-804-4426 or +63 969-251-0672\n📧 state101ortigasbranch@gmail.com\n⏰ Mon-Sat 9AM-5PM\n\n✅ Services are by appointment only. Please complete the Application Form for initial assessment.",
    "legit": "✅ Yes, our company is 100% legitimate. We’re officially registered and have a permit to operate issued by the Municipality of Pasig.",
    
    # === FAQs added per request ===
    # Services
    "services": "🛂 We provide full assistance with US visa applications and processing.",
    "what services do you offer": "🛂 We provide full assistance with US visa applications and processing.",
    
    # Other countries
    "other countries": "🌍 We currently don’t offer visa assistance for other countries. Our services are focused on US visa processing.",
    "do you also offer visas to other countries": "🌍 We currently don’t offer visa assistance for other countries. Our services are focused on US visa processing.",
    
    # Legitimacy (extra trigger)
    "is your company legit": "✅ Yes, our company is 100% legitimate. We’re officially registered and have a permit to operate issued by the Municipality of Pasig.",
    
    # Program details
    "program details": "📝 All the details about our program will be discussed during the initial briefing and assessment at our office.",
    "details of your program": "📝 All the details about our program will be discussed during the initial briefing and assessment at our office.",
    
    # Visa type offered
    "visa type": "🛂 We offer the B1 Non-Immigrant Visa.",
    "what type of visa you offer": "🛂 We offer the B1 Non-Immigrant Visa.",
    
    # Qualifications
    "qualifications": "✅ Open to applicants with or without prior training or experience. Applicants must be willing to undergo training and develop the necessary skills for the program.",
    
    # Age
    "age limit": "👥 There is no strict age limit, provided the applicant is physically capable of performing the required tasks.",
    
    # Gender
    "is there genders required": "⚧ Open to all genders.",
    "gender": "⚧ Open to all genders.",
    
    # Graduates
    "does it accept graduates only": "🎓 Accepts both graduates and undergraduates.",
    "graduates": "🎓 Accepts both graduates and undergraduates.",
    
    # Fees / Process related
    "fees related": "📝 All the details about our program will be discussed during the initial briefing and assessment at our office.",
    "process related": "📝 All the details about our program will be discussed during the initial briefing and assessment at our office.",
    
}

# ========== COLOR THEMES ==========
COLOR_THEMES = {
    "White": {
        "primary": "#FFFFFF",
        "secondary": "#F5F5F5",
        "text": "#000000",
        "text_secondary": "#444444",
        "accent": "#DC143C",  # Crimson Red
        "button": "#DC143C",
        "icon": "🌙"  # Moon icon for light mode
    },
    "Black": {
        "primary": "#121212",
        "secondary": "#1E1E1E",
        "text": "#FFFFFF",
        "text_secondary": "#B0B0B0",
        "accent": "#00BFFF",  # Electric Blue
        "button": "#00BFFF",
        "icon": "☀️"  # Sun icon for dark mode
    }
}

# ========== LLM WRAPPER ==========
# ========== LLM WRAPPER WITH RELEVANCE CHECK ==========
class VisaAssistant:
    def __init__(self):
        self.client = Groq(api_key=st.secrets["GROQ_API_KEY"])
        self.daily_count = 0
        self.last_call = 0
        # Strict mode ensures canonical info comes only from hardcoded data
        self.strict_mode = bool(st.secrets.get("STRICT_MODE", True))
        # Facts-backed fallback mode: when true, LLM receives canonical facts and must answer using them only
        self.smart_facts_mode = bool(st.secrets.get("SMART_FACTS_MODE", True))
        
        # Define topics that are considered relevant to State101 Travel
        self.relevant_keywords = [
            "visa", "travel", "passport", "appointment", "requirements", 
            "canada", "canadian", "america", "american", "us", "usa",
            "application", "processing", "state101", "state 101",
            "consultation", "documentation", "embassy", "interview",
            "tourist", "business", "student", "work permit", "immigration",
            "fee", "cost", "price", "hours", "location", "contact",
            "eligibility", "qualification", "denial", "approval",
            "urgent", "status", "track", "form", "apply", "b1"
        ]
        
        # Define off-topic keywords that should trigger immediate rejection
        self.offtopic_keywords = [
            "calculator", "code", "program", "recipe", "cook", "game",
            "movie", "song", "weather", "sports", "stock", "crypto",
            "math", "solve", "equation", "homework", "essay", "write a story"
        ]

        # Intent synonyms mapped to canonical intents
        self.intent_synonyms = {
            "location": [
                "where are you", "where are you located", "where is your office",
                "office address", "address", "location", "map", "directions",
                "find you", "tiktok", "tiktok location", "tiktok video", "google map"
            ],
            "hours": ["hours", "opening hours", "business hours", "schedule", "open time", "what time"],
            "contact": ["contact", "phone", "phone number", "call you", "email", "email address"],
            "services": ["services", "what services", "services do you offer"],
            "legit": ["legit", "legitimacy", "is your company legit"],
            "program details": ["program details", "details of your program", "details of program"],
            "visa type": ["visa type", "what type of visa", "what type of visa you offer"],
            "qualifications": ["qualifications", "qualification"],
            "age limit": ["age", "age limit"],
            "gender": ["gender", "genders required"],
            "graduates": ["graduates", "undergraduate", "does it accept graduates only"],
            "requirements": ["requirements", "documents", "needed documents"],
            "appointment": ["appointment", "book", "schedule appointment"],
            "status": ["status", "application status"],
            "price": ["price", "cost", "fee", "how much", "payment", "payment options", "pay"],
            "program details": [
                "program details", "details of your program", "details of program",
                "fees related", "process related",
                "visa application process", "application process", "process",
                "how does visa application process work", "how does the process work",
                "how does your process work", "steps", "procedure", "flow", "timeline", "how to apply"
            ],
        }

    def _normalize(self, text: str) -> str:
        return re.sub(r'[^\w\s]', '', text.lower()).strip()

    def match_intent(self, prompt: str) -> str | None:
        norm = self._normalize(prompt)
        for key, synonyms in self.intent_synonyms.items():
            for s in synonyms:
                if s in norm:
                    return key
        return None

    def get_canonical_response(self, intent: str) -> str | None:
        # Direct retrieval if a matching key exists
        if intent in HARDCODED_RESPONSES:
            return HARDCODED_RESPONSES[intent]
        # Map some intents to underlying keys
        mapping = {
            "location": "location",
            "hours": "hours",
            "contact": "urgent",  # contains official phone numbers and email
            "services": "services",
            "legit": "legit",
            "program details": "program details",
            "visa type": "visa type",
            "qualifications": "qualifications",
            "age limit": "age limit",
            "gender": "gender",
            "graduates": "graduates",
            "requirements": "requirements",
            "appointment": "appointment",
            "status": "status",
            "price": "price",
        }
        key = mapping.get(intent)
        if key and key in HARDCODED_RESPONSES:
            return HARDCODED_RESPONSES[key]
        return None

    def pack_facts(self) -> dict:
        """Build a compact facts dictionary from hardcoded responses.
        These are the only allowed canonical values the LLM may use in fallback."""
        def first_url(text: str) -> str | None:
            m = re.search(r"https?://\S+", text or "")
            return m.group(0) if m else None

        # Address line (no links)
        address_line = HARDCODED_RESPONSES.get("located") or ""
        # Location block contains address + links
        location_block = HARDCODED_RESPONSES.get("location") or address_line
        map_url = first_url(HARDCODED_RESPONSES.get("map", "")) or first_url(location_block) or ""
        # Extract TikTok link if present
        tiktok_url = None
        for url_match in re.findall(r"https?://\S+", location_block):
            if "tiktok.com" in url_match:
                tiktok_url = url_match
                break

        # Extract phones and email from 'urgent' block (contains official numbers and email)
        urgent = HARDCODED_RESPONSES.get("urgent", "")
        phones = re.findall(r"\+?\d[\d\s-]{7,}\d", urgent)
        email_match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", urgent)
        email_addr = email_match.group(0) if email_match else ""

        facts = {
            "address": address_line,
            "location_block": location_block,
            "map_url": map_url,
            "tiktok_url": tiktok_url or "",
            "hours": HARDCODED_RESPONSES.get("hours", ""),
            "phones": phones,
            "email": email_addr,
            "services": HARDCODED_RESPONSES.get("services", ""),
            "legitimacy": HARDCODED_RESPONSES.get("legit", ""),
            "program_details": HARDCODED_RESPONSES.get("program details", ""),
            "qualifications": HARDCODED_RESPONSES.get("qualifications", ""),
            "age_policy": HARDCODED_RESPONSES.get("age limit", ""),
            "gender_policy": HARDCODED_RESPONSES.get("gender", ""),
            "graduates_policy": HARDCODED_RESPONSES.get("graduates", ""),
            "price_note": HARDCODED_RESPONSES.get("price", HARDCODED_RESPONSES.get("how much", "")),
            "requirements": HARDCODED_RESPONSES.get("requirements", ""),
            "contact_block": HARDCODED_RESPONSES.get("urgent", ""),
            "form_hint": "📝 Please visit the 'Application Form' tab to begin your application.",
        }
        return facts

    def fuzzy_fact_match(self, prompt: str) -> str | None:
        """Lightweight keyword overlap to map unseen phrasing to an intent."""
        tokens = set(self._normalize(prompt).split())
        topic_keywords = {
            "location": {"where", "address", "map", "directions", "office", "find", "tiktok", "location"},
            "hours": {"hours", "open", "opening", "schedule", "time", "times"},
            "contact": {"contact", "phone", "call", "email", "mail", "number"},
            "services": {"services", "offer", "provide", "service"},
            "program details": {"process", "procedure", "steps", "flow", "timeline", "briefing", "assessment", "program", "details", "apply"},
            "qualifications": {"qualifications", "qualification", "eligible", "eligibility", "experience", "training"},
            "age limit": {"age", "years", "old", "limit"},
            "gender": {"gender", "male", "female", "women", "men"},
            "graduates": {"graduate", "undergraduate", "degree", "college"},
            "price": {"price", "cost", "fee", "payment", "pay", "rates", "rate", "how", "much"},
            "requirements": {"requirements", "documents", "docs", "papers", "needed"},
            "appointment": {"appointment", "book", "schedule", "set", "meeting"},
            "status": {"status", "track", "tracking", "update", "reference"},
            "visa type": {"type", "b1", "b2", "what", "visa", "kind"},
        }
        best_key = None
        best_score = 0
        for key, kws in topic_keywords.items():
            score = len(tokens & kws)
            if score > best_score:
                best_score = score
                best_key = key
        # Require at least 2 keyword overlaps to avoid false positives
        if best_score >= 2:
            return best_key
        return None

    def is_relevant_query(self, prompt):
        """Check if the query is related to State101 Travel services"""
        normalized_prompt = prompt.lower()
        
        # First check for obvious off-topic requests
        for keyword in self.offtopic_keywords:
            if keyword in normalized_prompt:
                return False
        
        # Check for greetings (always allow)
        greetings = ["hi", "hello", "hey", "good morning", "good afternoon", "good evening"]
        if any(greeting in normalized_prompt for greeting in greetings) and len(normalized_prompt.split()) <= 3:
            return True
        
        # Check if query contains relevant keywords
        has_relevant_keyword = any(keyword in normalized_prompt for keyword in self.relevant_keywords)
        
        # If no relevant keywords found and prompt is substantial (>5 words), likely off-topic
        if not has_relevant_keyword and len(normalized_prompt.split()) > 5:
            return False
            
        return True

    @sleep_and_retry
    @limits(calls=10, period=60)
    def generate(self, prompt):
        try:
            # Detect and translate if not English
            if len(prompt.split()) > 2:
                lang = detect(prompt)
                if lang != "en":
                    prompt = GoogleTranslator(source=lang, target="en").translate(prompt)
        except:
            pass

        # Intent-first, hardcoded responses
        intent = self.match_intent(prompt)
        if intent:
            canonical = self.get_canonical_response(intent)
            if canonical:
                return canonical
            if self.strict_mode:
                return "📘 I can share our official information only. Please ask about requirements, location, hours, services, or submit the application form."

        # Fuzzy fact match before LLM
        fuzzy_intent = self.fuzzy_fact_match(prompt)
        if fuzzy_intent:
            canonical = self.get_canonical_response(fuzzy_intent)
            if canonical:
                return canonical
            if self.strict_mode:
                return "📘 I can share our official information only. Please ask about requirements, location, hours, services, or submit the application form."

        # Check if query is relevant to State101 Travel
        if not self.is_relevant_query(prompt):
            return """😊 I'm sorry, but I can only assist with queries related to **State101 Travel** and our visa services for the US and Canada.

I can help you with:
✈️ Visa application processes and requirements
📋 Documentation needed for Canadian/American visas
📞 Booking appointments and consultations
📍 Our office location and business hours
💼 B1 visa information and opportunities

**How can I assist you with your visa needs today?**"""

        # Check for form request
        if "form" in prompt.lower() or "apply" in prompt.lower():
            return "📝 Please visit the 'Application Form' tab to begin your application."

        # Clean prompt and match hardcoded answers
        normalized_prompt = re.sub(r'[^\w\s]', '', prompt).strip().lower()
        for question, answer in HARDCODED_RESPONSES.items():
            normalized_question = re.sub(r'[^\w\s]', '', question).strip().lower()
            if normalized_question in normalized_prompt:
                return answer

        # Rate limiting
        now = time.time()
        if now - self.last_call < 1.5:
            time.sleep(1.5 - (now - self.last_call))

        try:
            # Enhanced system prompt with strict boundaries
            enhanced_system_prompt = SYSTEM_PROMPT + """

**CRITICAL RESTRICTION**: You MUST ONLY answer questions related to State101 Travel and visa services. If asked about anything unrelated (coding, recipes, general knowledge, etc.), respond with:

"I apologize, but I can only assist with State101 Travel visa services. Please ask me about US/Canada visa requirements, applications, or our services."

Never provide code, calculations, or information outside of visa/travel services."""

            # Provide facts-backed instructions when enabled
            facts = self.pack_facts() if self.smart_facts_mode else None
            facts_instructions = """
You must answer ONLY using the FACTS provided below. If a requested detail isn't explicitly present, do your best to:
1) Use the closest relevant item from FACTS (e.g., use program_details for process questions, price_note for fees, contact_block for contact info).
2) If it still cannot be answered from FACTS, respond with the official contact_block and form_hint. Do NOT say "not available".
Never invent, rename, or alter addresses, phone numbers, emails, hours, or services beyond what appears in FACTS.
"""

            messages = [
                {"role": "system", "content": enhanced_system_prompt}
            ]
            if facts:
                messages.append({"role": "system", "content": facts_instructions})
                # Keep facts compact
                messages.append({"role": "system", "content": f"FACTS: {facts}"})
            messages.append({"role": "user", "content": prompt})

            response = self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                temperature=0.3,
                max_tokens=800
            )
            self.last_call = time.time()
            self.daily_count += 1
            
            # Double-check the response doesn't contain code or off-topic content
            response_text = response.choices[0].message.content
            if self.strict_mode:
                # Only sanitize to location if the original prompt matched location intent
                if self.match_intent(prompt) == "location":
                    response_text = HARDCODED_RESPONSES.get("location", response_text)
            if any(indicator in response_text.lower() for indicator in ["```", "def ", "function", "import ", "class "]):
                return """😊 I'm sorry, but I can only assist with queries related to **State101 Travel** and our visa services.

**How can I help you with your visa application today?**"""
            
            return response_text
            
        except Exception as e:
            return "⚠️ System busy. Please contact us directly:\n📞 +63 905-804-4426 or +63 969-251-0672\n📧 state101ortigasbranch@gmail.com"
# ========== GOOGLE SHEETS INTEGRATION ==========
@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
def save_to_sheet(data):
    try:
        creds = Credentials.from_service_account_info(
            st.secrets["GCP_SERVICE_ACCOUNT"],
            scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        )
        sheet = gspread.authorize(creds).open("state101application").sheet1
        sheet.append_row(data)
        return True
    except Exception:
        return False

# ========== EMAIL SENDING (REPLACES SHEETS SUBMISSION) ==========
def send_application_email(form_data, uploaded_files, drive_folder_url: str | None = None):
    """Send application details and attachments to a configured email.

    Expects the following keys in st.secrets:
      - SMTP_HOST (default: smtp.gmail.com)
      - SMTP_PORT (default: 587)
      - SMTP_USER
      - SMTP_PASS (or SMTP_PASSWORD)
      - MAIL_TO (recipient email)
    """
    host = st.secrets.get("SMTP_HOST", "smtp.gmail.com")
    port = int(st.secrets.get("SMTP_PORT", 587))
    user = st.secrets.get("SMTP_USER")
    pwd = st.secrets.get("SMTP_PASS", st.secrets.get("SMTP_PASSWORD"))
    to_addr = st.secrets.get("MAIL_TO")
    from_addr = st.secrets.get("FROM_EMAIL", user)

    if not all([user, pwd, to_addr]):
        raise RuntimeError("Missing SMTP settings in secrets.toml (SMTP_USER, SMTP_PASS, MAIL_TO)")

    msg = EmailMessage()
    subject = f"New Visa Application - {form_data['full_name']} ({form_data['visa_type']})"
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    # Make it easy to reply to the applicant directly
    if form_data.get("email"):
        msg["Reply-To"] = form_data["email"]

    body_lines = [
            "A new visa application has been submitted:\n",
        f"Full Name: {form_data['full_name']}",
        f"Email: {form_data['email']}",
        f"Phone: {form_data['phone']}",
        f"Age: {form_data['age']}",
        f"Address: {form_data['address']}",
        f"Visa Type: {form_data['visa_type']}",
        f"Preferred Day: {form_data.get('preferred_day', 'N/A')}",
        f"Available Time: {form_data['available_time']}",
        f"Submitted At: {time.strftime('%Y-%m-%d %H:%M')}"
    ]
    if drive_folder_url:
        body_lines.append(f"Drive Folder: {drive_folder_url}")
    msg.set_content("\n".join(body_lines))

    # Attach uploaded files
    for uf in uploaded_files:
        try:
            filename = getattr(uf, "name", "attachment")
            file_bytes = uf.getvalue() if hasattr(uf, "getvalue") else uf.read()
            mime_type, _ = mimetypes.guess_type(filename)
            if mime_type:
                maintype, subtype = mime_type.split("/", 1)
            else:
                maintype, subtype = ("application", "octet-stream")
            msg.add_attachment(file_bytes, maintype=maintype, subtype=subtype, filename=filename)
        except Exception:
            # If any attachment fails, continue sending others
            continue

    # Send via SMTP
    context = ssl.create_default_context()
    try:
        if port == 465:
            # Implicit SSL (SMTPS)
            with smtplib.SMTP_SSL(host, port, context=context) as server:
                server.login(user, pwd)
                server.send_message(msg)
        else:
            # STARTTLS
            with smtplib.SMTP(host, port) as server:
                server.ehlo()
                server.starttls(context=context)
                server.login(user, pwd)
                server.send_message(msg)
    except Exception as e1:
        # Fallback: try the other common port (587 or 465)
        alt_port = 587 if port != 587 else 465
        try:
            if alt_port == 465:
                with smtplib.SMTP_SSL(host, alt_port, context=context) as server:
                    server.login(user, pwd)
                    server.send_message(msg)
            else:
                with smtplib.SMTP(host, alt_port) as server:
                    server.ehlo()
                    server.starttls(context=context)
                    server.login(user, pwd)
                    server.send_message(msg)
        except Exception as e2:
            raise RuntimeError(f"SMTP failed on port {port}: {e1}; fallback on {alt_port} also failed: {e2}")
    return True

# ========== GOOGLE DRIVE BACKUP ==========
def _sanitize_filename(name: str) -> str:
    # Remove characters not allowed in Drive names just in case
    return re.sub(r"[\\/:*?\"<>|]+", "-", name).strip()

def upload_to_drive(form_data, uploaded_files):
    """Create a subfolder under DRIVE_PARENT_FOLDER_ID and upload form.txt + attachments.

    Returns the folder webViewLink URL.
    """
    parent_id = st.secrets.get("DRIVE_PARENT_FOLDER_ID")
    if not parent_id:
        raise RuntimeError("Missing DRIVE_PARENT_FOLDER_ID in secrets.toml")

    creds = Credentials.from_service_account_info(
        st.secrets["GCP_SERVICE_ACCOUNT"], scopes=["https://www.googleapis.com/auth/drive"]
    )
    drive = build("drive", "v3", credentials=creds)

    # Preflight: ensure parent folder is accessible
    try:
        drive.files().get(fileId=parent_id, fields="id, name", supportsAllDrives=True).execute()
    except Exception as e:
        raise RuntimeError(f"Drive parent folder not accessible. Check sharing and ID. Underlying error: {e}")

    # Create subfolder name like 20251107-1430 - Full Name
    when = datetime.now().strftime("%Y%m%d-%H%M")
    folder_name = _sanitize_filename(f"{when} - {form_data['full_name']}")

    folder_metadata = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    folder = drive.files().create(body=folder_metadata, fields="id, webViewLink", supportsAllDrives=True).execute()
    folder_id = folder.get("id")
    folder_link = folder.get("webViewLink") or f"https://drive.google.com/drive/folders/{folder_id}"

    # Upload form details as text file
    form_lines = [
        f"Full Name: {form_data['full_name']}",
        f"Email: {form_data['email']}",
        f"Phone: {form_data['phone']}",
        f"Age: {form_data['age']}",
        f"Address: {form_data['address']}",
        f"Visa Type: {form_data['visa_type']}",
        f"Preferred Day: {form_data.get('preferred_day', 'N/A')}",
        f"Available Time: {form_data['available_time']}",
        f"Submitted At: {time.strftime('%Y-%m-%d %H:%M')}",
    ]
    form_text = "\n".join(form_lines)
    media = MediaIoBaseUpload(io.BytesIO(form_text.encode("utf-8")), mimetype="text/plain")
    drive.files().create(
        body={"name": "application.txt", "parents": [folder_id]},
        media_body=media,
        fields="id",
        supportsAllDrives=True,
    ).execute()

    # Upload each attachment
    for uf in uploaded_files:
        try:
            filename = _sanitize_filename(getattr(uf, "name", "attachment"))
            file_bytes = uf.getvalue() if hasattr(uf, "getvalue") else uf.read()
            mime_type, _ = mimetypes.guess_type(filename)
            if not mime_type:
                mime_type = "application/octet-stream"
            media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype=mime_type)
            drive.files().create(
                body={"name": filename, "parents": [folder_id]},
                media_body=media,
                fields="id",
                supportsAllDrives=True,
            ).execute()
        except Exception:
            continue

    return folder_link

# ========== APPLICATION FORM ==========
def show_application_form():
    with st.form("visa_form"):
        st.subheader("📝 Initial Assessment Form")
        st.caption("Kindly fill up the following details for initial assessment")

        cols = st.columns(2)
        full_name = cols[0].text_input("Full Name*")
        phone = cols[1].text_input("Phone Number*")  
        email = st.text_input("Email*")  
        # No strict age limit per FAQs; allow a broad, realistic range. Using 1–120 as bounds.
        age = st.number_input("Age*", min_value=1, max_value=120)
        address = st.text_area("Complete Address*")

        visa_type = st.radio("Visa Applying For*", ["Canadian Visa ", "American Visa"])
        day_of_week = st.radio(
            "Preferred Day (Monday–Sunday)*",
            [
                "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"
            ]
        )
        available_time = st.selectbox(
            "What time of day are you free for consultation?*",
            ["9AM-12PM", "1PM-3PM", "4PM-5PM"]
        )

        st.markdown("---")
        st.markdown("#### Upload your Requirements")
        uploads = st.file_uploader(
            "Upload your Requirements (minimum of 2 files e.g., passport, photo, certificates, Resume, Diploma)",
            accept_multiple_files=True,
            type=None,
            help="Attach at least two supporting documents (e.g., passport, photo, certificates,Resume,Diploma)."
        )

        submitted = st.form_submit_button("Submit Application")
        if submitted:
            if not all([full_name, email, phone, address]):
                st.error("Please fill all required fields (*)")
            elif not re.match(r"[^@]+@[^@]+\.[^@]+", email):
                st.error("Please enter a valid email address")
            elif not re.match(r"^09\d{9}$", phone.replace(" ", "").replace("-", "")):
                st.error("Please enter a valid Philippine phone number (11 digits, starts with 09)")
            elif not uploads or len(uploads) < 2:
                st.error("Please upload at least 2 files under 'Upload your Requirements'.")
            else:
                form_payload = {
                    "full_name": full_name,
                    "email": email,
                    "phone": phone,
                    "age": age,
                    "address": address,
                    "visa_type": visa_type,
                    "preferred_day": day_of_week,
                    "available_time": available_time,
                }

                email_ok = False
                sheet_ok = False
                drive_ok = False
                drive_link = None
                email_err = None
                sheet_err = None
                drive_err = None

                # Try Google Drive backup (subfolder + files) first to capture link
                try:
                    drive_link = upload_to_drive(form_payload, uploads)
                    drive_ok = True
                except Exception as e:
                    drive_ok = False
                    drive_err = str(e)

                # Try send email (include drive link if available)
                try:
                    send_application_email(form_payload, uploads, drive_folder_url=drive_link)
                    email_ok = True
                except Exception as e:
                    email_ok = False
                    email_err = str(e)

                # Build row for Google Sheets backup (includes preferred_day and Drive link)
                sheet_row = [
                    full_name,
                    email,
                    phone,
                    str(age),
                    address,
                    visa_type,
                    day_of_week,
                    available_time,
                    time.strftime("%Y-%m-%d %H:%M"),
                    drive_link or "",
                ]

                # Try save to Google Sheet as backup
                try:
                    sheet_ok = save_to_sheet(sheet_row)
                except Exception as e:
                    sheet_ok = False
                    sheet_err = str(e)

                # Report outcome (end-user friendly)
                if email_ok or sheet_ok or drive_ok:
                    st.success("✅ Application submitted! Our team will contact you within 24 hours.")
                else:
                    st.error("❌ We couldn't submit your application due to a temporary issue. Please try again in a few minutes or contact us at state101ortigasbranch@gmail.com.")

                # Optional diagnostics
                debug = bool(st.secrets.get("DEBUG_SUBMISSION", False))
                if debug and (email_err or drive_err or sheet_err):
                    with st.expander("Diagnostics (for developers)"):
                        st.write({
                            "drive_ok": drive_ok,
                            "drive_err": drive_err,
                            "email_ok": email_ok,
                            "email_err": email_err,
                            "sheet_ok": sheet_ok,
                            "sheet_err": sheet_err,
                            "drive_parent": st.secrets.get("DRIVE_PARENT_FOLDER_ID"),
                            "smtp_host": st.secrets.get("SMTP_HOST"),
                            "smtp_port": st.secrets.get("SMTP_PORT"),
                            "mail_to": st.secrets.get("MAIL_TO"),
                        })

                # Show concise error hints only in debug mode
                if debug:
                    if not email_ok and email_err:
                        st.info(f"Email error: {email_err}")
                    if not drive_ok and drive_err:
                        st.info(f"Drive error: {drive_err}")

# ========== REQUIREMENTS DISPLAY ==========
def show_requirements():
    st.subheader("📋 Initial Requirements Checklist")
    st.markdown(HARDCODED_RESPONSES["requirements"])
    st.divider()
    st.write("""
    **Need Help? Contact Us:**
    - 📞 +639058044426 or 639692510672 
    - 📧 state101ortigasbranch@gmail.com
    - 📍 2F Unit 223, One Oasis Hub B, Ortigas Ext, Pasig
    - ⏰ Mon-Sat 9AM-5PM
    """)

# ========== APPLY THEME ==========
def apply_theme(theme_name):
    theme = COLOR_THEMES[theme_name]
    
    css = f"""
    <style>
    /* Main background */
    .stApp {{
        background-color: {theme['primary']};
        color: {theme['text']};
        transition: background-color 0.3s ease, color 0.3s ease;
    }}

    /* Sidebar */
    .css-1d391kg {{
        background-color: {theme['secondary']};
        color: {theme['text']};
        transition: background-color 0.3s ease, color 0.3s ease;
    }}

    /* Headers */
    h1, h2, h3, h4, h5, h6 {{
        color: {theme['text']} !important;
        transition: color 0.3s ease;
    }}

    /* Main text */
    .stMarkdown, .stText {{
        color: {theme['text']};
        transition: color 0.3s ease;
    }}

    /* Buttons (accent / solid) */
    .stButton>button {{
        background-color: {theme['button']};
        color: white !important;
        border: none;
        border-radius: 6px;
        padding: 0.5rem 1rem;
        font-weight: 600;
        transition: all 0.25s ease;
    }}
    .stButton>button:hover {{
        filter: brightness(1.05);
        box-shadow: 0 0 10px {theme['accent']};
    }}

    /* Outlined / minimal buttons (keeps existing UI consistent) */
    .stDownloadButton>button {{
        background: transparent;
        border: 2px solid {theme['text']};
        color: {theme['text']} !important;
        border-radius: 6px;
        font-weight: 600;
    }}
    .stDownloadButton>button:hover {{
        background-color: {theme['text']};
        color: {theme['primary']} !important;
    }}

    /* Input fields */
    .stTextInput>div>div>input, .stTextArea>div>div>textarea {{
        background-color: {theme['secondary']};
        color: {theme['text']};
        border: 1px solid {theme['text']};
        border-radius: 6px;
        transition: background-color 0.25s ease, color 0.25s ease, border-color 0.25s ease;
    }}
    /* Placeholder readability */
    .stTextInput>div>div>input::placeholder,
    .stTextArea>div>div>textarea::placeholder {{
        color: {theme['text_secondary']};
        opacity: 1; /* ensure visibility across browsers */
    }}
    /* Focus visibility */
    .stTextInput>div>div>input:focus,
    .stTextArea>div>div>textarea:focus {{
        outline: 2px solid {theme['accent']};
        border-color: {theme['accent']};
    }}

    /* Radio container */
    .stRadio>div {{
        background-color: {theme['secondary']};
        padding: 10px;
        border-radius: 6px;
        transition: background-color 0.25s ease;
    }}

    /* --- RADIO LABELS: UNIFIED TEXT COLOR FOR ACCESSIBILITY --- */
    div[data-baseweb="radio"] label,
    div[data-baseweb="radio"] label p,
    div[data-baseweb="radio"] label span,
    .stRadio label,
    .stRadio label p,
    .stRadio label span {{
        color: {theme['text']} !important;  /* match standard body text */
        font-weight: 600;
        background: none !important;
        -webkit-background-clip: initial !important;
        -webkit-text-fill-color: {theme['text']} !important;
    }}

    /* Highlight the selected radio option slightly using the accent color */
    div[data-baseweb="radio"] [aria-checked="true"] label,
    div[data-baseweb="radio"] [aria-checked="true"] label p,
    div[data-baseweb="radio"] [aria-checked="true"] label span {{
        color: {theme['accent']} !important;
        -webkit-text-fill-color: {theme['accent']} !important;
    }}

    /* Select boxes */
    .stSelectbox>div>div {{
        background-color: {theme['secondary']};
        color: {theme['text']};
        border: 1px solid {theme['text']};
        border-radius: 6px;
    }}
    .stSelectbox>div:focus-within {{
        outline: 2px solid {theme['accent']};
    }}

    /* Chat messages */
    .stChatMessage {{
        background-color: {theme['secondary']};
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 0.5rem 0;
        color: {theme['text']};
    }}

    /* Tabs */
    .stTabs [data-baseweb="tab"] {{
        background-color: {theme['secondary']};
        color: {theme['text']};
        border-radius: 4px 4px 0 0;
        padding: 10px 16px;
    }}
    .stTabs [aria-selected="true"] {{
        background-color: {theme['accent']};
        color: #FFFFFF !important;
    }}

    /* Form labels */
    .stForm label {{
        color: {theme['text']} !important;
   }}

        /* Alerts: theme-aware for both light and dark */
        .stSuccess, .stError,
        div[role="status"], div[role="alert"],
        div[data-testid="stStatusWidget"], div[data-testid="stAlert"],
        div[class*="stAlert"] {{
            background-color: {theme['secondary']} !important;
            color: {theme['text']} !important;
            font-weight: 600 !important;
            border-radius: 6px !important;
            padding: 0.5rem 0.75rem !important;
            border-left: 4px solid {theme['accent']} !important;
            box-shadow: none !important;
        }}

        /* ensure text inside the alerts is visible */
        div[role="status"] p, div[role="alert"] p,
        div[data-testid="stStatusWidget"] p, div[data-testid="stAlert"] p,
        .stSuccess p, .stError p {{
            color: {theme['text']} !important;
            margin: 0;
        }}

    /* File uploader visibility */
    div[data-testid="stFileUploader"] {{
        background: {theme['secondary']};
        color: {theme['text']};
        border: 1px solid {theme['text']};
        border-radius: 8px;
        padding: 8px 12px;
    }}
    /* Dropzone area (cover common internal structures) */
    div[data-testid="stFileUploader"] [data-testid*="Dropzone"],
    div[data-testid="stFileUploader"] [class*="dropzone" i],
    div[data-testid="stFileUploader"] section,  /* fallback for versions rendering a <section> */
    div[data-testid="stFileUploader"] div[role="button"] {{ /* clickable drop area */
        background: {theme['secondary']} !important;
        color: {theme['text']} !important;
        border: 2px dashed {theme['text']} !important;
        border-radius: 8px !important;
    }}
    /* Typography inside dropzone */
    div[data-testid="stFileUploader"] p,
    div[data-testid="stFileUploader"] span,
    div[data-testid="stFileUploader"] svg {{
        color: {theme['text']} !important;
        fill: {theme['text']} !important;
        opacity: 0.95;
    }}
    /* Browse/choose button inside uploader */
    div[data-testid="stFileUploader"] button {{
        background-color: {theme['button']} !important;
        color: #FFFFFF !important;
        border: none !important;
        border-radius: 6px !important;
        padding: 4px 10px !important;
    }}
    /* Divider */
    .stDivider {{
        border-color: {theme['text']} !important;
        opacity: 0.3;
    }}

    /* Theme toggle button */
    .theme-toggle {{
        position: fixed;
        top: 15px;
        right: 15px;
        z-index: 999;
        background-color: {theme['button']};
        color: white;
        border: none;
        border-radius: 50%;
        width: 40px;
        height: 40px;
        font-size: 20px;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        transition: all 0.3s ease;
    }}
    .theme-toggle:hover {{
        transform: scale(1.06);
        box-shadow: 0 6px 18px rgba(0,0,0,0.18);
    }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)


# ========== MAIN APP ==========
def main():
    # Use company logo as page icon (favicon) when available
    logo_path = Path("images/state101-logo.png")
    page_icon = logo_path if logo_path.exists() else "🛂"
    st.set_page_config(
        page_title="State101 Visa Assistant",
        page_icon=page_icon,
        layout="centered"  # center the main content for better desktop/mobile look
    )
    
    # Initialize theme in session state
    if "theme" not in st.session_state:
        st.session_state.theme = "White"
    
    if "agreed" not in st.session_state:
        st.session_state.agreed = False

    if not st.session_state.agreed:
        # Apply theme even to terms page
        apply_theme(st.session_state.theme)
        
        st.title("📝 Terms and Conditions")
        st.write("""
        Before using our services, please read and agree to the following:

       State101 Chatbot Terms and Conditions
By using the State101 Chatbot, you agree to the following terms and conditions.
1. General Disclaimer
The chatbot is for information and initial consultation only. The information it provides is not legal
advice and should not replace a formal consultation with a qualified professional. To get
personalized guidance and move forward with any application, you must book an official
appointment with our team.
2. Personal Data
Any personal data you provide, including through the Application Form, is handled securely. It will be
used solely to help with your visa assistance and consultation. We use strict validation rules to ensure
all information is complete and correctly formatted.
3. Chatbot Functionality
The chatbot is designed to provide a seamless experience with several key functions:
• Conversational Assistant: You can ask questions about Canadian and American visas, and your chat
history is saved for you to review.
• Application Form: A dedicated tab for submitting your personal and contact details for visa
assistance.
• Visa Requirements: The chatbot provides a clear checklist of necessary documents for Canadian
and American visa applications in a separate tab.
• Language Support: It can detect and translate non-English messages to improve communication
accuracy.
• AI-Powered Responses: While many common questions have pre-set answers for consistency, the
chatbot can also use AI to give more detailed responses to complex queries.
• Fallback Logic: In case of technical issues, the chatbot will provide a friendly notification and our
contact information. It also uses rate limiting to prevent excessive requests and maintain service
stability.
• Session Management: The chatbot remembers your interactions and agreements within a single
session, so you won't lose your chat history or have to re-agree to the terms if you refresh the page.
4. Limitation of Liability
State101 Travel is not liable for any direct or indirect damages resulting from the use of the chatbot.
This includes but isn't limited to visa application rejections, delays, or any loss of income or travel
plans.
5. Changes to Terms
We reserve the right to update these terms at any time. Any significant changes will be
communicated to our clients. By continuing to use the chatbot, you agree to the latest version of
these terms.

        """)

        
        st.markdown("""
        <style>
        div[data-testid="stCheckbox"] label p {
            color: #0066ff !important;  /* Blue text */
            font-weight: bold !important;
            font-size: 1rem !important;
        }
        </style>
        """, unsafe_allow_html=True)

        if st.checkbox("I agree to the Terms and Conditions"):
            st.session_state.agreed = True
            st.rerun()
        else:
            st.stop()

    # Apply selected theme after agreement
    apply_theme(st.session_state.theme)

    
    # Theme toggle button - SIMPLE VERSION THAT WILL WORK
    current_theme = st.session_state.theme
    toggle_icon = COLOR_THEMES[current_theme]["icon"]
    
    # Create columns for logo, title, and toggle button
    col_logo, col_title, col_toggle = st.columns([1, 5, 1])

    with col_logo:
        if logo_path.exists():
            # use_column_width deprecated; replaced with use_container_width
            st.image(str(logo_path), use_container_width=True)
        else:
            st.markdown("<div style='font-size:46px'>🛂</div>", unsafe_allow_html=True)

    with col_title:
        st.title("State101 Visa Assistant")
        st.caption("Specializing in US and Canada Visa Applications")

    with col_toggle:
        # Simple button that will definitely be visible
        if st.button(toggle_icon, key="theme_toggle_button"):
            st.session_state.theme = "Black" if st.session_state.theme == "White" else "White"
            st.rerun()

        # Remove sidebar entirely and center the main container with a clean max-width
        st.markdown(
                """
                <style>
                    /* Hide sidebar */
                    [data-testid=stSidebar], .css-1d391kg { display: none !important; }

                    /* Center the main content with responsive max width */
                    .block-container {
                        max-width: 900px;          /* good balance for desktop */
                        margin-left: auto;
                        margin-right: auto;
                        padding-left: 1.25rem !important;
                        padding-right: 1.25rem !important;
                    }

                    /* Mobile tweaks */
                    @media (max-width: 640px) {
                        .block-container { max-width: 100%; padding-left: 0.75rem !important; padding-right: 0.75rem !important; }
                    }
                </style>
                """,
                unsafe_allow_html=True,
        )

    # Initialize chatbot only after terms are accepted
    if "chatbot" not in st.session_state and st.session_state.agreed:
        st.session_state.chatbot = VisaAssistant()
    if "messages" not in st.session_state:
        st.session_state.messages = []

    tab1, tab2, tab3 = st.tabs(["Chat Assistant", "Application Form", "Requirements"])

    with tab1:
        # Create a container for chat messages
        chat_container = st.container()
        
        # Display chat messages
        with chat_container:
            for msg in st.session_state.messages:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])
        
        # Add empty space to push content up
        st.markdown("<br>" * 2, unsafe_allow_html=True)

        # Input box at the bottom (only in tab1)
        user_prompt = st.chat_input("Ask about US and Canada visas...")
        if user_prompt:
            # Show user's message
            st.session_state.messages.append({"role": "user", "content": user_prompt})
            
            # Get assistant response
            bot_response = st.session_state.chatbot.generate(user_prompt)
            st.session_state.messages.append({"role": "assistant", "content": bot_response})
            
            # Rerun to refresh and show new messages
            st.rerun()

    with tab2:
        show_application_form()

    with tab3:
        show_requirements()

if __name__ == "__main__":
    main()

















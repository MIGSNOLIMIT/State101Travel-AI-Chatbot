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
   - Always emphasize: "Services are by appointment only"

5. **Style Guide**:
   - Use bullet points for requirements
   - Include emojis for readability (🛂 ✈️ 📝)
   - Never speculate - defer to official contacts when uncertain

6. **Data Handling**:
   - Remind users: "Your information is secure and will only be used for visa assessment"

7. **Error Handling**:
   - If unsure: "I specialize in visa assistance. For this question, please contact our specialists during business hours."
"""

# ========== HARDCODED RESPONSES ==========
HARDCODED_RESPONSES = {
"requirements": """🛂 **Visa Requirements**:\n- Valid passport (with atleast 6 months validity beyond your intended stay in the U.S.)\n- 2x2 photo (white background)\n- Training Certificate(if available)\n- Diploma(if available)\n- Resume""",
    "appointment": "⏰ Strictly by appointment only. Please submit the application form first.",
    "location": "📍 2F Unit 223, One Oasis Hub B, Ortigas Ext, Pasig City",
    "hours": "🕘 Open Mon-Sat 9AM-5PM",
    "opportunities": "💼 B1 Visa Includes 6-month care-giving training program with our Partner homecare facilities in US.",
    "business hours": "🕘 We're open Monday to Saturday, 9:00 AM to 5:00 PM.",
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
    "legit": "✅ Proof of legitimacy are posted on our Website.",
    
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
        
        # Define topics that are considered relevant to State101 Travel
        self.relevant_keywords = [
            "visa", "travel", "passport", "appointment", "requirements", 
            "canada", "canadian", "america", "american", "us", "usa",
            "application", "processing", "state101", "state 101",
            "consultation", "documentation", "embassy", "interview",
            "tourist", "business", "student", "work permit", "immigration",
            "fee", "cost", "price", "hours", "location", "contact",
            "eligibility", "qualification", "denial", "approval",
            "urgent", "status", "track", "form", "apply", "b1", "b2"
        ]
        
        # Define off-topic keywords that should trigger immediate rejection
        self.offtopic_keywords = [
            "calculator", "code", "program", "recipe", "cook", "game",
            "movie", "song", "weather", "sports", "stock", "crypto",
            "math", "solve", "equation", "homework", "essay", "write a story"
        ]

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

        # Check if query is relevant to State101 Travel
        if not self.is_relevant_query(prompt):
            return """😊 I'm sorry, but I can only assist with queries related to **State101 Travel** and our visa services for the US and Canada.

I can help you with:
✈️ Visa application processes and requirements
📋 Documentation needed for Canadian/American visas
📞 Booking appointments and consultations
📍 Our office location and business hours
💼 B1/B2 visa information and opportunities

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

            response = self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": enhanced_system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=800
            )
            self.last_call = time.time()
            self.daily_count += 1
            
            # Double-check the response doesn't contain code or off-topic content
            response_text = response.choices[0].message.content
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

# ========== APPLICATION FORM ==========
def show_application_form():
    with st.form("visa_form"):
        st.subheader("📝 Initial Assessment Form")
        st.caption("Kindly fill up the following details for initial assessment")

        cols = st.columns(2)
        full_name = cols[0].text_input("Full Name*")
        phone = cols[1].text_input("Phone Number*")  
        email = st.text_input("Email*")  
        age = st.number_input("Age*", min_value=18, max_value=99)
        address = st.text_area("Complete Address*")

        visa_type = st.radio("Visa Applying For*", ["Canadian Visa ", "American Visa"])
        available_time = st.selectbox(
            "What time of day are you free for consultation?*",
            ["9AM-12PM", "1PM-3PM", "4PM-5PM"]
        )

        submitted = st.form_submit_button("Submit Application")
        if submitted:
            if not all([full_name, email, phone, address]):
                st.error("Please fill all required fields (*)")
            elif not re.match(r"[^@]+@[^@]+\.[^@]+", email):
                st.error("Please enter a valid email address")
            elif not re.match(r"^09\d{9}$", phone.replace(" ", "").replace("-", "")):
                st.error("Please enter a valid Philippine phone number (11 digits, starts with 09)")
            else:
                data = [
                    full_name, email, phone, str(age), address,
                    visa_type, available_time, time.strftime("%Y-%m-%d %H:%M")
                ]
                if save_to_sheet(data):
                    st.success("✅ Application Submitted! Our team will contact you within 24 hours.")
                else:
                    st.error("⚠️ Submission failed. Please contact us directly at state101ortigasbranch@gmail.com")

# ========== REQUIREMENTS DISPLAY ==========
def show_requirements():
    st.subheader("📋 Visa Requirements Checklist")
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
        transition: background-color 0.25s ease, color 0.25s ease;
    }}

    /* Radio container */
    .stRadio>div {{
        background-color: {theme['secondary']};
        padding: 10px;
        border-radius: 6px;
        transition: background-color 0.25s ease;
    }}

    /* --- RADIO LABELS: FORCE ELECTRIC BLUE (#00BFFF) FOR BOTH THEMES --- */
    /* cover multiple possible DOM structures Streamlit may render */
    div[data-baseweb="radio"] label,
    div[data-baseweb="radio"] label p,
    div[data-baseweb="radio"] label span,
    .stRadio label,
    .stRadio label p,
    .stRadio label span {{
        color: #00BFFF !important;
        font-weight: 700;
    }}

    /* ensure checked radio remains blue */
    div[data-baseweb="radio"] [aria-checked="true"] label,
    div[data-baseweb="radio"] [aria-checked="true"] label p,
    div[data-baseweb="radio"] [aria-checked="true"] label span {{
        color: #00BFFF !important;
        font-weight: 700;
    }}

    /* Select boxes */
    .stSelectbox>div>div {{
        background-color: {theme['secondary']};
        color: {theme['text']};
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

                /* Success / error boxes - robust override for Streamlit alerts */
        .stSuccess, .stError,
        div[role="status"], div[role="alert"],
        div[data-testid="stStatusWidget"], div[data-testid="stAlert"],
        div[class*="stAlert"] {{
            background-color: #000000 !important;
            color: #FFFFFF !important;
            font-weight: 600 !important;
            border-radius: 6px !important;
            padding: 0.5rem 0.75rem !important;
            box-shadow: none !important;
        }}

        /* ensure text inside the alerts is white */
        div[role="status"] p, div[role="alert"] p,
        div[data-testid="stStatusWidget"] p, div[data-testid="stAlert"] p,
        .stSuccess p, .stError p {{
            color: #FFFFFF !important;
            margin: 0;
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
    st.set_page_config(
        page_title="State101 Visa Assistant",
        page_icon="🛂",
        layout="centered"
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
    
    # Create columns for title and toggle button
    col1, col2, col3 = st.columns([5, 1, 1])
    
    with col1:
        st.title("🛂 State101 Visa Assistant")
        st.caption("Specializing in US and Canada Visa Applications")
    
    with col3:
        # Simple button that will definitely be visible
        if st.button(toggle_icon, key="theme_toggle_button"):
            st.session_state.theme = "Black" if st.session_state.theme == "White" else "White"
            st.rerun()

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














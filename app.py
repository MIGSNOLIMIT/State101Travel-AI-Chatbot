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
    "requirements": """🛂 **Visa Requirements**:\n- Valid passport (with atleast 6 months validity beyond your intended stay in the U.S.)\n- 2x2 photo (white background)\n- Resume\n- NBI Clearance\n- Birth Certificate\n- Marriage Cert (if applicable)\n- Employment Certificate""",
    "appointment": "⏰ Strictly by appointment only. Please submit the application form first.",
    "location": "📍 2F Unit 223, One Oasis Hub B, Ortigas Ext, Pasig City",
    "hours": "🕘 Open Mon-Sat 9AM-5PM",
    "opportunities": "💼 B1 Visa Includes 6-month care-giving training program with our Partner homecare facilities in US.",
    "business hours": "🕘 We're open Monday to Saturday, 9:00 AM to 5:00 PM.",
    "processing time": "⏳ Standard processing takes 2-4 weeks. Expedited services may be available.",
    "complex": "🔍 For case-specific advice, please contact our specialists directly:\n📞 0961 084 2538\n📧 state101ortigasbranch@gmail.com",
    "status": "🔄 For application status updates, please email us with your reference number.",
    "urgent": "⏰ For urgent concerns, call us at +63 905-804-4426 or +63 969-251-0672 during business hours.",
    "how much": "Please proceed to Application Form for Initial Assesment and expect a phone Call within 24 hrs",
    "legit": "Proof of legitimacy are posted on our Website",
    "Tinuod_ba _to?": "Proof of legitimacy are posted on our Website"
}

# ========== COLOR THEMES ==========
COLOR_THEMES = {
    "White": {
        "primary": "#FFFFFF",
        "secondary": "#F0F2F6",
        "text": "#262730",
        "accent": "#FF4B4B",
        "button": "#FF4B4B",
        "icon": "🌙"  # Moon icon for light mode
    },
    "Black": {
        "primary": "#262730",
        "secondary": "#0E1117",
        "text": "#FAFAFA",
        "accent": "#FF4B4B",
        "button": "#FF4B4B",
        "icon": "☀️"  # Sun icon for dark mode
    }
}

# ========== LLM WRAPPER ==========
class VisaAssistant:
    def __init__(self):
        self.client = Groq(api_key=st.secrets["GROQ_API_KEY"])
        self.daily_count = 0
        self.last_call = 0

    @sleep_and_retry
    @limits(calls=10, period=60)
    def generate(self, prompt):
        try:
            # Detect and translate if not English
            if len(prompt.split()) > 2:  # Only detect for longer texts
                lang = detect(prompt)
                if lang != "en":
                    prompt = GoogleTranslator(source=lang, target="en").translate(prompt)
        except:
            pass

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
            response = self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=800
            )
            self.last_call = time.time()
            self.daily_count += 1
            return response.choices[0].message.content
        except Exception as e:
            return "⚠️ System busy. Please contact us directly:\n📞 0961 084 2538\n📧 state101ortigasbranch@gmail.com"

# ========== GOOGLE SHEETS INTEGRATION ==========
@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
def save_to_sheet(data):
    try:
        creds = Credentials.from_service_account_info(
            st.secrets["GCP_SERVICE_ACCOUNT"],
            scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        )
        sheet = gspread.authorize(creds).open("State101Applications").sheet1
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
    
    /* Text */
    .stMarkdown, .stText {{
        color: {theme['text']};
        transition: color 0.3s ease;
    }}
    
    /* Buttons */
    .stButton>button {{
        background-color: {theme['button']};
        color: white;
        border: none;
        border-radius: 4px;
        padding: 0.5rem 1rem;
        transition: background-color 0.3s ease;
    }}
    
    /* Input fields */
    .stTextInput>div>div>input, .stTextArea>div>div>textarea {{
        background-color: {theme['secondary']};
        color: {theme['text']};
        transition: background-color 0.3s ease, color 0.3s ease;
    }}
    
    /* Radio buttons */
    .stRadio>div {{
        background-color: {theme['secondary']};
        color: {theme['text']};
        padding: 10px;
        border-radius: 4px;
        transition: background-color 0.3s ease, color 0.3s ease;
    }}
    
    /* Select boxes */
    .stSelectbox>div>div {{
        background-color: {theme['secondary']};
        color: {theme['text']};
        transition: background-color 0.3s ease, color 0.3s ease;
    }}
    
    /* Chat messages */
    .stChatMessage {{
        background-color: {theme['secondary']};
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 0.5rem 0;
        color: {theme['text']};
        transition: background-color 0.3s ease, color 0.3s ease;
    }}
    
    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {{
        gap: 8px;
    }}
    
    .stTabs [data-baseweb="tab"] {{
        background-color: {theme['secondary']};
        color: {theme['text']};
        border-radius: 4px 4px 0px 0px;
        padding: 10px 16px;
        transition: background-color 0.3s ease, color 0.3s ease;
    }}
    
    .stTabs [aria-selected="true"] {{
        background-color: {theme['accent']};
        color: white;
        transition: background-color 0.3s ease;
    }}
    
    /* Select box for theme */
    .stSelectbox>div>div>div {{
        color: {theme['text']};
        transition: color 0.3s ease;
    }}
    
    /* Select box dropdown */
    div[data-baseweb="select"] div {{
        color: {theme['text']} !important;
        transition: color 0.3s ease;
    }}
    
    /* Form labels */
    .stForm label {{
        color: {theme['text']} !important;
        transition: color 0.3s ease;
    }}
    
    /* Success and error messages */
    .stSuccess, .stError {{
        color: {theme['text']} !important;
        transition: color 0.3s ease;
    }}
    
    /* Divider */
    .stDivider {{
        border-color: {theme['text']} !important;
        opacity: 0.3;
        transition: border-color 0.3s ease;
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
        transform: scale(1.1);
        box-shadow: 0 4px 15px rgba(0,0,0,0.2);
    }}
    
    /* Animation for theme toggle */
    @keyframes rotate {{
        from {{ transform: rotate(0deg); }}
        to {{ transform: rotate(360deg); }}
    }}
    
    .theme-toggle.rotating {{
        animation: rotate 0.5s ease;
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

        if st.checkbox("I agree to the Terms and Conditions"):
            st.session_state.agreed = True
            st.rerun()
        else:
            st.stop()

    # Apply selected theme
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
        # Display chat messages without a scrollable container
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        # Input box at the bottom (always visible)
        user_prompt = st.chat_input("Ask about US and Canada visas...")
        if user_prompt:
            # Show user's message
            st.session_state.messages.append({"role": "user", "content": user_prompt})
            with st.chat_message("user"):
                st.markdown(user_prompt)

            # Get assistant response
            with st.chat_message("assistant"):
                with st.spinner("Researching..."):
                    bot_response = st.session_state.chatbot.generate(user_prompt)
                    st.markdown(bot_response)
                    st.session_state.messages.append({"role": "assistant", "content": bot_response})
            
            
            st.rerun()

    with tab2:
        show_application_form()

    with tab3:
        show_requirements()

if __name__ == "__main__":
    main()
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
from typing import List, Tuple
from rapidfuzz import fuzz
import importlib
import math
from email_validator import validate_email, EmailNotValidError
import phonenumbers
try:
    # Optional top-level import so it's visible in the file header when installed
    # Falls back gracefully if the package isn't present
    from fastembed import TextEmbedding as _FASTEMBED_TEXTEMBEDDING
except Exception:
    _FASTEMBED_TEXTEMBEDDING = None

# ====== DIALOG SUPPORT (modal fallback if available) ======
_DIALOG_DECORATOR = getattr(st, "dialog", None) or getattr(st, "experimental_dialog", None)
if _DIALOG_DECORATOR:
    @_DIALOG_DECORATOR("Submit without uploads?")
    def _no_uploads_modal():
        # Theme-aware styling to fit current chatbot UI
        theme_name = st.session_state.get("theme", "White")
        theme = COLOR_THEMES.get(theme_name, COLOR_THEMES["White"])
        accent = theme.get("accent", "#DC143C")
        secondary = theme.get("secondary", "#F5F5F5")
        text_color = theme.get("text", "#000000")

        st.markdown(
            f"""
            <div style="padding:10px 12px; background:{secondary}; color:{text_color};
                        border-left:4px solid {accent}; border-radius:6px; font-weight:600; margin-bottom:10px;">
                <div style="color:#b00020; font-weight:700;">Note: this can help us improve efficiency</div>
            </div>
            <div style="margin:6px 0 12px 0; color:{text_color}; font-weight:600;">
                Are you sure you don't want to upload any requirements yet?
            </div>
            """,
            unsafe_allow_html=True,
        )
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Yes, submit without uploads", key="modal_yes_submit", use_container_width=True):
                st.session_state["no_uploads_confirmed"] = True
                st.session_state["trigger_no_uploads_modal"] = False
                st.rerun()
        with col2:
            if st.button("No, I'll upload files", key="modal_no_cancel", use_container_width=True):
                st.session_state["no_uploads_confirmed"] = False
                st.session_state["trigger_no_uploads_modal"] = False
                st.session_state["pending_form_payload"] = None
                # Close dialog on rerun
                st.rerun()

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
    # Core Services
    "services": "🛂 We provide full assistance with US and Canada Visa applications and processing.",
    "what services do you offer": "🛂 We provide full assistance with US and Canada Visa applications and processing.",
    
    # Location & Contact
    "location": "📍 2F Unit 223, One Oasis Hub B, Ortigas Ext, Pasig City\n\n🗺️ Find us here: https://maps.app.goo.gl/o2rvHLBcUZhpDJfp8\n\n🎥 Location guide video: https://vt.tiktok.com/ZSyuUpdN6/",
    "located": "📍 2F Unit 223, One Oasis Hub B, Ortigas Ext, Pasig City\n\n🗺️ Find us here: https://maps.app.goo.gl/o2rvHLBcUZhpDJfp8\n\n🎥 Location guide video: https://vt.tiktok.com/ZSyuUpdN6/",
    "where is your office": "📍 2F Unit 223, One Oasis Hub B, Ortigas Ext, Pasig City\n\n🗺️ Find us here: https://maps.app.goo.gl/o2rvHLBcUZhpDJfp8\n\n🎥 Location guide video: https://vt.tiktok.com/ZSyuUpdN6/",
    "map": "📍 2F Unit 223, One Oasis Hub B, Ortigas Ext, Pasig City\n\n🗺️ Find us here: https://maps.app.goo.gl/o2rvHLBcUZhpDJfp8\n\n🎥 Location guide video: https://vt.tiktok.com/ZSyuUpdN6/",
    
    # Hours
    "hours": "🕘 Monday to Saturday, 9:00 AM to 5:00 PM",
    "business hours": "🕘 Monday to Saturday, 9:00 AM to 5:00 PM",
    "what are your office hours": "🕘 Monday to Saturday, 9:00 AM to 5:00 PM",
    "office hours": "🕘 Monday to Saturday, 9:00 AM to 5:00 PM",
    
    # Contact
    "contact": "You can contact us directly:\n📞 +63 905-804-4426 or +63 969-251-0672\n\n📧 state101ortigasbranch@gmail.com",
    "how can i contact": " You can contact us directly:\n📞 +63 905-804-4426 or +63 969-251-0672\n\n📧 state101ortigasbranch@gmail.com",
    "how can i contact your team": " You can contact us directly:\n📞 +63 905-804-4426 or +63 969-251-0672\n\n📧 state101ortigasbranch@gmail.com",
    
    # Legitimacy
    "legit": "✅ Yes, our company is 100% legitimate. We're officially registered and have a permit to operate issued by the Municipality of Pasig.",
    "is your company legit": "✅ Yes, our company is 100% legitimate. We're officially registered and have a permit to operate issued by the Municipality of Pasig.",
    "is state101 travel legitimate": "✅ Yes, our company is 100% legitimate. We're officially registered and have a permit to operate issued by the Municipality of Pasig.",
    
    # Visa Types
    "visa type": "🛂 We offer Non-Immigrant Visa for US and Express Entry and other immigration pathways for Canada.",
    "what types of visas": "🛂 We offer Non-Immigrant Visa for US and Express Entry and other immigration pathways for Canada.",
    "what type of visa you offer": "🛂 We offer Non-Immigrant Visa for US and Express Entry and other immigration pathways for Canada.",
    "what types of visas do you process": "🛂 We offer Non-Immigrant Visa for US and Express Entry and other immigration pathways for Canada.",
    "do you have student visa": "🛂 We offer Non-Immigrant Visa for US and Express Entry and other immigration pathways for Canada.",
    
    # Requirements
    "requirements": """🛂 **Initial Requirements**:
• Valid passport (Photocopy)
• 2x2 photo (white background)
• Training Certificate (if available)
• Diploma (Photocopy if available)
• Updated Resume
• Other supporting documents may be discussed during your assessment.""",
    "what are the requirements": """🛂 **Initial Requirements**:
• Valid passport (Photocopy)
• 2x2 photo (white background)
• Training Certificate (if available)
• Diploma (Photocopy if available)
• Updated Resume
• Other supporting documents may be discussed during your assessment.""",
    "documents required": """🛂 **Initial Requirements**:
• Valid passport (Photocopy)
• 2x2 photo (white background)
• Training Certificate (if available)
• Diploma (Photocopy if available)
• Updated Resume
• Other supporting documents may be discussed during your assessment.""",
    "what documents are required": """🛂 **Initial Requirements**:
• Valid passport (Photocopy)
• 2x2 photo (white background)
• Training Certificate (if available)
• Diploma (Photocopy if available)
• Updated Resume
• Other supporting documents may be discussed during your assessment.""",
    
    # Visa Approval Guarantee
    "guarantee": "✅ Yes, we significantly increase your chances of visa approval. Whether you are applying for a US Non-Immigrant Visa or Express Entry to Canada, our expert team provides complete, end-to-end guidance—from your very first step until the final submission—to ensure your application is strong, accurate, and presented with confidence.",
    "is there a guarantee": "✅ Yes, we significantly increase your chances of visa approval. Whether you are applying for a US Non-Immigrant Visa or Express Entry to Canada, our expert team provides complete, end-to-end guidance—from your very first step until the final submission—to ensure your application is strong, accurate, and presented with confidence.",
    
    # Programs
    "caregiver program": """📝 All the details about our program will be discussed during the initial briefing and assessment at our office.

\n\n📍 2F Unit 223, One Oasis Hub B, Ortigas Ext, Pasig City
\n\n🗺️ https://maps.app.goo.gl/o2rvHLBcUZhpDJfp8
\n\n🎥 https://vt.tiktok.com/ZSyuUpdN6/
\n\n📞 +63 905-804-4426 or +63 969-251-0672
\n\n📧 state101ortigasbranch@gmail.com
\n\n⏰ Mon-Sat 9AM-5PM""",
    
    "work abroad program": """📝 All the details about our program will be discussed during the initial briefing and assessment at our office.

\n\n📍 2F Unit 223, One Oasis Hub B, Ortigas Ext, Pasig City
\n\n🗺️ https://maps.app.goo.gl/o2rvHLBcUZhpDJfp8
\n\n🎥 https://vt.tiktok.com/ZSyuUpdN6/
\n\n📞 +63 905-804-4426 or +63 969-251-0672
\n\n📧 state101ortigasbranch@gmail.com
\n\n⏰ Mon-Sat 9AM-5PM""",
    
    # Qualifications
    "qualifications": "✅ Open to applicants with or without prior training or experience. Applicants must be willing to undergo training and develop the necessary skills for the program.",
    "what are the qualifications": "✅ Open to applicants with or without prior training or experience. Applicants must be willing to undergo training and develop the necessary skills for the program.",
    
    # Age
    "age limit": "👥 No age limit, provided the applicant is physically capable of performing the required tasks.",
    "age": "👥 No age limit, provided the applicant is physically capable of performing the required tasks.",
    
    # Gender
    "gender": "⚧ Open to all genders.",
    "is there genders required": "⚧ Open to all genders.",
    "gender requirement": "⚧ Open to all genders.",
    
    # Graduates
    "graduates": "🎓 Accepts both graduates and undergraduates.",
    "does it accept graduates only": "🎓 Accepts both graduates and undergraduates.",
    "do you accept undergraduates": "🎓 Accepts both graduates and undergraduates.",
    
    # Appointment Booking
    "appointment": """📅 **To book an appointment**, complete our application form with:
• Full Name
• Email
• Phone
• Age
• Address
• Visa Type (Canadian/American)
• Available Time

Your information is secure and will only be used for visa assessment.

\n\n📍 2F Unit 223, One Oasis Hub B, Ortigas Ext, Pasig City
\n\n🗺️ https://maps.app.goo.gl/o2rvHLBcUZhpDJfp8
\n\n🎥 https://vt.tiktok.com/ZSyuUpdN6/
\n\n📞 +63 905-804-4426 or +63 969-251-0672
\n\n📧 state101ortigasbranch@gmail.com
\n\n⏰ Mon-Sat 9AM-5PM

\n\n✨ We recommend booking an appointment to ensure we can accommodate you promptly!""",
    
    "how can i book": """📅 **To book an appointment**, complete our application form with:
• Full Name
• Email
• Phone
• Age
• Address
• Visa Type (Canadian/American)
• Available Time

Your information is secure and will only be used for visa assessment.

\n\n📍 2F Unit 223, One Oasis Hub B, Ortigas Ext, Pasig City
\n\n🗺️ https://maps.app.goo.gl/o2rvHLBcUZhpDJfp8
\n\n🎥 https://vt.tiktok.com/ZSyuUpdN6/
\n\n📞 +63 905-804-4426 or +63 969-251-0672
\n\n📧 state101ortigasbranch@gmail.com
\n\n⏰ Mon-Sat 9AM-5PM

✨ We recommend booking an appointment to ensure we can accommodate you promptly!""",
    
    "how can i book an appointment": """📅 **To book an appointment**, complete our application form with:
• Full Name
• Email
• Phone
• Age
• Address
• Visa Type (Canadian/American)
• Available Time

Your information is secure and will only be used for visa assessment.

\n\n📍 2F Unit 223, One Oasis Hub B, Ortigas Ext, Pasig City
\n\n🗺️ https://maps.app.goo.gl/o2rvHLBcUZhpDJfp8
\n\n🎥 https://vt.tiktok.com/ZSyuUpdN6/
\n\n📞 +63 905-804-4426 or +63 969-251-0672
\n\n📧 state101ortigasbranch@gmail.com
\n\n⏰ Mon-Sat 9AM-5PM

✨ We recommend booking an appointment to ensure we can accommodate you promptly!""",
    
    "walk in": "✅ Yes, we accept walk-in clients with or without an appointment, but we highly recommend booking an appointment to ensure we can accommodate you promptly.",
    "can i walk in": "✅ Yes, we accept walk-in clients with or without an appointment, but we highly recommend booking an appointment to ensure we can accommodate you promptly.",
    
    # Application Start
    "how can i start my application": """📝 **To get started**, complete our application form with:
• Full Name
• Email
• Phone
• Age
• Address
• Visa Type (Canadian/American)
• Available Time

Your information is secure and will only be used for visa assessment.

📍 **Our Location:**
2F Unit 223, One Oasis Hub B, Ortigas Ext, Pasig City

🗺️ **Google Maps:** https://maps.app.goo.gl/o2rvHLBcUZhpDJfp8

🎥 **Location Guide Video:** https://vt.tiktok.com/ZSyuUpdN6/

📞 **Contact Us:**
+63 905-804-4426 or +63 969-251-0672

📧 **Email:**
state101ortigasbranch@gmail.com

⏰ **Office Hours:**
Monday to Saturday, 9AM-5PM""",
    
    "how can i apply": """📝 **To get started**, complete our application form with:
• Full Name
• Email
• Phone
• Age
• Address
• Visa Type (Canadian/American)
• Available Time

Your information is secure and will only be used for visa assessment.

📍 **Our Location:**
2F Unit 223, One Oasis Hub B, Ortigas Ext, Pasig City

🗺️ **Google Maps:** https://maps.app.goo.gl/o2rvHLBcUZhpDJfp8

🎥 **Location Guide Video:** https://vt.tiktok.com/ZSyuUpdN6/

📞 **Contact Us:**
+63 905-804-4426 or +63 969-251-0672

📧 **Email:**
state101ortigasbranch@gmail.com

⏰ **Office Hours:**
Monday to Saturday, 9AM-5PM""",
    
    # After Submission
    "what happens after": "📞 Expect a call within 24 hours as soon as we can handle your query.",
    "what happens after i submit": "📞 Expect a call within 24 hours as soon as we can handle your query.",
    
    # Application Outside Metro Manila
    "apply outside metro manila": "📍 Yes, we assist clients from all over the Philippines. Our business hours are Mon-Sat 9am to 5pm.",
    "can i apply if im outside": "📍 Yes, we assist clients from all over the Philippines. Our business hours are Mon-Sat 9am to 5pm.",
    "nationwide": "📍 Yes, we assist clients from all over the Philippines. Our business hours are Mon-Sat 9am to 5pm.",
    
    # Application Status
    "application status": "📞 For the status of your application, feel free to contact us on our official numbers: +63 905-804-4426 or +63 969-251-0672.",
    "how do i know the status": "📞 For the status of your application, feel free to contact us on our official numbers: +63 905-804-4426 or +63 969-251-0672.",
    "status of my application": "📞 For the status of your application, feel free to contact us on our official numbers: +63 905-804-4426 or +63 969-251-0672.",
    
    # Job Offers & Placements
    "job offers abroad": "🛂 As of now we only offer non-Immigrant Visa for US and Express Entry and other immigration pathways for Canada. For detailed advice on the current visas we offer please contact us directly at +63 905-804-4426 or +63 969-251-0672.",
    "available job offers": "🛂 As of now we only offer non-Immigrant Visa for US and Express Entry and other immigration pathways for Canada. For detailed advice on the current visas we offer please contact us directly at +63 905-804-4426 or +63 969-251-0672.",
    "job placements": "🛂 As of now we only offer non-Immigrant Visa for US and Express Entry and other immigration pathways for Canada. For detailed advice on the current visas we offer please contact us directly at +63 905-804-4426 or +63 969-251-0672.",
    
    # Partner Agency
    "partner agency": "🏢 No, we are an independent and private company located at our main office in Pasig City, accredited by the Municipality of Pasig.",
    "do you have a partner agency": "🏢 No, we are an independent and private company located at our main office in Pasig City, accredited by the Municipality of Pasig.",
    
    # Families & Couples
    "families or couples": "👨‍👩‍👧 Yes, families and couples can apply together. We highly suggest you visit the application form to begin booking your appointment with us. If you have further questions, feel free to contact us at +63 905-804-4426 or +63 969-251-0672.",
    "can families apply": "👨‍👩‍👧 Yes, families and couples can apply together. We highly suggest you visit the application form to begin booking your appointment with us. If you have further questions, feel free to contact us at +63 905-804-4426 or +63 969-251-0672.",
    
    # Orientation
    "orientation": "🧭 Yes, we are here to orient you with your needs to apply for a Visa to ensure you are fully prepared and understand the process.",
    "is the orientation mandatory": "🧭 Yes, we are here to orient you with your needs to apply for a Visa to ensure you are fully prepared and understand the process.",
    "orientation mandatory": "🧭 Yes, we are here to orient you with your needs to apply for a Visa to ensure you are fully prepared and understand the process.",
    
    "orientation online": """📝 All the details about our program will be discussed during the initial briefing and assessment at our office.

We recommend an appointment before walking in. To schedule an appointment, please fill out our application form.

\n\n📍 2F Unit 223, One Oasis Hub B, Ortigas Ext, Pasig City
\n\n🗺️ https://maps.app.goo.gl/o2rvHLBcUZhpDJfp8
\n\n🎥 https://vt.tiktok.com/ZSyuUpdN6/
\n\n📞 +63 905-804-4426 or +63 969-251-0672
\n\n📧 state101ortigasbranch@gmail.com
\n\n⏰ Mon-Sat 9AM-5PM""",
    
    "can i join the orientation online": """📝 All the details about our program will be discussed during the initial briefing and assessment at our office.

We recommend an appointment before walking in. To schedule an appointment, please fill out our application form.

\n\n📍 2F Unit 223, One Oasis Hub B, Ortigas Ext, Pasig City
\n\n🗺️ https://maps.app.goo.gl/o2rvHLBcUZhpDJfp8
\n\n🎥 https://vt.tiktok.com/ZSyuUpdN6/
\n\n📞 +63 905-804-4426 or +63 969-251-0672
\n\n📧 state101ortigasbranch@gmail.com
\n\n⏰ Mon-Sat 9AM-5PM""",
    
    # What to Bring
    "what to bring": "🧾 Bring the Initial Requirements (Valid passport, 2x2 photo, Training Certificate if available, Diploma if available, Updated Resume). If you have further questions, feel free to contact us for confirmation before your visit.",
    "what should i bring": "🧾 Bring the Initial Requirements (Valid passport, 2x2 photo, Training Certificate if available, Diploma if available, Updated Resume). If you have further questions, feel free to contact us for confirmation before your visit.",
    
    # Reschedule
    "reschedule": "📞 You can contact us directly at +63 905-804-4426 or +63 969-251-0672 to reschedule your orientation.",
    "how can i reschedule": "📞 You can contact us directly at +63 905-804-4426 or +63 969-251-0672 to reschedule your orientation.",
    
    # Other Branches
    "other branches": "🏢 No, we are only located at our Pasig City office. Feel free to contact us for more information regarding the orientation.",
    "do you have orientations in other branches": "🏢 No, we are only located at our Pasig City office. Feel free to contact us for more information regarding the orientation.",
    
    # Fees & Pricing
    "processing fee": """💰 All the details about our program will be discussed during the initial briefing and assessment at our office.

\n\n📍 2F Unit 223, One Oasis Hub B, Ortigas Ext, Pasig City
\n\n🗺️ https://maps.app.goo.gl/o2rvHLBcUZhpDJfp8
\n\n🎥 https://vt.tiktok.com/ZSyuUpdN6/
\n\n📞 +63 905-804-4426 or +63 969-251-0672
\n\n📧 state101ortigasbranch@gmail.com
\n\n⏰ Mon-Sat 9AM-5PM""",
    
    "how much": """💰 All the details about our program will be discussed during the initial briefing and assessment at our office.

📍 2F Unit 223, One Oasis Hub B, Ortigas Ext, Pasig City
🗺️ https://maps.app.goo.gl/o2rvHLBcUZhpDJfp8
🎥 https://vt.tiktok.com/ZSyuUpdN6/
📞 +63 905-804-4426 or +63 969-251-0672
📧 state101ortigasbranch@gmail.com
⏰ Mon-Sat 9AM-5PM""",
    
    "price": """💰 All the details about our program will be discussed during the initial briefing and assessment at our office.

📍 2F Unit 223, One Oasis Hub B, Ortigas Ext, Pasig City
🗺️ https://maps.app.goo.gl/o2rvHLBcUZhpDJfp8
🎥 https://vt.tiktok.com/ZSyuUpdN6/
📞 +63 905-804-4426 or +63 969-251-0672
📧 state101ortigasbranch@gmail.com
⏰ Mon-Sat 9AM-5PM""",
    
    "cost": """💰 All the details about our program will be discussed during the initial briefing and assessment at our office.

📍 2F Unit 223, One Oasis Hub B, Ortigas Ext, Pasig City
🗺️ https://maps.app.goo.gl/o2rvHLBcUZhpDJfp8
🎥 https://vt.tiktok.com/ZSyuUpdN6/
📞 +63 905-804-4426 or +63 969-251-0672
📧 state101ortigasbranch@gmail.com
⏰ Mon-Sat 9AM-5PM""",
    
    # Payment Methods
    "payment methods": """💳 All the details about our program will be discussed during the initial briefing and assessment at our office.

📍 2F Unit 223, One Oasis Hub B, Ortigas Ext, Pasig City
🗺️ https://maps.app.goo.gl/o2rvHLBcUZhpDJfp8
🎥 https://vt.tiktok.com/ZSyuUpdN6/
📞 +63 905-804-4426 or +63 969-251-0672
📧 state101ortigasbranch@gmail.com
⏰ Mon-Sat 9AM-5PM""",
    
    "what payment methods": """💳 All the details about our program will be discussed during the initial briefing and assessment at our office.

📍 2F Unit 223, One Oasis Hub B, Ortigas Ext, Pasig City
🗺️ https://maps.app.goo.gl/o2rvHLBcUZhpDJfp8
🎥 https://vt.tiktok.com/ZSyuUpdN6/
📞 +63 905-804-4426 or +63 969-251-0672
📧 state101ortigasbranch@gmail.com
⏰ Mon-Sat 9AM-5PM""",
    
    # Installment Plans
    "installment plans": """📝 All the details about our program will be discussed during the initial briefing and assessment at our office.

📍 2F Unit 223, One Oasis Hub B, Ortigas Ext, Pasig City
🗺️ https://maps.app.goo.gl/o2rvHLBcUZhpDJfp8
🎥 https://vt.tiktok.com/ZSyuUpdN6/
📞 +63 905-804-4426 or +63 969-251-0672
📧 state101ortigasbranch@gmail.com
⏰ Mon-Sat 9AM-5PM""",
    
    "do you offer installment": """📝 All the details about our program will be discussed during the initial briefing and assessment at our office.

📍 2F Unit 223, One Oasis Hub B, Ortigas Ext, Pasig City
🗺️ https://maps.app.goo.gl/o2rvHLBcUZhpDJfp8
🎥 https://vt.tiktok.com/ZSyuUpdN6/
📞 +63 905-804-4426 or +63 969-251-0672
📧 state101ortigasbranch@gmail.com
⏰ Mon-Sat 9AM-5PM""",
    
    # Hidden Charges
    "hidden charges": """📝 All the details about our program will be discussed during the initial briefing and assessment at our office.

📍 2F Unit 223, One Oasis Hub B, Ortigas Ext, Pasig City
🗺️ https://maps.app.goo.gl/o2rvHLBcUZhpDJfp8
🎥 https://vt.tiktok.com/ZSyuUpdN6/
📞 +63 905-804-4426 or +63 969-251-0672
📧 state101ortigasbranch@gmail.com
⏰ Mon-Sat 9AM-5PM""",
    
    "are there any hidden charges": """📝 All the details about our program will be discussed during the initial briefing and assessment at our office.

📍 2F Unit 223, One Oasis Hub B, Ortigas Ext, Pasig City
🗺️ https://maps.app.goo.gl/o2rvHLBcUZhpDJfp8
🎥 https://vt.tiktok.com/ZSyuUpdN6/
📞 +63 905-804-4426 or +63 969-251-0672
📧 state101ortigasbranch@gmail.com
⏰ Mon-Sat 9AM-5PM""",
    
    # Free Consultation/Training
    "consultation free": """📝 All the details about our program will be discussed during the initial briefing and assessment at our office.

📍 2F Unit 223, One Oasis Hub B, Ortigas Ext, Pasig City
🗺️ https://maps.app.goo.gl/o2rvHLBcUZhpDJfp8
🎥 https://vt.tiktok.com/ZSyuUpdN6/
📞 +63 905-804-4426 or +63 969-251-0672
📧 state101ortigasbranch@gmail.com
⏰ Mon-Sat 9AM-5PM""",
    
    "is the consultation really free": """📝 All the details about our program will be discussed during the initial briefing and assessment at our office.

📍 2F Unit 223, One Oasis Hub B, Ortigas Ext, Pasig City
🗺️ https://maps.app.goo.gl/o2rvHLBcUZhpDJfp8
🎥 https://vt.tiktok.com/ZSyuUpdN6/
📞 +63 905-804-4426 or +63 969-251-0672
📧 state101ortigasbranch@gmail.com
⏰ Mon-Sat 9AM-5PM""",
    
    "are trainings free": """📝 All the details about our program will be discussed during the initial briefing and assessment at our office.

📍 2F Unit 223, One Oasis Hub B, Ortigas Ext, Pasig City
🗺️ https://maps.app.goo.gl/o2rvHLBcUZhpDJfp8
🎥 https://vt.tiktok.com/ZSyuUpdN6/
📞 +63 905-804-4426 or +63 969-251-0672
📧 state101ortigasbranch@gmail.com
⏰ Mon-Sat 9AM-5PM""",
    
    "is there a fee for training": """📝 All the details about our program will be discussed during the initial briefing and assessment at our office.

📍 2F Unit 223, One Oasis Hub B, Ortigas Ext, Pasig City
🗺️ https://maps.app.goo.gl/o2rvHLBcUZhpDJfp8
🎥 https://vt.tiktok.com/ZSyuUpdN6/
📞 +63 905-804-4426 or +63 969-251-0672
📧 state101ortigasbranch@gmail.com
⏰ Mon-Sat 9AM-5PM""",
    
    # Submit Documents/Requirements
    "submit requirements": "📤 Submit your requirements through the Initial Assessment tab with your personal and contact details.",
    "how do i submit": "📤 Submit your requirements through the Initial Assessment tab with your personal and contact details.",
    "submit documents": "📤 Submit your requirements through the Initial Assessment tab with your personal and contact details.",
    
    # Verification & Safety
    "verify consultant": """🔐 To ensure you're dealing with an official member of State101, please note our official details:
• Location: 2F Unit 223, One Oasis Hub B, Ortigas Ext, Pasig City
• Contact Numbers: +63 905-804-4426 or +63 969-251-0672
• Business Hours: Open Mon-Sat 9AM-5PM
• We are officially registered with the Municipality of Pasig.

We recommend verifying through these official channels.""",
    
    "how can i verify": """🔐 To ensure you're dealing with an official member of State101, please note our official details:
• Location: 2F Unit 223, One Oasis Hub B, Ortigas Ext, Pasig City
• Contact Numbers: +63 905-804-4426 or +63 969-251-0672
• Business Hours: Open Mon-Sat 9AM-5PM
• We are officially registered with the Municipality of Pasig.

We recommend verifying through these official channels.""",
    
    "official staff member": """🔐 To ensure you're dealing with an official member of State101, please note our official details:
• Location: 2F Unit 223, One Oasis Hub B, Ortigas Ext, Pasig City
• Contact Numbers: +63 905-804-4426 or +63 969-251-0672
• Business Hours: Open Mon-Sat 9AM-5PM
• We are officially registered with the Municipality of Pasig.

We recommend verifying through these official channels.""",
    
    "how can i make sure im dealing": """🔐 To ensure you're dealing with an official member of State101, please note our official details:
• Location: 2F Unit 223, One Oasis Hub B, Ortigas Ext, Pasig City
• Contact Numbers: +63 905-804-4426 or +63 969-251-0672
• Business Hours: Open Mon-Sat 9AM-5PM
• We are officially registered with the Municipality of Pasig.

We recommend verifying through these official channels.""",
    
    # Social Media
    "social media": "🌐 Yes, you can find our social media links available at the bottom of our Website. Please feel free to check us out and follow us for updates and guides.",
    "do you have facebook": "🌐 Yes, you can find our social media links available at the bottom of our Website. Please feel free to check us out and follow us for updates and guides.",
    "do you have social media": "🌐 Yes, you can find our social media links available at the bottom of our Website. Please feel free to check us out and follow us for updates and guides.",
    
    # Scammers
    "scammers": """⚠️ To ensure you're dealing with an official member of State101, please note our official details:
• Location: 2F Unit 223, One Oasis Hub B, Ortigas Ext, Pasig City
• Contact Numbers: +63 905-804-4426 or +63 969-251-0672
• Business Hours: Open Mon-Sat 9AM-5PM
• We are officially registered with the Municipality of Pasig.

Please only use our official contacts and report any suspicious accounts to us.""",
    
    "encounter scammers": """⚠️ To ensure you're dealing with an official member of State101, please note our official details:
• Location: 2F Unit 223, One Oasis Hub B, Ortigas Ext, Pasig City
• Contact Numbers: +63 905-804-4426 or +63 969-251-0672
• Business Hours: Open Mon-Sat 9AM-5PM
• We are officially registered with the Municipality of Pasig.

Please only use our official contacts and report any suspicious accounts to us.""",
    
    "what should i do if i encounter scammers": """⚠️ To ensure you're dealing with an official member of State101, please note our official details:
• Location: 2F Unit 223, One Oasis Hub B, Ortigas Ext, Pasig City
• Contact Numbers: +63 905-804-4426 or +63 969-251-0672
• Business Hours: Open Mon-Sat 9AM-5PM
• We are officially registered with the Municipality of Pasig.

Please only use our official contacts and report any suspicious accounts to us.""",
    
    # Other Countries
    "other countries": "🌍 We currently don't offer visa assistance to other countries. We offer Non-Immigrant Visa for US and Express Entry and other immigration pathways for Canada.",
    "do you also offer visas to other countries": "🌍 We currently don't offer visa assistance to other countries. We offer Non-Immigrant Visa for US and Express Entry and other immigration pathways for Canada.",
    
    # Greetings
    "hi": "Hi there! 👋 What can I help you with?\n\nYou can ask about:\n\n• Visa types & requirements\n\n• Our location & hours\n\n• How to book an appointment\n\n• Qualifications & eligibility",
    "hello": "Hello! 👋 What can I help you with?\n\nYou can ask about:\n\n• Visa types & requirements\n\n• Our location & hours\n\n• How to book an appointment\n\n• Qualifications & eligibility",
    "hey": "Hey! 👋 What can I help you with?\n\nYou can ask about:\n\n• Visa types & requirements\n\n• Our location & hours\n\n• How to book an appointment\n\n• Qualifications & eligibility",
    "good morning": "Good morning! ☀️ How can I assist you today?",
    "good afternoon": "Good afternoon! 🌤️ How can I assist you today?",
    "good evening": "Good evening! 🌙 How can I assist you today?",
    "greetings": "Hello! 👋 What can I help you with?\n\nYou can ask about:\n\n• Visa types & requirements\n\n• Our location & hours\n\n• How to book an appointment\n\n• Qualifications & eligibility",
    "hola": "¡Hola! 👋 What can I help you with?\n\nYou can ask about:\n\n• Visa types & requirements\n\n• Our location & hours\n\n• How to book an appointment\n\n• Qualifications & eligibility",
    "whats up": "Hey! 👋 What can I help you with?\n\nYou can ask about:\n\n• Visa types & requirements\n\n• Our location & hours\n\n• How to book an appointment\n\n• Qualifications & eligibility",
    "what's up": "Hey! 👋 What can I help you with?\n\n• Visa types & requirements\n\n• Our location & hours\n\n• How to book an appointment\n\n• Qualifications & eligibility",
    "howdy": "Howdy! 👋 What can I help you with?\n\nYou can ask about:\n\n• Visa types & requirements\n\n• Our location & hours\n\n• How to book an appointment\n\n• Qualifications & eligibility",
    "sup": "Hey! 👋 What can I help you with?\n\nYou can ask about:\n\n• Visa types & requirements\n\n• Our location & hours\n\n• How to book an appointment\n\n• Qualifications & eligibility",
    
    # Goodbyes & Farewells
    "bye": "Goodbye! 👋 Thank you for visiting State101 Travel. Feel free to come back anytime if you have more visa questions. We're here to help!",
    "goodbye": "Goodbye! 👋 Thank you for visiting State101 Travel. Feel free to come back anytime if you have more visa questions. We're here to help!",
    "see you": "See you later! 👋 Thanks for chatting with us. Don't hesitate to reach out if you need any visa assistance. We're here for you!",
    "see you later": "See you later! 👋 Thanks for chatting with us. Don't hesitate to reach out if you need any visa assistance. We're here for you!",
    "farewell": "Farewell! 👋 Thank you for visiting State101 Travel. We look forward to helping you with your visa application!",
    "take care": "Take care! 👋 Thanks for visiting State101 Travel. Feel free to reach out anytime. We're here to help!",
    "catch you": "Catch you later! 👋 Thanks for chatting with State101 Travel. Come back soon if you have more questions!",
    "cya": "See ya! 👋 Thanks for visiting. Feel free to come back anytime with your visa questions!",
    "adios": "¡Adiós! 👋 Thank you for visiting State101 Travel. Come back soon if you need help with your visa!",
    "later": "Later! 👋 Thanks for chatting with us. Feel free to reach out anytime for visa assistance!",
    
    # Thanks & Appreciation
    "thanks": "You're welcome! 😊 Is there anything else I can help you with?\n\nYou can ask about:\n\n• Visa types & requirements\n\n• Our location & hours\n\n• How to book an appointment\n\n• Qualifications & eligibility",
    "thank you": "You're welcome! 😊 Is there anything else I can help you with?\n\nYou can ask about:\n\n• Visa types & requirements\n\n• Our location & hours\n\n• How to book an appointment\n\n• Qualifications & eligibility",
    "thx": "You're welcome! 😊 Is there anything else I can help you with?\n\nYou can ask about:\n\n• Visa types & requirements\n\n• Our location & hours\n\n• How to book an appointment\n\n• Qualifications & eligibility",
}

class VisaAssistant:
    def __init__(self):
        self.client = Groq(api_key=st.secrets["GROQ_API_KEY"])
        self.daily_count = 0
        self.last_call = 0
        self.thinking_delay = float(st.secrets.get("THINKING_DELAY_MS", 900)) / 1000.0
        self.strict_mode = bool(st.secrets.get("STRICT_MODE", True))
        self.smart_facts_mode = bool(st.secrets.get("SMART_FACTS_MODE", True))
        self.semantic_enabled = bool(st.secrets.get("SEMANTIC_ROUTER", True))
        self.semantic_threshold = float(st.secrets.get("SEMANTIC_THRESHOLD", 86))
        self.semantic_entries: List[Tuple[str, str]] = []

        self.embedding_enabled = bool(st.secrets.get("EMBEDDING_ROUTER", True))
        self.embedding_threshold = float(st.secrets.get("EMBEDDING_THRESHOLD", 0.58))
        self._embedder = None
        self.embedding_entries: List[Tuple[str, str]] = []
        self.embedding_vectors: List[List[float]] = []
        
        self.rag_enabled = bool(st.secrets.get("RAG_ENABLED", False))
        self.rag_top_k = int(st.secrets.get("RAG_TOP_K", 4))
        self.rag_knowledge_dir = st.secrets.get("KNOWLEDGE_DIR", "knowledge")
        self.rag_chunks: List[Tuple[str, str]] = []
        self.rag_vectors: List[List[float]] = []
        
        self.domain_gating_enabled = bool(st.secrets.get("DOMAIN_GATING_ENABLED", True))
        self.domain_min_len_for_offtopic = int(st.secrets.get("DOMAIN_MIN_LEN_FOR_OFFTOPIC", 6))
        self.domain_embed_threshold = float(st.secrets.get("DOMAIN_EMBED_THRESHOLD", 0.62))

        self.llm_relevance_enabled = bool(st.secrets.get("LLM_RELEVANCE_ENABLED", True))
        self.llm_relevance_model = st.secrets.get("LLM_RELEVANCE_MODEL", "llama-3.3-70b-versatile")
        self.llm_relevance_fail_open = bool(st.secrets.get("LLM_RELEVANCE_FAIL_OPEN", True))
        self._relevance_cache = {}
        self.third_party_guard_enabled = bool(st.secrets.get("THIRD_PARTY_LOCATION_GUARD_ENABLED", True))
        self.third_party_place_terms = [
            "airport", "naia", "terminal", "runway", "jollibee", "mcdo", "mcdonald", "kfc",
            "burger king", "subway", "7-eleven", "7 eleven", "mall", "sm", "robinsons", "megammall", "mega mall",
            "market", "supermarket", "groceries", "pharmacy", "drugstore", "hospital", "clinic", "hotel", "resort",
            "bank", "atm", "police station", "station", "university", "school", "church", "park"
        ]
        self._us_reference_markers = [
            "state101", "state 101", "your office", "your location", "your address", "office address",
            "where are you", "where is your office", "visit your office", "go to your office"
        ]
        
        self.relevant_keywords = [
            "visa", "travel", "passport", "appointment", "requirements", 
            "canada", "canadian", "america", "american", "us", "usa",
            "application", "processing", "state101", "state 101",
            "consultation", "documentation", "embassy", "interview",
            "tourist", "business", "student", "work permit", "immigration",
            "fee", "cost", "price", "hours", "location", "contact", "website", "webpage",
            "eligibility", "qualification", "denial", "approval",
            "urgent", "status", "track", "form", "apply", "b1", "choose", "benefits", "offerings"
        ]
        
        self.offtopic_keywords = [
            "calculator", "code", "program", "recipe", "cook", "game",
            "movie", "song", "weather", "sports", "stock", "crypto",
            "math", "solve", "equation", "homework", "essay", "write a story"
        ]

        self.intent_synonyms = {
            "location": [
                "where are you", "where are you located", "where is your office",
                "office address", "address", "location", "map", "directions",
                "find you", "tiktok", "tiktok location", "tiktok video", "google map"
            ],
            "hours": ["hours", "opening hours", "business hours", "schedule", "open time", "what time"],
            "contact": ["contact", "phone", "phone number", "call you", "email", "email address"],
            "website": ["website", "web site", "web page", "webpage", "website page"],
            "services": ["services", "what services", "services do you offer"],
            "legit": ["legit", "legitimacy", "is your company legit"],
            "visa type": ["visa type", "what type of visa", "what types of visas"],
            "qualifications": ["qualifications", "qualification", "what are the qualifications"],
            "requirements": ["requirements", "documents", "needed documents", "prepare"],
            "appointment": ["appointment", "book", "schedule appointment"],
            "greeting": [
                "hi", "hello", "hey", "good morning", "good afternoon", "good evening",
                "greetings", "hola", "what's up", "whats up", "howdy", "sup"
            ],
            "goodbye": [
                "bye", "goodbye", "see you", "farewell", "take care", "catch you",
                "see you later", "later", "cya", "adios", "thanks", "thank you", "thx"
            ],
        }
        
        if self.semantic_enabled:
            self._build_semantic_index()
        if self.embedding_enabled:
            self._build_embedding_index()
        if self.rag_enabled:
            self._build_rag_index()

    def _build_semantic_index(self):
        entries: List[Tuple[str, str]] = []
        for intent, syns in self.intent_synonyms.items():
            for s in syns:
                entries.append((intent, s))
        for key in HARDCODED_RESPONSES.keys():
            entries.append((key, key))
        seen = set()
        deduped: List[Tuple[str, str]] = []
        for intent, text in entries:
            t = text.strip().lower()
            if t and t not in seen:
                seen.add(t)
                deduped.append((intent, text))
        self.semantic_entries = deduped

    def _import_fastembed(self):
        try:
            if _FASTEMBED_TEXTEMBEDDING is not None:
                return _FASTEMBED_TEXTEMBEDDING
        except NameError:
            pass
        try:
            mod = importlib.import_module("fastembed")
            TextEmbedding = getattr(mod, "TextEmbedding")
            return TextEmbedding
        except Exception:
            return None

    def _l2_normalize(self, vec: List[float]) -> List[float]:
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]

    def _build_embedding_index(self):
        TextEmbedding = self._import_fastembed()
        if TextEmbedding is None:
            self.embedding_enabled = False
            return
        try:
            self._embedder = TextEmbedding()
            entries: List[Tuple[str, str]] = []
            for intent, syns in self.intent_synonyms.items():
                for s in syns:
                    entries.append((intent, s))
            for key in HARDCODED_RESPONSES.keys():
                entries.append((key, key))
            seen = set()
            deduped: List[Tuple[str, str]] = []
            for intent, text in entries:
                t = text.strip().lower()
                if t and t not in seen:
                    seen.add(t)
                    deduped.append((intent, text))
            self.embedding_entries = deduped
            texts = [t for _, t in self.embedding_entries]
            vectors = list(self._embedder.embed(texts))
            self.embedding_vectors = [self._l2_normalize(list(v)) for v in vectors]
        except Exception:
            self.embedding_enabled = False

    def _list_knowledge_files(self) -> List[Path]:
        base = Path(self.rag_knowledge_dir)
        if not base.exists() or not base.is_dir():
            return []
        exts = {".md", ".txt"}
        files: List[Path] = []
        for p in base.rglob("*"):
            if p.is_file() and p.suffix.lower() in exts:
                files.append(p)
        return files

    def _read_text_file(self, p: Path) -> str:
        try:
            return p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            try:
                return p.read_text(errors="ignore")
            except Exception:
                return ""

    def _chunk_text(self, text: str, source: str, chunk_size: int = 900, overlap: int = 150) -> List[Tuple[str, str]]:
        chunks: List[Tuple[str, str]] = []
        t = text.strip()
        if not t:
            return chunks
        start = 0
        n = len(t)
        while start < n:
            end = min(n, start + chunk_size)
            chunk = t[start:end]
            chunks.append((source, chunk))
            if end == n:
                break
            start = max(end - overlap, start + 1)
        return chunks

    def _build_rag_index(self):
        files = self._list_knowledge_files()
        if not files:
            self.rag_enabled = False
            return
        chunks: List[Tuple[str, str]] = []
        for f in files:
            txt = self._read_text_file(f)
            chunks.extend(self._chunk_text(txt, source=str(f)))
        cleaned: List[Tuple[str, str]] = []
        seen = set()
        for src, ch in chunks:
            c = ch.strip()
            if len(c) < 40:
                continue
            key = (src, c[:80])
            if key in seen:
                continue
            seen.add(key)
            cleaned.append((src, c))
        self.rag_chunks = cleaned

        TextEmbedding = self._import_fastembed()
        if TextEmbedding is None:
            self.rag_vectors = []
            return
        try:
            embedder = TextEmbedding()
            texts = [c for _, c in self.rag_chunks]
            vecs = list(embedder.embed(texts))
            self.rag_vectors = [self._l2_normalize(list(v)) for v in vecs]
        except Exception:
            self.rag_vectors = []

    def _cosine_sim(self, a: List[float], b: List[float]) -> float:
        return sum(x*y for x, y in zip(a, b))

    def _normalize(self, text: str) -> str:
        return re.sub(r'[^\w\s]', '', text.lower()).strip()

    def match_intent(self, prompt: str) -> str | None:
        norm = self._normalize(prompt)
        for key, synonyms in self.intent_synonyms.items():
            for s in synonyms:
                s_norm = self._normalize(s)
                pattern = r"\b" + re.escape(s_norm) + r"\b"
                if re.search(pattern, norm):
                    return key
        return None

    def get_canonical_response(self, intent: str) -> str | None:
        if intent in HARDCODED_RESPONSES:
            return HARDCODED_RESPONSES[intent]
        mapping = {
            "location": "location",
            "hours": "hours",
            "contact": "contact",
            "website": "website",
            "services": "services",
            "legit": "legit",
            "visa type": "visa type",
            "qualifications": "qualifications",
            "requirements": "requirements",
            "appointment": "appointment",
            "greeting": "hello",
            "goodbye": "goodbye",
        }
        key = mapping.get(intent)
        if key and key in HARDCODED_RESPONSES:
            return HARDCODED_RESPONSES[key]
        return None

    def semantic_route(self, prompt: str) -> str | None:
        if not self.semantic_enabled:
            return None
        norm_prompt = self._normalize(prompt)
        best_intent = None
        best_score = -1.0
        for intent, phrase in self.semantic_entries:
            score = fuzz.token_set_ratio(norm_prompt, self._normalize(phrase))
            if score > best_score:
                best_score = score
                best_intent = intent
        if best_score >= self.semantic_threshold and best_intent:
            return self.get_canonical_response(best_intent)
        return None

    def embed_route(self, prompt: str) -> str | None:
        if not self.embedding_enabled or not self._embedder or not self.embedding_vectors:
            return None
        try:
            q_vec = list(self._embedder.embed([prompt]))[0]
            q_vec = self._l2_normalize(list(q_vec))
            best_idx = -1
            best_score = -1.0
            for i, v in enumerate(self.embedding_vectors):
                score = sum(a*b for a, b in zip(q_vec, v))
                if score > best_score:
                    best_score = score
                    best_idx = i
            if best_idx >= 0 and best_score >= self.embedding_threshold:
                intent = self.embedding_entries[best_idx][0]
                return self.get_canonical_response(intent)
        except Exception:
            return None
        return None

    def fuzzy_fact_match(self, prompt: str) -> str | None:
        tokens = set(self._normalize(prompt).split())
        topic_keywords = {
            "location": {"address", "map", "directions", "office", "tiktok", "location"},
            "hours": {"hours", "open", "opening", "schedule", "time"},
            "contact": {"contact", "phone", "call", "email", "mail"},
            "services": {"services", "offer", "provide"},
            "requirements": {"requirements", "documents", "needed", "prepare"},
            "appointment": {"appointment", "book", "schedule"},
        }
        best_key = None
        best_score = 0
        for key, kws in topic_keywords.items():
            score = len(tokens & kws)
            if score > best_score:
                best_score = score
                best_key = key
        if best_score >= 2:
            return best_key
        return None

    def is_relevant_query(self, prompt):
        if not self.domain_gating_enabled:
            return True
        normalized_prompt = prompt.lower()
        for keyword in self.offtopic_keywords:
            if keyword in normalized_prompt:
                return False
        greetings = ["hi", "hello", "hey", "good morning", "good afternoon", "good evening"]
        tokens = normalized_prompt.split()
        if any(g in normalized_prompt for g in greetings) and len(tokens) <= 3:
            return True
        has_relevant_keyword = any(keyword in normalized_prompt for keyword in self.relevant_keywords)
        if not has_relevant_keyword and len(tokens) >= self.domain_min_len_for_offtopic:
            return False
        return True

    def check_query_relevance(self, prompt: str) -> bool:
        try:
            cache_key = self._normalize(prompt)
            if cache_key in self._relevance_cache:
                return self._relevance_cache[cache_key]
            relevance_system = (
                "You are a strict query filter for State101 Travel (US/Canada visa assistance). "
                "Output exactly one token: RELEVANT or OFFTOPIC."
            )
            content = (
                "Decide if the following query is about State101 Travel or US/Canada visa assistance.\n"
                "- RELEVANT: visas, requirements, documents, services, location, hours, contact, appointments, pricing, qualifications.\n"
                "- OFFTOPIC: food, entertainment, coding, math, general knowledge, other businesses.\n\n"
                f"User query: \"{prompt}\"\n\n"
                "Answer: RELEVANT or OFFTOPIC"
            )
            resp = self.client.chat.completions.create(
                model=self.llm_relevance_model,
                messages=[
                    {"role": "system", "content": relevance_system},
                    {"role": "user", "content": content},
                ],
                temperature=0.1,
                max_tokens=6,
            )
            label = (resp.choices[0].message.content or "").strip().upper()
            is_rel = label.startswith("RELEVANT") and "OFFTOPIC" not in label
            if len(self._relevance_cache) > 500:
                self._relevance_cache.clear()
            self._relevance_cache[cache_key] = is_rel
            return is_rel
        except Exception:
            return True if self.llm_relevance_fail_open else False

    @sleep_and_retry
    @limits(calls=10, period=60)
    def generate(self, prompt):
        try:
            if len(prompt.split()) > 2:
                lang = detect(prompt)
                if lang != "en":
                    prompt = GoogleTranslator(source=lang, target="en").translate(prompt)
        except:
            pass

        try:
            time.sleep(self.thinking_delay)
        except Exception:
            pass

        # Relevance check
        if self.third_party_guard_enabled:
            text = prompt.lower()
            mentions_third_party = any(t in text for t in self.third_party_place_terms)
            refers_to_us = any(m in text for m in self._us_reference_markers)
            if mentions_third_party and not refers_to_us:
                return "😊 I specialize in State101 Travel's US and Canada visa services. Please ask about visa requirements, our process, appointments, or contact info."

        if self.llm_relevance_enabled:
            if not self.check_query_relevance(prompt):
                return "😊 I specialize in State101 Travel's US and Canada visa services. How can I help you with your visa application?"
        else:
            if not self.is_relevant_query(prompt):
                return "😊 I specialize in State101 Travel's US and Canada visa services. How can I help you with your visa application?"

        # Intent matching
        intent = self.match_intent(prompt)
        if intent:
            canonical = self.get_canonical_response(intent)
            if canonical:
                return canonical

        # Semantic routing
        sem_answer = self.semantic_route(prompt)
        if sem_answer:
            return sem_answer

        # Embedding routing
        emb_answer = self.embed_route(prompt)
        if emb_answer:
            return emb_answer

        # Fuzzy matching
        fuzzy_intent = self.fuzzy_fact_match(prompt)
        if fuzzy_intent:
            canonical = self.get_canonical_response(fuzzy_intent)
            if canonical:
                return canonical

        # Default response
        return "😊 I specialize in State101 Travel's US and Canada visa services. How can I help you today?"

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

# ========== VALIDATION HELPERS ==========
def _is_valid_email(addr: str) -> Tuple[bool, str | None]:
    """Validate email format (syntax only, no DNS) returning (ok, error_message)."""
    try:
        validate_email(addr, check_deliverability=False)
        return True, None
    except EmailNotValidError as e:
        return False, e.title or str(e)

def _validate_ph_phone(num: str) -> Tuple[bool, str | None]:
    """Validate Philippine phone number. Accepts 09XXXXXXXXX or +639XXXXXXXXX.
    Returns (is_valid, e164_or_none)."""
    if not num:
        return False, None
    # Strip obvious formatting characters
    raw = re.sub(r"[\s()-]", "", num)
    # If it starts with 09 convert to +639 for parsing consistency
    if raw.startswith("09") and len(raw) == 11:
        raw = "+63" + raw[1:]
    try:
        parsed = phonenumbers.parse(raw, "PH")
    except Exception:
        return False, None
    if phonenumbers.is_valid_number_for_region(parsed, "PH"):
        e164 = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        return True, e164
    return False, None

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
        st.markdown("#### Upload your Requirements (optional)")
        uploads = st.file_uploader(
            "Upload any available requirements (e.g., passport, photo, certificates, Resume, Diploma)",
            accept_multiple_files=True,
            type=["pdf", "jpg", "jpeg", "png", "heic", "heif", "doc", "docx", "rtf", "txt"],
            help="Optional but recommended. Allowed formats: PDF, JPG, JPEG, PNG, HEIC/HEIF, DOC/DOCX, RTF, TXT."
        )

        # State flags for modal flow
        if "trigger_no_uploads_modal" not in st.session_state:
            st.session_state.trigger_no_uploads_modal = False
        if "no_uploads_confirmed" not in st.session_state:
            st.session_state.no_uploads_confirmed = False
        if "pending_form_payload" not in st.session_state:
            st.session_state.pending_form_payload = None

        submitted = st.form_submit_button("Submit Application")
        if submitted:
            if not all([full_name, email, phone, address]):
                st.error("Please fill all required fields (*)")
            else:
                # Email validation
                ok_email, email_err_msg = _is_valid_email(email)
                if not ok_email:
                    st.error(f"Please enter a valid email address: {email_err_msg}")
                    return
                # Phone validation
                ok_phone, phone_e164 = _validate_ph_phone(phone)
                if not ok_phone:
                    st.error("Please enter a valid Philippine phone number (e.g., 09XXXXXXXXX or +639XXXXXXXXXX)")
                    return
                # If no uploads: first attempt triggers modal; subsequent attempt with confirmed flag proceeds
                if (not uploads or len(uploads) == 0) and not st.session_state.no_uploads_confirmed:
                    # Preserve the form data so we can reuse after confirmation
                    st.session_state.pending_form_payload = {
                        "full_name": full_name,
                        "email": email,
                        "phone": phone_e164 or phone,
                        "age": age,
                        "address": address,
                        "visa_type": visa_type,
                        "preferred_day": day_of_week,
                        "available_time": available_time,
                    }
                    st.session_state.trigger_no_uploads_modal = True
                    st.info("Please confirm you want to submit without uploading any requirements.")
                    # Rerun so the modal (outside the form) renders immediately in this cycle
                    st.rerun()
                # Normalize stored phone to E.164 format
                phone = phone_e164 or phone
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

                # Enforce allowed file types server-side as a defense-in-depth
                allowed_exts = {"pdf", "jpg", "jpeg", "png", "heic", "heif", "doc", "docx", "rtf", "txt"}
                uploaded_files = []
                skipped_files = []
                for uf in (uploads or []):
                    name = getattr(uf, "name", "") or ""
                    ext = str(Path(name).suffix).lower().lstrip(".")
                    if ext in allowed_exts:
                        uploaded_files.append(uf)
                    else:
                        skipped_files.append(name or "(unnamed)")
                if skipped_files:
                    st.info(f"These files were skipped due to unsupported type: {', '.join(skipped_files)}")

                email_ok = False
                sheet_ok = False
                drive_ok = False
                drive_link = None
                email_err = None
                sheet_err = None
                drive_err = None

                # Try Google Drive backup (subfolder + files) first to capture link
                try:
                    drive_link = upload_to_drive(form_payload, uploaded_files)
                    drive_ok = True
                except Exception as e:
                    drive_ok = False
                    drive_err = str(e)

                # Try send email (include drive link if available)
                try:
                    send_application_email(form_payload, uploaded_files, drive_folder_url=drive_link)
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

    # Outside the form: handle modal confirmation and final submission without uploads
    # If confirmation granted and we have a pending payload, finalize submission without uploads FIRST
    if st.session_state.get("no_uploads_confirmed") and st.session_state.get("pending_form_payload"):
        form_payload = st.session_state.pending_form_payload
        # Clear flags to avoid duplicate submissions on rerun
        st.session_state.no_uploads_confirmed = False
        st.session_state.pending_form_payload = None
        st.session_state.trigger_no_uploads_modal = False

        email_ok = False
        sheet_ok = False
        drive_ok = False
        drive_link = None
        email_err = None
        sheet_err = None
        drive_err = None
        uploaded_files = []  # intentionally empty

        try:
            drive_link = upload_to_drive(form_payload, uploaded_files)
            drive_ok = True
        except Exception as e:
            drive_ok = False
            drive_err = str(e)
        try:
            send_application_email(form_payload, uploaded_files, drive_folder_url=drive_link)
            email_ok = True
        except Exception as e:
            email_ok = False
            email_err = str(e)

        sheet_row = [
            form_payload["full_name"],
            form_payload["email"],
            form_payload["phone"],
            str(form_payload["age"]),
            form_payload["address"],
            form_payload["visa_type"],
            form_payload.get("preferred_day", ""),
            form_payload["available_time"],
            time.strftime("%Y-%m-%d %H:%M"),
            drive_link or "",
        ]
        try:
            sheet_ok = save_to_sheet(sheet_row)
        except Exception as e:
            sheet_ok = False
            sheet_err = str(e)

        if email_ok or sheet_ok or drive_ok:
            st.success("✅ Application submitted without uploads. You can send documents later.")
        else:
            st.error("❌ We couldn't submit your application due to a temporary issue. Please try again or contact us directly.")

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
                })
        if debug:
            if not email_ok and email_err:
                st.info(f"Email error: {email_err}")
            if not drive_ok and drive_err:
                st.info(f"Drive error: {drive_err}")

    # Otherwise, if a modal is requested, open it or show themed fallback prompt
    elif st.session_state.get("trigger_no_uploads_modal"):
        # If dialog feature exists, open it; else provide inline fallback prompt with buttons
        if _DIALOG_DECORATOR:
            _no_uploads_modal()
        else:
            # Theme-aware inline fallback matching chatbot UI
            theme_name = st.session_state.get("theme", "White")
            theme = COLOR_THEMES.get(theme_name, COLOR_THEMES["White"])
            accent = theme.get("accent", "#DC143C")
            secondary = theme.get("secondary", "#F5F5F5")
            text_color = theme.get("text", "#000000")

            st.markdown(
                f"""
                <div style="padding:10px 12px; background:{secondary}; color:{text_color};
                            border-left:4px solid {accent}; border-radius:6px; font-weight:600; margin-bottom:10px;">
                    <div style=\"color:#b00020; font-weight:700;\">Note: this can help us improve efficiency</div>
                </div>
                <div style="margin:6px 0 12px 0; color:{text_color}; font-weight:600;">
                    Are you sure you don't want to upload any requirements yet?
                </div>
                """,
                unsafe_allow_html=True,
            )
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Yes, submit without uploads", key="fallback_yes_submit", use_container_width=True):
                    st.session_state.no_uploads_confirmed = True
                    st.session_state.trigger_no_uploads_modal = False
                    st.rerun()
            with c2:
                if st.button("No, I'll upload files", key="fallback_no_cancel", use_container_width=True):
                    st.session_state.no_uploads_confirmed = False
                    st.session_state.trigger_no_uploads_modal = False
                    st.session_state.pending_form_payload = None
                    st.rerun()

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
        
        st.markdown("""## 📝 Terms and Conditions""")
        
        # Structured Terms and Conditions
        with st.container():
            st.markdown("""
            
            ###### By using State101 Travel Chatbot, you agree to the following terms and conditions. Please read the followings carefully:
            """)
            
            # Section 1
            with st.expander("**1. General Disclaimer**", expanded=True):
                st.markdown("""
                The chatbot is for information and initial consultation only. The information it provides is not legal advice and should not replace a formal consultation with a qualified professional. To get personalized guidance and move forward with any application, you must book an official appointment with our team.
                """)
            
            # Section 2
            with st.expander("**2. Personal Data**"):
                st.markdown("""
                Any personal data you provide, including through the Application Form, is handled securely. It will be used solely to help with your visa assistance and consultation. We use strict validation rules to ensure all information is complete and correctly formatted.
                """)
            
            # Section 3
            with st.expander("**3. Chatbot Functionality**"):
                st.markdown("""
                The chatbot is designed to provide a seamless experience with several key functions:

                • **Conversational Assistant**: You can ask questions about Canadian and American visas, and your chat history is saved for you to review.
                
                • **Language Support**: Can detect and translate non-English messages to improve communication accuracy.
                
                • **AI-Powered Responses**: While many common questions have pre-set answers for consistency, the chatbot can also use AI to give more detailed responses to complex queries.
                
                • **Fallback Logic**: In case of technical issues, the chatbot will provide a friendly notification and our contact information. It also uses rate limiting to prevent excessive requests and maintain service stability.
                
                • **Session Management**: The chatbot remembers your interactions and agreements within a single session, so you won't lose your chat history or have to re-agree to the terms if you refresh the page.
                """)
            
            # Section 4
            with st.expander("**4. Limitation of Liability**"):
                st.markdown("""
                State101 Travel is not liable for any direct or indirect damages resulting from the use of the chatbot. This includes but isn't limited to visa application rejections, delays, or any loss of income or travel plans.
                """)
            
            # Section 5
            with st.expander("**5. Changes to Terms**"):
                st.markdown("""
                We reserve the right to update these terms at any time. Any significant changes will be communicated to our clients. By continuing to use the chatbot, you agree to the latest version of these terms.
                """)
        
        st.markdown("---")
        
        # Agreement Section - Clean and Professional Design
        st.markdown("""
        <style>
        .agreement-container {
            background-color: #f8f9fa;
            border-radius: 10px;
            padding: 15px;
            border: 1px solid #e0e0e0;
            margin: 10px 0;
            text-align: center;
        }
        .agreement-message {
            font-weight: 600;
            color: #555;
            margin-bottom: 25px;
            font-size: 1.1rem;
        }
        .stButton>button {
            background-color: #6c757d !important;
            color: white !important;
            border: none;
            border-radius: 6px;
            padding: 0.5rem 2rem;
            font-weight: 600;
            transition: all 0.2s ease;
        }
        .stButton>button:hover {
            background-color: #5a6268 !important;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        </style>
        """, unsafe_allow_html=True)
        
        # Agreement container with content inside
        st.markdown(
            '''
            <div class="agreement-container">
                <div class="agreement-message">
                    Please accept the Terms and Conditions to continue using State101 Travel Chatbot
                </div>
            </div>
            ''', 
            unsafe_allow_html=True
        )
        
        # Single Agree button centered
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button("Agree to Terms", use_container_width=True, type="primary"):
                st.session_state.agreed = True
                # Add welcome message to chat history when user agrees
                st.session_state.messages = [{
                    "role": "assistant", 
                    "content": "Hello! 👋 Welcome to State101 Travel. How can I help you today? Feel free to ask about visa requirements, application process, our location, and etc.!"
                }]
                st.rerun()
        
        # Stop execution if not agreed
        st.stop()

    # Rest of your main function continues here...
    # Apply selected theme after agreement
    apply_theme(st.session_state.theme)
    
    # Theme toggle button
    current_theme = st.session_state.theme
    toggle_icon = COLOR_THEMES[current_theme]["icon"]
    
    # Create columns for logo, title, and toggle button
    col_logo, col_title, col_toggle = st.columns([1, 5, 1])

    with col_logo:
        if logo_path.exists():
            st.image(str(logo_path), use_container_width=True)
        else:
            st.markdown("<div style='font-size:46px'>🛂</div>", unsafe_allow_html=True)

    with col_title:
        st.title("State101 Travel Chatbot")
        st.caption("Specializing in US and Canada Visa Applications")

    with col_toggle:
        if st.button(toggle_icon, key="theme_toggle_button"):
            st.session_state.theme = "Black" if st.session_state.theme == "White" else "White"
            st.rerun()

    # Remove sidebar and center content
    st.markdown(
        """
        <style>
            [data-testid=stSidebar], .css-1d391kg { display: none !important; }
            .block-container {
                max-width: 900px;
                margin-left: auto;
                margin-right: auto;
                padding-left: 1.25rem !important;
                padding-right: 1.25rem !important;
            }
            @media (max-width: 640px) {
                .block-container { 
                    max-width: 100%; 
                    padding-left: 0.75rem !important; 
                    padding-right: 0.75rem !important; 
                }
            }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Initialize chatbot only after terms are accepted
    if "chatbot" not in st.session_state and st.session_state.agreed:
        st.session_state.chatbot = VisaAssistant()
    if "messages" not in st.session_state:
        st.session_state.messages = [{
            "role": "assistant", 
            "content": "Hello! 👋 Welcome to State101 Travel. How can I help you today? Feel free to ask about visa requirements, application process, our location, and etc.!"
        }]
    
    # Website link in a more compact container
    st.markdown("""
    <style>
    .website-container {
        background-color: #f0f8ff;
        border-radius: 10px;
        padding: 6px 10px;
        border: 1px solid #b8daff;
        margin: 6px 0;
        text-align: center;
    }
    .website-message {
        font-weight: 500;
        color: #004085;
        font-size: 0.9rem;
        line-height: 1.2;
    }
    </style>
    """, unsafe_allow_html=True)
    
    st.markdown(
        '''
        <div class="website-container">
            <div class="website-message">
                To apply, visit our Application Form at our website or click this link: 
                <a href="https://state101-travel-website.vercel.app/services" target="_blank" style="color: #0066cc; text-decoration: none; font-weight: bold;">
                    Application Form
                </a>
            </div>
        </div>
        ''', 
        unsafe_allow_html=True
    )
    
    # Single Chat Assistant tab only
    st.header("Chat Assistant")

    chat_container = st.container()
    with chat_container:
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
    
    st.markdown("<br>" * 2, unsafe_allow_html=True)
    user_prompt = st.chat_input("Ask about US and Canada visas...")
    
    if user_prompt:
        st.session_state.messages.append({"role": "user", "content": user_prompt})
        bot_response = st.session_state.chatbot.generate(user_prompt)
        st.session_state.messages.append({"role": "assistant", "content": bot_response})
        st.rerun()

if __name__ == "__main__":
    main()

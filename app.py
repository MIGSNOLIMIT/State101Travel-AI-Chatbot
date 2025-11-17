import streamlit as st
import time
import re
from groq import Groq
from ratelimit import limits, sleep_and_retry
from pathlib import Path
from langdetect import detect
from deep_translator import GoogleTranslator
from typing import List, Tuple
from rapidfuzz import fuzz
import importlib
import math
import requests
import json
import hashlib
import textwrap
try:
    # Optional top-level import so it's visible in the file header when installed
    # Falls back gracefully if the package isn't present
    from fastembed import TextEmbedding as _FASTEMBED_TEXTEMBEDDING
except Exception:
    _FASTEMBED_TEXTEMBEDDING = None

# ========== SYSTEM PROMPT ==========
SYSTEM_PROMPT = """You are the State101 Chatbot, the official AI assistant for State101Travel specializing in US/Canada visa assistance. Your role is to:

1. **Information Provider**:
   - Clearly explain Canadian Visa and American visa processes
   - Provide requirements and services information when asked
   - Share business hours (Mon-Sat 9AM-5PM), location, and contact details

2. **Application & Requirements**:
   - Direct users to the website for the application form and requirements: https://state101-travel-website.vercel.app/services
   - The website has all the detailed requirements and application forms

3. **Response Rules**:
   - For requirements/questions in HARDCODED_RESPONSES, use ONLY those exact answers
   - For complex queries (case-specific, application status, urgent matters):
     "🔍 For detailed advice, please contact us directly:
      📞 +63 905-804-4426 or +63 969-251-0672
      📧 state101ortigasbranch@gmail.com
      ⏰ Mon-Sat 9AM-5PM"

4. **Key Talking Points**:
   - Always emphasize: "We recommend an appointment before walking in."
   - Direct users to https://state101-travel-website.vercel.app/services for applications and requirements

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
    - If requested information is not present in HARDCODED_RESPONSES, reply that the information isn't available and direct the user to contact via the official phones/email or visit https://state101-travel-website.vercel.app/services.
"""

# ========== HARDCODED RESPONSES ==========
HARDCODED_RESPONSES = {
    # Core information
    "requirements": """🛂 **Visa Requirements**:
- Valid passport (Photocopy)
- 2x2 photo (white background)
- Training Certificate (if available)
- Diploma (Photocopy if available)
- Updated Resume
- Other supporting documents may be discussed during your assessment.""",
    "appointment": "📅 We accept walk-in clients with or without an appointment, but we highly recommend booking an appointment first to ensure we can accommodate you promptly.",
    "hours": "🕘 Open Monday to Saturday, 9:00 AM to 5:00 PM.",
    "business hours": "🕘 We're open Monday to Saturday, 9:00 AM to 5:00 PM.",
    "opportunities": "💼 B1 Visa includes a 6-month care-giving training program with our partner homecare facilities in the US.",
    "located": "📍 2F Unit 223, One Oasis Hub B, Ortigas Ext, Pasig City\n\n🗺️ Find us here: https://maps.app.goo.gl/o2rvHLBcUZhpDJfp8\n\n🎥 Location guide video: https://vt.tiktok.com/ZSyuUpdN6/",
    "map": "📍 2F Unit 223, One Oasis Hub B, Ortigas Ext, Pasig City\n\n🗺️ Find us here: https://maps.app.goo.gl/o2rvHLBcUZhpDJfp8\n\n🎥 Location guide video: https://vt.tiktok.com/ZSyuUpdN6/",
    "location": "📍 2F Unit 223, One Oasis Hub B, Ortigas Ext, Pasig City\n\n🗺️ Find us here: https://maps.app.goo.gl/o2rvHLBcUZhpDJfp8\n\n🎥 Location guide video: https://vt.tiktok.com/ZSyuUpdN6/",
    "website": "🌐 Official Website: https://state101-travel-website.vercel.app/\n\nFor appointments and quick assistance, you can also contact us:\n📞 +63 905-804-4426 or +63 969-251-0672\n📧 state101ortigasbranch@gmail.com\n🗺️ Map: https://maps.app.goo.gl/o2rvHLBcUZhpDJfp8",
    "processing time": "⏳ Standard processing takes 2-4 weeks. Expedited services may be available.",
    "complex": "🔍 For case-specific advice, please contact our specialists directly:\n📞 0961 084 2538\n📧 state101ortigasbranch@gmail.com",
    "status": "🔄 For application status updates, please email us with your reference number or contact us at +63 905-804-4426 / +63 969-251-0672.",
    "urgent": "⏰ For urgent concerns, call us at +63 905-804-4426 or +63 969-251-0672 during business hours.",
    "contact": "📞 You can contact us directly: +63 905-804-4426 or +63 969-251-0672\n📧 state101ortigasbranch@gmail.com",
    
    # Pricing and payments
    "how much": "💰 All the details about our program will be discussed during the initial briefing and assessment at our office.",
    "price": "💰 All the details about our program will be discussed during the initial briefing and assessment at our office.",
    "cost": "💰 All the details about our program will be discussed during the initial briefing and assessment at our office.",
    "fee": "💰 All the details about our program will be discussed during the initial briefing and assessment at our office.",
    "payment": "💳 All the details about our program will be discussed during the initial briefing and assessment at our office.",
    "payment options": "💳 All the details about our program will be discussed during the initial briefing and assessment at our office.",
    "pay": "💳 All the details about our program will be discussed during the initial briefing and assessment at our office.",

    # Legitimacy
    "legit": "✅ Yes, our company is 100% legitimate. We’re officially registered and have a permit to operate issued by the Municipality of Pasig.",
    "is your company legit": "✅ Yes, our company is 100% legitimate. We’re officially registered and have a permit to operate issued by the Municipality of Pasig.",

    # Services (updated to include Canada)
    "services": "🛂 We provide full assistance with US and Canada visa applications and processing.",
    "what services do you offer": "🛂 We provide full assistance with US and Canada visa applications and processing.",

    # Other countries
    "other countries": "🌍 We currently don’t offer visa assistance for other countries. Our services are focused on US and Canada visa processing.",
    "do you also offer visas to other countries": "🌍 We currently don’t offer visa assistance for other countries. Our services are focused on US and Canada visa processing.",

    # Program details and FAQs that redirect to briefing
    "program details": "📝 All the details about our program will be discussed during the initial briefing and assessment at our office.",
    "details of your program": "📝 All the details about our program will be discussed during the initial briefing and assessment at our office.",
    "are trainings free": "📝 All the details about our program will be discussed during the initial briefing and assessment at our office.",
    "is orientation free": "📝 All the details about our program will be discussed during the initial briefing and assessment at our office.",
    "installment plans": "📝 All the details about our program will be discussed during the initial briefing and assessment at our office.",
    "hidden charges": "📝 All the details about our program will be discussed during the initial briefing and assessment at our office.",
    "consultation free": "📝 All the details about our program will be discussed during the initial briefing and assessment at our office.",

    # Visa type offered (updated)
    "visa type": "🛂 We offer Non-Immigrant Visa for the US and Express Entry and other immigration pathways for Canada.",
    "what type of visa you offer": "🛂 We offer Non-Immigrant Visa for the US and Express Entry and other immigration pathways for Canada.",

    # Qualifications & policies
    "qualifications": "✅ Open to applicants with or without prior training or experience. Applicants must be willing to undergo training and develop the necessary skills for the program.",
    "age limit": "👥 No age limit, provided the applicant is physically capable of performing the required tasks.",
    "is there genders required": "⚧ Open to all genders.",
    "gender": "⚧ Open to all genders.",
    "does it accept graduates only": "🎓 Accepts both graduates and undergraduates.",
    "graduates": "🎓 Accepts both graduates and undergraduates.",

    # Additional FAQs from user list
    "how can i contact your team": "📞 You can contact us directly: +63 905-804-4426 or +63 969-251-0672\n📧 state101ortigasbranch@gmail.com",
    "is there a guarantee of visa approval": "✅ We are here to guide you from start to finish and help increase your chances of visa approval for US non-immigrant visas and Canada's Express Entry and other pathways.",
    "do you offer caregiver or work abroad programs": "📝 All the details about our program will be discussed during the initial briefing and assessment at our office.\n\n📍 2F Unit 223, One Oasis Hub B, Ortigas Ext, Pasig City\n🗺️ https://maps.app.goo.gl/o2rvHLBcUZhpDJfp8\n🎥 https://vt.tiktok.com/ZSyuUpdN6/\n📞 +63 905-804-4426 or +63 969-251-0672\n📧 state101ortigasbranch@gmail.com\n⏰ Mon-Sat 9AM-5PM",
    "do you have student visa programs": "🛂 We offer Non-Immigrant Visa for the US and Express Entry and other immigration pathways for Canada.",
    "how can i book an appointment": "📝 To get started, please visit our website to complete the application form: https://state101-travel-website.vercel.app/services\n\nYour information is secure and used only for visa assessment.",
    "how can i start my application": "📝 To get started, please visit our website to complete the application form: https://state101-travel-website.vercel.app/services\n\nYour information is secure and used only for visa assessment.",
    "what happens after i submit my documents": "📞 Expect a call within 24 hours as soon as we can handle your query.",
    "can i apply even if im outside metro manila": "📍 Yes, we assist clients nationwide. Business hours: Mon-Sat 9AM-5PM.",
    "can i walk in without an appointment": "✅ Yes, we accept walk-in clients with or without an appointment, but we highly suggest booking an appointment for faster service.",
    "do you have available job offers abroad": "🛂 As of now we only offer non-Immigrant Visa for the US and Express Entry and other immigration pathways for Canada. For current details, please contact us directly at +63 905-804-4426 or +63 969-251-0672.",
    "do you have a partner agency abroad": "🏢 No, we are an independent and private company located at our main office in Pasig City, accredited by the Municipality of Pasig.",
    "are the job placements direct hire or through an agency": "🛂 As of now we only offer non-Immigrant Visa for the US and Express Entry and other immigration pathways for Canada. For current details, please contact us directly at +63 905-804-4426 or +63 969-251-0672.",
    "can families or couples apply together": "👨‍👩‍👧 Yes. Please visit https://state101-travel-website.vercel.app/services to begin your application. For questions, contact us at +63 905-804-4426 or +63 969-251-0672.",
    "is the orientation mandatory before applying": "🧭 Yes. We’ll orient you so you’re fully prepared and understand the process.",
    "can i join the orientation online": "📝 All the details about our program will be discussed during the initial briefing and assessment at our office. We recommend booking an appointment via our website: https://state101-travel-website.vercel.app/services\n\n📍 2F Unit 223, One Oasis Hub B, Ortigas Ext, Pasig City\n🗺️ https://maps.app.goo.gl/o2rvHLBcUZhpDJfp8\n🎥 https://vt.tiktok.com/ZSyuUpdN6/\n📞 +63 905-804-4426 or +63 969-251-0672.",
    "what should i bring during the orientation day": "🧾 Bring the Initial Requirements. If you have questions, contact us for confirmation before your visit.",
    "how can i reschedule my orientation": "📞 Please contact us directly at +63 905-804-4426 or +63 969-251-0672 to reschedule.",
    "do you have orientations in other branches": "🏢 No, we are only located at our Pasig City office.",
    "what documents are required to start processing": "🗂️ Provide the Initial Requirements. For a complete and personalized checklist, contact us.",
    "how do i submit my requirements": "📤 Submit your requirements through our website: https://state101-travel-website.vercel.app/services\n\nYou can view all requirements and submit your application there.",
    "how can i verify if my consultant is from state101 travel": "🔐 Please verify using our official details:\n• Location: 2F Unit 223, One Oasis Hub B, Ortigas Ext, Pasig City\n• Contact Numbers: +63 905-804-4426 or +63 969-251-0672\n• Business Hours: Mon-Sat 9AM-5PM\n• We are officially registered with the Municipality of Pasig.",
    "how can i make sure im dealing with an official staff member": "🔐 Please verify using our official details:\n• Location: 2F Unit 223, One Oasis Hub B, Ortigas Ext, Pasig City\n• Contact Numbers: +63 905-804-4426 or +63 969-251-0672\n• Business Hours: Mon-Sat 9AM-5PM\n• We are officially registered with the Municipality of Pasig.",
    "do you have social media": "🌐 Yes. You can find our social media links at the bottom of our website.",
    "what should i do if i encounter scammers": "⚠️ Please use our official contacts and report suspicious accounts. Official details:\n• Location: 2F Unit 223, One Oasis Hub B, Ortigas Ext, Pasig City\n• Contact Numbers: +63 905-804-4426 or +63 969-251-0672\n• Business Hours: Mon-Sat 9AM-5PM\n• We are officially registered with the Municipality of Pasig.",
    "do you assist with pre-departure orientation": "🧭 Yes, we orient you before departure to help ensure you are fully prepared for your journey.",
    
    # Value proposition
    "why choose": """🌟 Why choose State101 Travel?
- Focused expertise: US and Canada visa assistance only, so guidance stays accurate and relevant.
- Official and registered: Private company accredited by the Municipality of Pasig.
- Clear, consistent info: Location, hours, and contacts are fixed and verified.
- Friendly process: We recommend booking an appointment for a smooth visit.

Contacts & Hours:
📍 2F Unit 223, One Oasis Hub B, Ortigas Ext, Pasig City
🗺️ Map: https://maps.app.goo.gl/o2rvHLBcUZhpDJfp8
🎥 Location guide: https://vt.tiktok.com/ZSyuUpdN6/
📞 +63 905-804-4426 or +63 969-251-0672
📧 state101ortigasbranch@gmail.com
⏰ Mon–Sat, 9:00 AM – 5:00 PM""",
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
        # Delay answers slightly to simulate careful reasoning and reduce rapid-fire responses
        self.thinking_delay = float(st.secrets.get("THINKING_DELAY_MS", 900)) / 1000.0
        # Strict mode ensures canonical info comes only from hardcoded data
        self.strict_mode = bool(st.secrets.get("STRICT_MODE", True))
        # Facts-backed fallback mode: when true, LLM receives canonical facts and must answer using them only
        self.smart_facts_mode = bool(st.secrets.get("SMART_FACTS_MODE", True))
        # Semantic router settings (RapidFuzz string similarity)
        self.semantic_enabled = bool(st.secrets.get("SEMANTIC_ROUTER", True))
        self.semantic_threshold = float(st.secrets.get("SEMANTIC_THRESHOLD", 80))  # Lowered from 86 to 80 for better typo tolerance
        self.semantic_entries: List[Tuple[str, str]] = []  # (intent, phrase)

        # Embedding router settings (fastembed; optional)
        self.embedding_enabled = bool(st.secrets.get("EMBEDDING_ROUTER", True))
        self.embedding_threshold = float(st.secrets.get("EMBEDDING_THRESHOLD", 0.58))  # cosine 0..1
        self._embedder = None
        self.embedding_entries: List[Tuple[str, str]] = []  # (intent, phrase)
        self.embedding_vectors: List[List[float]] = []  # normalized vectors
        
        # --- RAG (Retrieval-Augmented Generation) ---
        self.rag_enabled = bool(st.secrets.get("RAG_ENABLED", False))
        self.rag_top_k = int(st.secrets.get("RAG_TOP_K", 4))
        self.rag_knowledge_dir = st.secrets.get("KNOWLEDGE_DIR", "knowledge")
        self.rag_chunks: List[Tuple[str, str]] = []  # (source, chunk_text)
        self.rag_vectors: List[List[float]] = []  # embeddings for chunks
        
        # --- Domain relevance gating (to avoid off-topic queries like "where to buy nuggets") ---
        self.domain_gating_enabled = bool(st.secrets.get("DOMAIN_GATING_ENABLED", True))
        # If a prompt has no relevant keywords and token length >= this value, mark off-topic
        self.domain_min_len_for_offtopic = int(st.secrets.get("DOMAIN_MIN_LEN_FOR_OFFTOPIC", 6))
        # Optional embedding-based relevance: if available, treat as in-domain when similarity >= threshold
        self.domain_embed_threshold = float(st.secrets.get("DOMAIN_EMBED_THRESHOLD", 0.62))  # cosine 0..1
        # Knowledgebase overrides (populated in pack_facts)
        self.kb_overrides: dict[str, str] = {}

        # --- LLM-based relevance gating (optional; uses classifier prompt with caching) ---
        self.llm_relevance_enabled = bool(st.secrets.get("LLM_RELEVANCE_ENABLED", True))
        self.llm_relevance_model = st.secrets.get("LLM_RELEVANCE_MODEL", "llama-3.3-70b-versatile")
        # If classification fails (API error), allow query to proceed when True (fail-open)
        self.llm_relevance_fail_open = bool(st.secrets.get("LLM_RELEVANCE_FAIL_OPEN", True))
        self._relevance_cache = {}
        # Optional strict guard for third‑party place queries (e.g., airport, malls)
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
        
        # Define topics that are considered relevant to State101 Travel
        self.relevant_keywords = [
            "visa", "travel", "passport", "appointment", "requirements", 
            "canada", "canadian", "america", "american", "us", "usa",
            "application", "processing", "state101", "state 101",
            "consultation", "documentation", "embassy", "interview",
            "tourist", "business", "student", "work permit", "immigration",
            "fee", "cost", "price", "hours", "location", "contact", "website", "webpage",
            "eligibility", "qualification", "denial", "approval",
            "urgent", "status", "track", "form", "apply", "b1", "choose", "benefits", "offerings", "table", "summary", "summarize",
            "reach", "call", "email", "phone", "number", "how to", "where", "when", "get", "find",
            # Legitimacy/trust related (for translated queries like "is this true?", "real?")
            "legit", "legitimate", "real", "true", "trust", "trustworthy", "scam", "fake", "registered", "official"
        ]
        
        # Define off-topic keywords that should trigger immediate rejection
        self.offtopic_keywords = [
            # Programming & Tech
            "calculator", "code", "program", "programming", "python", "javascript", "java",
            "html", "css", "coding", "developer", "software", "debug", "algorithm",
            "function", "variable", "loop", "array", "database", "sql", "api",
            
            # Food & Restaurants (NOT visa related)
            "nuggets", "chicken", "burger", "pizza", "food", "restaurant", "menu",
            "jollibee", "mcdo", "mcdonald", "kfc", "fastfood", "fast food",
            "recipe", "cook", "cooking", "bake", "kitchen", "meal", "lunch", "dinner",
            "breakfast", "starbucks", "shakeys", "max", "chowking", "greenwich",
            "potato corner", "army navy", "yellow cab", "papa johns", "pizza hut",
            "burger king", "wendys", "subway", "taco bell", "chipotle",
            
            # Entertainment
            "game", "gaming", "video game", "xbox", "playstation", "nintendo",
            "movie", "film", "cinema", "netflix", "series", "anime", "tv show",
            "song", "music", "spotify", "concert", "artist", "album", "singer",
            "youtube", "tiktok video", "vlog", "streamer", "twitch",
            
            # Academic (non-visa)
            "math", "solve", "equation", "homework", "essay", "write a story",
            "assignment", "thesis", "research", "study", "exam", "test", "quiz",
            "algebra", "calculus", "geometry", "physics", "chemistry", "biology",
            
            # Weather & Nature
            "weather", "forecast", "rain", "sunny", "temperature", "climate",
            "typhoon", "storm", "earthquake", "volcano",
            
            # Sports & Fitness
            "sports", "basketball", "football", "soccer", "volleyball", "boxing",
            "manny pacquiao", "nba", "pba", "ufc", "gym", "workout", "exercise",
            
            # Finance & Investment (non-visa)
            "stock", "crypto", "bitcoin", "ethereum", "trading", "investment",
            "forex", "shares", "dividend", "nft", "blockchain",
            
            # Shopping & E-commerce
            "lazada", "shopee", "amazon", "ebay", "zalora", "buy", "shopping",
            "discount", "sale", "gadget", "phone", "iphone", "samsung", "laptop",
            
            # Transportation (non-visa related locations)
            "grab", "uber", "taxi", "jeep", "bus", "mrt", "lrt", "airport terminal",
            "flight schedule", "airline", "pal", "cebu pacific", "air asia",
            
            # Medical & Health
            "doctor", "hospital", "medicine", "sick", "disease", "covid", "vaccine",
            "pharmacy", "mercury drug", "watsons", "clinic",
            
            # Random Topics
            "zodiac", "horoscope", "astrology", "fortune", "lucky number",
            "lottery", "lotto", "raffle", "contest", "joke", "riddle",
            "ghost", "horror", "paranormal", "magic", "spell",
            
            # Other Businesses/Services (not State101)
            "bank", "bdo", "bpi", "metrobank", "gcash", "paymaya", "coins",
            "load", "prepaid", "postpaid", "globe", "smart", "pldt",
            "hotel", "booking", "agoda", "airbnb", "resort", "beach",
            
            # Specific non-visa queries
            "minecraft", "roblox", "fortnite", "pubg", "mobile legends", "dota",
            "facebook", "instagram", "twitter", "telegram", "whatsapp",
            "google", "search", "wikipedia", "tutorial", "how to make",
            "news", "politics", "election", "government", "law", "court"
        ]

        # Intent synonyms mapped to canonical intents
        self.intent_synonyms = {
            "location": [
                "where are you", "where are you located", "where is your office",
                "office address", "address", "location", "map", "directions",
                "find you", "tiktok", "tiktok location", "tiktok video", "google map",
                "how to get there", "how do i get there", "how can i get there",
                "where can i find you", "office", "branch", "nasa saan", "saan office",
                # Common misspellings and variations
                "were are you", "wer r u", "adress", "addres", "direcsion", "locasion",
                "were is ur office", "ofice", "offce", "locashun", "were u at",
                # More natural language
                "directions to your office", "how to go there", "paano pumunta", "saan kayo",
                "makati ba", "pasig ba", "mall ba kayo", "building nyo", "landmark"
            ],
            "hours": [
                "hours", "opening hours", "business hours", "schedule", "open time", "what time",
                "when are you open", "what time do you open", "what time do you close",
                "open today", "closed today", "available", "operating hours",
                # Variations and slang
                "wat time", "time open", "open ba kayo", "bukas ba", "sked", "scheds",
                "anong oras", "schedule nyo", "open now", "closed now", "working hours",
                "available ba", "pwede ba ngayon", "open ba today", "weekends", "saturday"
            ],
            "contact": [
                "contact", "phone", "phone number", "call you", "email", "email address", 
                "how to contact you", "contact you", "reach you", "how can i contact you",
                "contact info", "contact details", "phone numbers", "mobile number",
                # Variations and slang
                "fone", "number", "txt", "text", "cp number", "mobile", "cellphone", 
                "reach out", "get in touch", "call", "message", "contact nyo",
                "paano makipag ugnayan", "numero nyo", "email nyo", "telepono",
                # More variations
                "contact information", "how to reach", "how do i call", "text you",
                "whatsapp", "viber", "messenger", "dm", "chat"
            ],
            "website": [
                "website", "web site", "web page", "webpage", "website page", "site", "link",
                "web", "online", "url", "website nyo", "link nyo", "fb page", "facebook"
            ],
            "services": [
                "services", "what services", "services do you offer",
                "what services does state101 travel offer", "what do you do",
                "what can you help with", "ano tulong nyo", "what kind of help",
                # Variations
                "serbisyo", "offer", "ano services", "wat u offer", "ano kaya nyo",
                "what do you provide", "ano pwede", "available services", "offerings"
            ],
            "legit": [
                "legit", "legitimacy", "is your company legit", "are you legit", 
                "is this real", "is this true", "real", "true", "trustworthy", "scam", "fake",
                "can i trust you", "are you registered", "official", "registered",
                # Slang and variations
                "totoo ba", "legit ba", "totoo", "tru", "4real", "fr", "for real",
                "scammer", "scam ba", "fake ba", "trust", "trusted", "sketchy",
                "reliable", "legit ba talaga", "sure ba", "safe ba", "maaasahan ba"
            ],
            "program details": [
                "program details", "details of your program", "details of program",
                "are trainings free", "is orientation free", "installment plans", "hidden charges",
                "consultation free", "process", "procedure", "how it works",
                "explain the process", "steps", "what happens", "timeline",
                "fees related", "process related", "visa application process",
                "how does visa application process work", "how does the process work",
                "how does your process work", "flow", "how to apply",
                # More variations
                "paano process", "ano steps", "ano gagawin", "paano mag start",
                "what is the process", "whats the procedure", "explain program"
            ],
            "visa type": [
                "visa type", "what type of visa", "what type of visa you offer",
                "what types of visas do you process", "do you have student visa programs",
                "o visa", "o-1 visa", "o1 visa", "o visa for us talent",
                "tourist visa", "work visa", "student visa", "business visa",
                "what visa", "ano visa", "types of visa", "visa options"
            ],
            "qualifications": [
                "qualifications", "qualification", "what are the qualifications",
                "am i qualified", "can i apply", "eligible", "eligibility",
                "requirements to apply", "do i qualify", "qualified ba ako",
                "pwede ba ako", "pasok ba ako", "tanggap ba ako", "can i join"
            ],
            "age limit": [
                "age", "age limit", "age related", "age requirement", "how old",
                "minimum age", "maximum age", "too old", "too young",
                "edad", "age limit ba", "pwede ba kahit matanda", "senior"
            ],
            "gender": [
                "gender", "genders required", "male", "female", "gender requirement",
                "lalaki", "babae", "gender ba", "required gender", "boys", "girls",
                "for men", "for women", "lgbt", "lgbtq", "any gender"
            ],
            "graduates": [
                "graduates", "undergraduate", "does it accept graduates only",
                "college graduate", "high school", "diploma", "degree",
                "need degree", "graduate ba", "undergrad", "walang degree",
                "no diploma", "graduate lang ba", "college lang ba"
            ],
            "requirements": [
                "requirements", "documents", "needed documents", "prepare", "preparation", 
                "what should i prepare", "what to bring", "what do i need",
                "documents needed", "papers needed", "initial requirements",
                # Variations and slang
                "reqs", "docs", "papers", "kailangan", "ano need", "wat to bring",
                "dokumento", "requirement", "requirment", "documens",
                "ano kailangan", "ano dalhin", "ano requirements", "documents to submit",
                "what to submit", "needed papers", "initial docs"
            ],
            "appointment": [
                "appointment", "book", "schedule appointment", "how can i book an appointment",
                "how can i start my application", "book appointment", "make appointment",
                "set appointment", "schedule visit", "reserve", "booking",
                # Variations and slang
                "appoint", "sched", "schedule", "booking", "reserve", "set appointment",
                "pano mag book", "paano mag appointment", "book appointment",
                "mag pa schedule", "mag set ng appointment", "walk in", "walkin",
                "can i visit", "pwede ba pumunta", "need appointment ba"
            ],
            "status": [
                "status", "application status", "how do i know the status",
                "check status", "track application", "follow up", "update",
                # Variations
                "track", "tracking", "update", "progress", "ano na", "kamusta na",
                "application progress", "where is my application", "status ng application",
                "ano nangyari", "approved na ba", "rejected ba", "pending pa ba"
            ],
            "price": [
                "price", "cost", "fee", "how much", "payment", "payment options", "pay",
                "installment", "hidden charges", "consultation free", "processing fee",
                "what payment methods do you accept", "total cost", "full price",
                # Variations and slang
                "magkano", "presyo", "bayad", "pric", "kost", "free ba", "libre ba",
                "how mch", "pricing", "fees", "rates", "rate", "charges",
                "magkano lahat", "ano bayad", "mahal ba", "total", "down payment",
                "dp", "monthly", "weekly", "discount", "promo", "cheap"
            ],
            "why choose": [
                "why choose", "why choose state101", "why should i choose you", "why pick you",
                "what makes you different", "advantages", "benefits", "bakit kayo",
                "why you", "what makes you special", "why state101", "benefits nyo",
                "advantage", "what do you offer that others dont"
            ],
        }
        # Build indexes
        if self.semantic_enabled:
            self._build_semantic_index()
        if self.embedding_enabled:
            self._build_embedding_index()
        # Build RAG index last so fastembed (if available) can be reused
        if self.rag_enabled:
            self._build_rag_index()

    # --------- INDEX BUILDERS (restored into class) ---------
    def _build_semantic_index(self):
        """Populate self.semantic_entries with (intent, phrase) pairs for RapidFuzz routing."""
        entries: List[Tuple[str, str]] = []
        for intent, syns in self.intent_synonyms.items():
            for s in syns:
                entries.append((intent, s))
        # Add the hardcoded keys themselves for direct matches
        for key in HARDCODED_RESPONSES.keys():
            entries.append((key, key))
        # Deduplicate (case-insensitive)
        seen = set()
        deduped: List[Tuple[str, str]] = []
        for intent, text in entries:
            t = text.strip().lower()
            if t and t not in seen:
                seen.add(t)
                deduped.append((intent, text))
        self.semantic_entries = deduped

    def _import_fastembed(self):
        """Return fastembed TextEmbedding class if available, else None."""
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
        """Build embedding-based intent routing index if fastembed is installed."""
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

    # ---------- RAG SUPPORT (moved correctly into class) ----------
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
        return sum(x * y for x, y in zip(a, b))

    def rag_retrieve(self, prompt: str) -> List[Tuple[str, str]]:
        if not self.rag_enabled or not self.rag_chunks:
            return []
        if self.rag_vectors:
            TextEmbedding = self._import_fastembed()
            if TextEmbedding is not None:
                try:
                    embedder = TextEmbedding()
                    q = list(embedder.embed([prompt]))[0]
                    q = self._l2_normalize(list(q))
                    scored = []
                    for i, v in enumerate(self.rag_vectors):
                        scored.append((self._cosine_sim(q, v), i))
                    scored.sort(reverse=True)
                    top = [self.rag_chunks[i] for _, i in scored[: self.rag_top_k]]
                    return top
                except Exception:
                    pass
        try:
            scored = []
            norm = self._normalize(prompt)
            for i, (_, ch) in enumerate(self.rag_chunks):
                score = fuzz.token_set_ratio(norm, self._normalize(ch))
                scored.append((score, i))
            scored.sort(reverse=True)
            top = [self.rag_chunks[i] for _, i in scored[: self.rag_top_k]]
            return top
        except Exception:
            return []

    def _normalize(self, text: str) -> str:
        return re.sub(r'[^\w\s]', '', text.lower()).strip()

    def match_intent(self, prompt: str) -> str | None:
        """Match intents using word-boundary regex to avoid substring mistakes
        (e.g., 'age' matching inside 'page'). Supports multi-word synonyms.
        """
        norm = self._normalize(prompt)
        for key, synonyms in self.intent_synonyms.items():
            for s in synonyms:
                s_norm = self._normalize(s)
                # Build a word-boundary pattern for the entire phrase
                pattern = r"\b" + re.escape(s_norm) + r"\b"
                if re.search(pattern, norm):
                    return key
        return None

    def get_canonical_response(self, intent: str) -> str | None:
        # Priority: dynamic KB overrides FIRST, then hardcoded fallbacks
        # This ensures CMS updates by non-technical staff take precedence
        
        # 1. Check KB overrides (from CMS knowledgebase)
        kb_overrides = getattr(self, "kb_overrides", {})
        print(f"[DEBUG] get_canonical_response('{intent}') - KB has {len(kb_overrides)} entries: {list(kb_overrides.keys())}")
        if intent in kb_overrides:
            print(f"[DEBUG] ✅ Using KB for '{intent}'")
            return kb_overrides[intent]
        print(f"[DEBUG] ⚠️ No KB entry for '{intent}', falling back to hardcoded")
        
        # 2. Check direct hardcoded match
        if intent in HARDCODED_RESPONSES:
            return HARDCODED_RESPONSES[intent]
        
        # 3. Map intent aliases to underlying keys and check hardcoded fallback
        mapping = {
            "location": "location",
            "hours": "hours",
            "contact": "contact",  # KB overrides this, fallback to hardcoded contact
            "website": "website",
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
            "why choose": "why choose",
        }
        key = mapping.get(intent)
        if key and key in HARDCODED_RESPONSES:
            return HARDCODED_RESPONSES[key]
        
        return None

    def semantic_route(self, prompt: str) -> str | None:
        """Route using RapidFuzz token_set_ratio across known phrases.
        Returns canonical response if best score >= threshold.
        """
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
        """Route using embeddings cosine similarity if enabled and available."""
        if not self.embedding_enabled or not self._embedder or not self.embedding_vectors:
            return None
        try:
            q_vec = list(self._embedder.embed([prompt]))[0]
            q_vec = self._l2_normalize(list(q_vec))
            # cosine with normalized vectors equals dot product
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

    def pack_facts(self) -> dict:
        """Build facts with precedence: Knowledgebase overrides > CMS footer/topbar > hardcoded.
        Populates self.kb_overrides so get_canonical_response can serve dynamic answers."""
        kb_enabled = bool(st.secrets.get("KB_OVERRIDE_ENABLED", True))
        kb_dir = Path("knowledge")
        kb_categories: dict[str, str] = {}
        if kb_enabled and kb_dir.exists():
            for p in kb_dir.glob("kb_*.md"):
                try:
                    raw = p.read_text(encoding="utf-8")
                    if raw.startswith("---"):
                        fm_end = raw.find("\n---", 3)
                        if fm_end != -1:
                            front = raw[3:fm_end].strip().splitlines()
                            body = raw[fm_end+4:].strip()
                            meta = {}
                            for line in front:
                                if ":" in line:
                                    k, v = line.split(":", 1)
                                    meta[k.strip().lower()] = v.strip()
                            cat = meta.get("category") or meta.get("cat")
                            if cat:
                                cat_key = cat.lower().strip()
                                # last write wins only if not already set; simplifies ordering
                                if cat_key not in kb_categories:
                                    kb_categories[cat_key] = body
                    else:
                        cat_key = p.stem.replace("kb_", "").lower().split("_")[0]
                        if cat_key and cat_key not in kb_categories:
                            kb_categories[cat_key] = raw.strip()
                except Exception:
                    continue

        kb_to_intent = {
            # Location/Address variations (KB: Pasig address + maps + TikTok)
            "location": "location",
            "located": "location",
            "address": "location",
            "map": "location",
            "directions": "location",
            "office": "location",
            "find you": "location",
            "where are you": "location",
            "where is your office": "location",
            "where can i find": "location",
            "how to get there": "location",
            "tiktok": "location",
            "google map": "location",
            "google maps": "location",
            "pasig": "location",
            "ortigas": "location",
            "oasis": "location",
            "hub b": "location",
            "unit 223": "location",
            
            # Contact variations (KB: phones + email)
            "contact": "contact",
            "phone": "contact",
            "phone number": "contact",
            "mobile": "contact",
            "number": "contact",
            "call": "contact",
            "call you": "contact",
            "email": "contact",
            "email address": "contact",
            "reach": "contact",
            "reach you": "contact",
            "how to contact": "contact",
            "contact info": "contact",
            "contact information": "contact",
            "get in touch": "contact",
            "message": "contact",
            "text": "contact",
            "hotline": "contact",
            
            # Hours/Schedule variations (KB: Mon-Sat 9AM-5PM)
            "hours": "hours",
            "business hours": "hours",
            "schedule": "hours",
            "open": "hours",
            "opening hours": "hours",
            "what time": "hours",
            "open time": "hours",
            "time open": "hours",
            "when open": "hours",
            "operating hours": "hours",
            "available": "hours",
            "close": "hours",
            "closing time": "hours",
            "monday": "hours",
            "saturday": "hours",
            "sunday": "hours",
            "weekdays": "hours",
            "weekend": "hours",
            
            # Services variations (KB: US non-immigrant + Canada Express Entry)
            "services": "services",
            "what services": "services",
            "services do you offer": "services",
            "what do you offer": "services",
            "service": "services",
            "offer": "services",
            "assistance": "services",
            "help with": "services",
            "us visa": "services",
            "canada visa": "services",
            "express entry": "services",
            "non immigrant": "services",
            "immigration": "services",
            
            # Requirements variations (KB: passport, 2x2, training cert, diploma, resume)
            "requirements": "requirements",
            "documents": "requirements",
            "docs": "requirements",
            "needed documents": "requirements",
            "what to bring": "requirements",
            "prepare": "requirements",
            "preparation": "requirements",
            "what should i prepare": "requirements",
            "initial requirements": "requirements",
            "document requirements": "requirements",
            "passport": "requirements",
            "photo": "requirements",
            "2x2": "requirements",
            "resume": "requirements",
            "diploma": "requirements",
            "certificate": "requirements",
            "supporting documents": "requirements",
            "need to submit": "requirements",
            "submit": "requirements",
            
            # Program/Process variations (KB: explained during briefing)
            "program details": "program details",
            "program": "program details",
            "process": "program details",
            "procedure": "program details",
            "steps": "program details",
            "flow": "program details",
            "timeline": "program details",
            "how to apply": "program details",
            "application process": "program details",
            "fees related": "program details",
            "process related": "program details",
            "briefing": "program details",
            "assessment": "program details",
            "orientation": "program details",
            "training": "program details",
            "specifics": "program details",
            "explained": "program details",
            "details": "program details",
            
            # Legitimacy variations (KB: officially registered, Pasig permit)
            "legit": "legit",
            "legitimacy": "legit",
            "legitimate": "legit",
            "is your company legit": "legit",
            "are you legit": "legit",
            "registered": "legit",
            "official": "legit",
            "permit": "legit",
            "accredited": "legit",
            "licensed": "legit",
            "scam": "legit",
            "fake": "legit",
            "trust": "legit",
            "trustworthy": "legit",
            
            # Price/Cost variations (KB: discussed during briefing)
            "price": "price",
            "prices": "price",
            "fees": "price",
            "fee": "price",
            "cost": "price",
            "costs": "price",
            "payment": "price",
            "pay": "price",
            "how much": "price",
            "payment options": "price",
            "installment": "price",
            "rates": "price",
            "pricing": "price",
            "charge": "price",
            "charges": "price",
            "afford": "price",
            "expensive": "price",
            "cheap": "price",
            "budget": "price",
            
            # Qualifications variations (KB: open to all, training/experience not required)
            "qualification": "qualifications",
            "qualifications": "qualifications",
            "eligible": "qualifications",
            "eligibility": "qualifications",
            "who can apply": "qualifications",
            "can i apply": "qualifications",
            "am i qualified": "qualifications",
            "requirements to apply": "qualifications",
            "experience": "qualifications",
            "training required": "qualifications",
            "skills": "qualifications",
            "background": "qualifications",
            
            # Appointment variations (KB: walk-ins accepted, booking recommended)
            "appointment": "appointment",
            "book": "appointment",
            "schedule appointment": "appointment",
            "how to book": "appointment",
            "reserve": "appointment",
            "set appointment": "appointment",
            "booking": "appointment",
            "walk in": "appointment",
            "walkin": "appointment",
            "drop by": "appointment",
            "visit": "appointment",
            "consultation": "appointment",
            
            # Status tracking variations (KB: email with reference or call)
            "status": "status",
            "track": "status",
            "application status": "status",
            "tracking": "status",
            "update": "status",
            "check status": "status",
            "reference number": "status",
            "follow up": "status",
            "progress": "status",
            
            # Website variations
            "website": "website",
            "web site": "website",
            "webpage": "website",
            "web page": "website",
            
            # Visa type variations
            "visa type": "visa type",
            "type of visa": "visa type",
            "what visa": "visa type",
            "visa types": "visa type",
            
            # Age policy variations (KB: no age limit, physical capability)
            "age limit": "age limit",
            "age": "age limit",
            "how old": "age limit",
            "age requirement": "age limit",
            "age restriction": "age limit",
            "minimum age": "age limit",
            "maximum age": "age limit",
            "too old": "age limit",
            "too young": "age limit",
            "physically capable": "age limit",
            
            # Gender policy variations (KB: open to all genders)
            "gender": "gender",
            "male": "gender",
            "female": "gender",
            "gender requirement": "gender",
            "gender orientation": "gender",
            "lgbtq": "gender",
            "women": "gender",
            "men": "gender",
            "lady": "gender",
            "guy": "gender",
            
            # Graduates policy variations (KB: accepts graduates and undergraduates)
            "graduates": "graduates",
            "graduate": "graduates",
            "undergraduate": "graduates",
            "education": "graduates",
            "degree": "graduates",
            "college": "graduates",
            "diploma required": "graduates",
            "finished school": "graduates",
            "no degree": "graduates",
            "high school": "graduates",
            
            # Why choose variations
            "why choose": "why choose",
            "benefits": "why choose",
            "advantages": "why choose",
            "why pick": "why choose",
        }
        
        # Store the comprehensive keyword mapping for reference (used by intent_synonyms in __init__)
        # This helps document all the natural language variations we support
        self.kb_keyword_map = kb_to_intent
        
        # Map KB file category names to canonical intent names
        # This is what actually converts KB frontmatter categories to intent keys
        kb_category_to_intent = {
            "location": "location",
            "contact": "contact",
            "hours": "hours",
            "services": "services",
            "requirements": "requirements",
            "program": "program details",
            "legit": "legit",
            "price": "price",
            "qualification": "qualifications",
            "age limit": "age limit",
            "gender": "gender",
            "graduate": "graduates",
            "appointment": "appointment",
            "status": "status",
            "website": "website",
            "visa type": "visa type",
            "why choose": "why choose",
        }
        
        # Build kb_overrides dict: intent_name -> KB content
        self.kb_overrides = {}
        for kb_cat, content in kb_categories.items():
            intent = kb_category_to_intent.get(kb_cat, kb_cat)
            self.kb_overrides[intent] = content.strip()
        
        # Debug: Print loaded KB overrides (helpful for troubleshooting)
        if self.kb_overrides:
            print(f"[KB] Loaded {len(self.kb_overrides)} knowledge base overrides: {list(self.kb_overrides.keys())}")

        # REMOVED CMS /api/facts fallback - KB overrides are now truly first priority
        # The precedence is now strictly: KB overrides > HARDCODED_RESPONSES > nothing
        # This ensures knowledgebase updates via CMS /api/knowledgebase take full precedence

        def first_url(text: str) -> str | None:
            m = re.search(r"https?://\S+", text or "")
            return m.group(0) if m else None

        address_line = self.kb_overrides.get("location") or (HARDCODED_RESPONSES.get("located") or "")
        location_block = self.kb_overrides.get("location") or HARDCODED_RESPONSES.get("location") or address_line
        map_url = first_url(location_block) or first_url(HARDCODED_RESPONSES.get("map", "")) or ""

        contact_src = self.kb_overrides.get("contact") or HARDCODED_RESPONSES.get("contact", "")
        if isinstance(contact_src, list):
            phones = contact_src
            contact_text = "\n".join(contact_src)
        else:
            contact_text = contact_src or ""
            phones = re.findall(r"\+?\d[\d\s-]{7,}\d", contact_text)
        email_match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", self.kb_overrides.get("contact", "") or contact_text)
        email_addr = email_match.group(0) if email_match else ""

        facts = {
            "address": address_line,
            "location_block": location_block,
            "map_url": map_url,
            "tiktok_url": None,
            "website_url": self.kb_overrides.get("website") or HARDCODED_RESPONSES.get("website", ""),
            "hours": self.kb_overrides.get("hours") or HARDCODED_RESPONSES.get("hours", ""),
            "phones": phones,
            "email": email_addr,
            "services": self.kb_overrides.get("services") or HARDCODED_RESPONSES.get("services", ""),
            "legitimacy": self.kb_overrides.get("legit") or HARDCODED_RESPONSES.get("legit", ""),
            "program_details": self.kb_overrides.get("program details") or self.kb_overrides.get("program") or HARDCODED_RESPONSES.get("program details", ""),
            "qualifications": self.kb_overrides.get("qualifications") or HARDCODED_RESPONSES.get("qualifications", ""),
            "age_policy": self.kb_overrides.get("age limit") or HARDCODED_RESPONSES.get("age limit", ""),
            "gender_policy": self.kb_overrides.get("gender") or HARDCODED_RESPONSES.get("gender", ""),
            "graduates_policy": self.kb_overrides.get("graduates") or HARDCODED_RESPONSES.get("graduates", ""),
            "price_note": self.kb_overrides.get("price") or HARDCODED_RESPONSES.get("price", HARDCODED_RESPONSES.get("how much", "")),
            "requirements": self.kb_overrides.get("requirements") or HARDCODED_RESPONSES.get("requirements", ""),
            "contact_block": self.kb_overrides.get("contact") or HARDCODED_RESPONSES.get("urgent", ""),
            "form_hint": "📝 Please visit our website to apply: https://state101-travel-website.vercel.app/services",
        }
        return facts

    # ---- MULTI-INTENT FUSION HELPERS ----
    def _regex_intent_hits(self, prompt: str) -> list[str]:
        """Return all intents matched by word-boundary regex across synonyms.
        Unlike match_intent (which returns the first), this returns a list for fusion.
        """
        norm = self._normalize(prompt)
        hits: list[str] = []
        for key, synonyms in self.intent_synonyms.items():
            for s in synonyms:
                s_norm = self._normalize(s)
                pattern = r"\b" + re.escape(s_norm) + r"\b"
                if re.search(pattern, norm):
                    if key not in hits:
                        hits.append(key)
                        break  # don't add same intent multiple times
        return hits

    def _keyword_overlap_hits(self, prompt: str) -> list[str]:
        """Heuristic: pick top overlapping keyword topics. Returns up to 3 distinct intents."""
        tokens = set(self._normalize(prompt).split())
        topic_keywords = {
            # Avoid generic tokens like 'where' or 'find' to reduce false positives
            "location": {"address", "map", "directions", "office", "tiktok", "location"},
            "appointment": {"appointment", "book", "schedule", "set", "meeting", "reserve"},
            "hours": {"hours", "open", "opening", "schedule", "time", "times"},
            "contact": {"contact", "phone", "call", "email", "mail", "number"},
            "requirements": {"requirements", "documents", "docs", "papers", "needed"},
            "price": {"price", "cost", "fee", "payment", "pay", "rates", "rate", "much"},
            "status": {"status", "track", "tracking", "update", "reference"},
            "visa type": {"type", "b1", "b2", "what", "visa", "kind"},
        }
        scored: list[tuple[str, int]] = []
        for key, kws in topic_keywords.items():
            score = len(tokens & kws)
            if score > 0:
                scored.append((key, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        # keep those with score >= 2 strongly, else top 1 weak overlap
        strong = [k for k, s in scored if s >= 2]
        if strong:
            return strong[:3]
        return [k for k, _ in scored[:1]]

    def _fuse_intents(self, intents: list[str]) -> str | None:
        """Combine canonical answers for up to 3 intents in a user-friendly way."""
        if not intents:
            return None
        merged: list[str] = []
        for it in intents:
            ans = self.get_canonical_response(it)
            if ans and ans not in merged:
                merged.append(ans)
        if not merged:
            return None
        # Join with a visual spacer; keep emoji formatting from each block
        return "\n\n".join(merged[:3])

    def fuzzy_fact_match(self, prompt: str) -> str | None:
        """Lightweight keyword overlap to map unseen phrasing to an intent."""
        tokens = set(self._normalize(prompt).split())
        topic_keywords = {
            # Avoid generic tokens like 'where' or 'find' to reduce false positives
            "location": {"address", "map", "directions", "office", "tiktok", "location"},
            "hours": {"hours", "open", "opening", "schedule", "time", "times"},
            "contact": {"contact", "phone", "call", "email", "mail", "number"},
            "services": {"services", "offer", "provide", "service"},
            "program details": {"process", "procedure", "steps", "flow", "timeline", "briefing", "assessment", "program", "details", "apply"},
            "qualifications": {"qualifications", "qualification", "eligible", "eligibility", "experience", "training"},
            "age limit": {"age", "years", "old", "limit"},
            "gender": {"gender", "male", "female", "women", "men"},
            "graduates": {"graduate", "undergraduate", "degree", "college"},
            "price": {"price", "cost", "fee", "payment", "pay", "rates", "rate", "how", "much"},
            "requirements": {"requirements", "documents", "docs", "papers", "needed", "prepare", "preparation", "bring"},
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
        """Heuristic domain gate for State101 Travel. Conservative allow-list + optional embedding relevance."""
        if not self.domain_gating_enabled:
            return True

        normalized_prompt = prompt.lower()

        # Immediate off-topic triggers
        for keyword in self.offtopic_keywords:
            if keyword in normalized_prompt:
                return False

        # Short greetings/questions: allow to keep UX smooth
        greetings = ["hi", "hello", "hey", "good morning", "good afternoon", "good evening"]
        tokens = normalized_prompt.split()
        if any(g in normalized_prompt for g in greetings) and len(tokens) <= 3:
            return True
        
        # Very short queries (3 words or less): be lenient, likely simple questions
        # This helps with translated Filipino queries like "is this true?", "where?", "real?"
        if len(tokens) <= 3:
            return True

        # Keyword-based relevance
        has_relevant_keyword = any(keyword in normalized_prompt for keyword in self.relevant_keywords)

        # Optional embedding-based relevance using RAG or intent embeddings
        try:
            if not has_relevant_keyword and self._embedder and (self.rag_vectors or self.embedding_vectors):
                # Build a reference pool: prefer RAG vectors; fallback to intent embedding vectors
                ref_vectors = self.rag_vectors if self.rag_vectors else self.embedding_vectors
                q_vec = list(self._embedder.embed([prompt]))[0]
                q_vec = self._l2_normalize(list(q_vec))
                best = -1.0
                for v in ref_vectors:
                    # cosine on normalized vectors
                    score = sum(a*b for a, b in zip(q_vec, v))
                    if score > best:
                        best = score
                if best >= self.domain_embed_threshold:
                    has_relevant_keyword = True
        except Exception:
            pass

        # If still no signal and the prompt is fairly long, consider it off-topic
        if not has_relevant_keyword and len(tokens) >= self.domain_min_len_for_offtopic:
            return False

        return True

    def check_query_relevance(self, prompt: str) -> bool:
        """Use an LLM to decide if a query is relevant to State101 visa services.
        Returns True when relevant, False when off-topic. Caches results per normalized prompt.
        Uses KB content to provide context about what State101 actually offers.
        """
        try:
            cache_key = self._normalize(prompt)
            if cache_key in self._relevance_cache:
                return self._relevance_cache[cache_key]

            # Build dynamic context from KB overrides to show what we actually cover
            kb_topics = []
            if hasattr(self, "kb_overrides") and self.kb_overrides:
                kb_topics = list(self.kb_overrides.keys())
            
            kb_context = ""
            if kb_topics:
                kb_context = f"\n\nState101 Travel covers these topics: {', '.join(kb_topics)}."

            relevance_system = (
                "You are a strict query filter for State101 Travel (US/Canada visa assistance). "
                "Output exactly one token: RELEVANT or OFFTOPIC."
            )
            content = (
                "Decide if the following query is about State101 Travel or US/Canada visa assistance.\n"
                "Consider the following rules:\n"
                "- RELEVANT topics: visas (US/Canada tourist/business/student/work), requirements, documents, services, location/address/map/directions, hours, contact info, appointments, pricing, eligibility, qualifications, age limits, gender policies, graduate requirements, legitimacy, program details, application status, greetings.\n"
                "- CONTEXT ASSUMPTION: Ambiguous queries about location, contact, directions, office, hours, or services default to asking about State101 Travel unless explicitly mentioning OTHER businesses.\n"
                "- LOCATION/DIRECTION QUERIES: 'how to get there?', 'office?', 'where?', 'directions?', 'map?' = asking about OUR office (RELEVANT).\n"
                "- CONTACT QUERIES: 'contact?', 'phone?', 'email?', 'how to reach you?' = asking for OUR contact info (RELEVANT).\n"
                "- HOURS QUERIES: 'hours?', 'open?', 'schedule?' = asking about OUR hours (RELEVANT).\n"
                "- OFFTOPIC: food (nuggets, burger, pizza), entertainment (movies, games), coding/tech, math/homework, general knowledge, weather, sports, OR explicitly asking about OTHER specific businesses/places (e.g., 'where is Jollibee?', 'how to get to SM Mall?').\n"
                f"{kb_context}\n\n"
                f"User query: \"{prompt}\"\n\n"
                "Answer with exactly one word: RELEVANT or OFFTOPIC"
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
            # Small bounded cache (avoid unbounded growth)
            if len(self._relevance_cache) > 500:
                self._relevance_cache.clear()
            self._relevance_cache[cache_key] = is_rel
            return is_rel
        except Exception:
            # Fail-open (configurable)
            return True if self.llm_relevance_fail_open else False

    @sleep_and_retry
    @limits(calls=10, period=60)
    def generate(self, prompt):
        original_prompt = prompt
        try:
            # Detect and translate if not English - DO THIS FIRST!
            # Allow even 2-word queries to be translated (was > 2, now >= 2)
            if len(prompt.split()) >= 2:
                lang = detect(prompt)
                print(f"[LANG DETECT] Detected language: {lang}")
                
                # Common Filipino words that indicate Tagalog/Filipino language
                # If detected wrong language but contains Filipino words, force to Filipino
                filipino_indicators = ["ba", "na", "ng", "sa", "ko", "mo", "ka", "po", "naman", "kasi", "totoo", "saan", "ano", "paano"]
                prompt_lower = prompt.lower()
                has_filipino = any(word in prompt_lower.split() for word in filipino_indicators)
                
                if has_filipino and lang not in ["tl", "fil"]:
                    print(f"[LANG DETECT] Filipino indicators detected, forcing language to 'tl' (was: {lang})")
                    lang = "tl"
                
                if lang != "en":
                    try:
                        translated = GoogleTranslator(source=lang, target="en").translate(prompt)
                        print(f"[TRANSLATION] '{prompt}' ({lang}) → '{translated}'")
                        prompt = translated
                    except Exception as e:
                        # If translation fails with detected lang, try Filipino as fallback
                        if lang != "tl" and has_filipino:
                            print(f"[TRANSLATION] Failed with {lang}, trying 'tl': {e}")
                            translated = GoogleTranslator(source="tl", target="en").translate(prompt)
                            print(f"[TRANSLATION RETRY] '{original_prompt}' (tl) → '{translated}'")
                            prompt = translated
                        else:
                            raise
                else:
                    print(f"[TRANSLATION] English detected, no translation needed")
        except Exception as e:
            print(f"[TRANSLATION ERROR] {e}")
            # Continue with original prompt if translation fails
            pass

        # small, consistent thinking delay to discourage rapid-fire outputs
        try:
            time.sleep(self.thinking_delay)
        except Exception:
            pass

        # --- Populate KB overrides FIRST (before any intent matching) ---
        # This ensures knowledgebase from CMS takes precedence over hardcoded responses
        if self.smart_facts_mode:
            _ = self.pack_facts()  # Populates self.kb_overrides

        # --- Early domain relevance gating ---
        # 1) Optional strict guard for third‑party place queries not referring to us
        if self.third_party_guard_enabled:
            text = prompt.lower()
            mentions_third_party = any(t in text for t in self.third_party_place_terms)
            refers_to_us = any(m in text for m in self._us_reference_markers)
            if mentions_third_party and not refers_to_us:
                return (
                    "😊 I can help with State101 Travel's US/Canada visa assistance inquiries only. "
                    "Please ask about visa requirements, appointments, contact info, or our location."
                )

        # 2) Use simple heuristic gate (like the working code)
        # Skip the overly strict LLM classifier that was rejecting valid queries
        if not self.is_relevant_query(prompt):
            return (
                "😊 I can help with State101 Travel's US/Canada visa assistance inquiries only. "
                "Please ask about visa requirements, appointments, contact info, or our location."
            )

        # If the user explicitly asks for a composition (table/summary/why choose/etc.),
        # go straight to the facts-backed LLM to synthesize the answer in the requested style.
        def _is_composition_request(p: str) -> Tuple[bool, str | None]:
            text = p.lower()
            table_triggers = ["table", "structured table", "tabulate", "grid"]
            summary_triggers = ["summarize", "summary", "overview"]
            why_triggers = ["why choose", "benefits", "advantages", "why pick", "why should i choose"]
            if any(t in text for t in table_triggers):
                return True, "TABLE"
            if any(t in text for t in summary_triggers):
                return True, "SUMMARY"
            if any(t in text for t in why_triggers):
                return True, "WHY"
            return False, None

        comp, comp_mode = _is_composition_request(prompt)
        if comp:
            try:
                enhanced_system_prompt = SYSTEM_PROMPT
                facts = self.pack_facts() if self.smart_facts_mode else None
                style_hint = ""
                if comp_mode == "TABLE":
                    style_hint = "Format your response as a clean Markdown table summarizing our services, contact information, hours, and location. Use only the FACTS."
                elif comp_mode == "SUMMARY":
                    style_hint = "Provide a concise bullet summary using only the FACTS. Include requirements and contact info."
                elif comp_mode == "WHY":
                    style_hint = "Explain briefly why to choose State101 using only the FACTS (legitimacy, focus on US/Canada, official contacts/location)."
                messages = [{"role": "system", "content": enhanced_system_prompt}]
                if facts:
                    messages.append({"role": "system", "content": "Use only these FACTS:"})
                    messages.append({"role": "system", "content": f"FACTS: {facts}"})
                if style_hint:
                    messages.append({"role": "system", "content": style_hint})
                messages.append({"role": "user", "content": prompt})

                response = self.client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=messages,
                    temperature=0.2,
                    max_tokens=800,
                )
                self.last_call = time.time()
                self.daily_count += 1
                return response.choices[0].message.content
            except Exception:
                # Fall back to deterministic blocks if LLM call fails
                pass

        # Multi-intent fusion: if the question clearly asks for 2+ items (e.g., address + appointment)
        # combine both canonical answers deterministically before single-intent routing.
        fusion_candidates = []
        # regex hits (precise phrases)
        fusion_candidates.extend(self._regex_intent_hits(prompt))
        # keyword overlaps (broad hints)
        for k in self._keyword_overlap_hits(prompt):
            if k not in fusion_candidates:
                fusion_candidates.append(k)
        # keep only intents we safely fuse to avoid noise
        fuse_whitelist = {
            "location", "appointment", "hours", "contact", "requirements", "price", "status", "visa type"
        }
        fusion_list = [i for i in fusion_candidates if i in fuse_whitelist]
        if len(fusion_list) >= 2:
            fused = self._fuse_intents(fusion_list)
            if fused:
                return fused

        # Intent-first, hardcoded responses
        intent = self.match_intent(prompt)
        if intent:
            canonical = self.get_canonical_response(intent)
            if canonical:
                return canonical
            if self.strict_mode:
                return "📘 I can share our official information only. Please ask about requirements, location, hours, or services. Visit https://state101-travel-website.vercel.app/services to apply."

        # RapidFuzz router before embeddings to avoid over-eager semantic matches
        sem_answer = self.semantic_route(prompt)
        if sem_answer:
            return sem_answer
        # Embedding router after string similarity; threshold kept conservative in secrets
        emb_answer = self.embed_route(prompt)
        if emb_answer:
            return emb_answer
        fuzzy_intent = self.fuzzy_fact_match(prompt)
        if fuzzy_intent:
            canonical = self.get_canonical_response(fuzzy_intent)
            if canonical:
                return canonical
            if self.strict_mode:
                return "📘 I can share our official information only. Please ask about requirements, location, hours, or services. Visit https://state101-travel-website.vercel.app/services to apply."

        # Check for form request
        if "form" in prompt.lower() or "apply" in prompt.lower():
            return "📝 Please visit our website to apply: https://state101-travel-website.vercel.app/services\n\nYou can find the application form and all requirements there."

        # LLM-based intent classification as fallback (for slang, translated queries, etc.)
        # This helps handle queries like "totoo?" (real?), "legit ba?", "san kayo?" that passed relevance
        # but didn't match exact keywords
        try:
            intent_prompt = f"""Classify this user query into ONE of these intents, or respond with 'general' if it doesn't fit:

Intents: location, contact, hours, services, requirements, program details, legit, price, qualifications, age limit, gender, graduates, appointment, status, visa type

User query: "{prompt}"

Respond with ONLY the intent name (lowercase), nothing else."""

            intent_response = self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": intent_prompt}],
                temperature=0.1,
                max_tokens=10
            )
            llm_intent = intent_response.choices[0].message.content.strip().lower()
            
            # Check if LLM found a valid intent
            if llm_intent and llm_intent != "general":
                canonical = self.get_canonical_response(llm_intent)
                if canonical:
                    return canonical
        except Exception:
            pass  # Fall through to general LLM if classification fails

        # NOTE: Removed direct hardcoded bypass here - all responses now go through
        # get_canonical_response() which checks KB first, then hardcoded fallback

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

            # Provide facts-backed instructions and RAG context when enabled
            facts = self.pack_facts() if self.smart_facts_mode else None
            rag_chunks = self.rag_retrieve(prompt)
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
            # Add retrieved knowledge chunks as optional supporting context (non-canonical)
            if rag_chunks:
                joined = "\n\n".join([f"[{i+1}] ({src})\n{txt}" for i, (src, txt) in enumerate(rag_chunks)])
                messages.append({"role": "system", "content": "Additional CONTEXT (use if relevant; do not override canonical FACTS for address/phones/hours):"})
                messages.append({"role": "system", "content": joined})
            messages.append({"role": "user", "content": prompt})

            response = self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                temperature=0.2,
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
            # Use KB contact info if available, otherwise hardcoded fallback
            contact_info = self.kb_overrides.get("contact") if hasattr(self, "kb_overrides") else None
            if not contact_info:
                contact_info = HARDCODED_RESPONSES.get("contact", "📞 +63 905-804-4426 or +63 969-251-0672\n📧 state101ortigasbranch@gmail.com")
            return f"⚠️ Our system is experiencing high traffic. Please try again or contact us directly:\n\n{contact_info}"

# ========= BASIC KB SYNC (PHASE 1: tasks 2-4) =========
# Support both local development and production deployment
KB_API_URL_LOCAL = "http://localhost:3000/api/knowledgebase"
KB_API_URL_PRODUCTION = "https://state101-travel-website.vercel.app/api/knowledgebase"
# Default to production, override with KB_API_URL in secrets for local dev
KB_API_URL_DEFAULT = KB_API_URL_PRODUCTION
FACTS_URL_DEFAULT = "http://localhost:3000/api/facts"

# We enforce strict precedence: KB (/api/knowledgebase) > HARDCODED_RESPONSES
# This ensures CMS updates by non-technical staff always take priority over footer data.
@st.cache_data(ttl=300)
def get_cms_facts():
    url = st.secrets.get("FACTS_URL", FACTS_URL_DEFAULT)
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        # Normalize shapes we expect
        if not isinstance(data, dict):
            return None
        phones = data.get("phones")
        if isinstance(phones, str):
            phones = [phones]
        elif not isinstance(phones, list):
            phones = []
        return {
            "address": (data.get("address") or "").strip(),
            "phones": [p for p in (phones or []) if p],
            "email": (data.get("email") or "").strip(),
            "hours": (data.get("hours") or "").strip(),
            "website_url": (data.get("website_url") or "").strip(),
        }
    except Exception:
        return None

def _kb_index_path() -> Path:
    return Path("knowledge") / ".knowledge_index.json"

def _load_kb_index() -> dict:
    p = _kb_index_path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def _save_kb_index(idx: dict) -> None:
    p = _kb_index_path()
    p.write_text(json.dumps(idx, indent=2), encoding="utf-8")

def _item_hash(item: dict) -> str:
    raw = f"{item.get('title','')}|{item.get('category','')}|{item.get('content','')}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def sync_remote_knowledgebase():
    """Fetch website CMS knowledgebase and mirror into knowledge/*.md.
    Basic fallback: if fetch fails or returns empty, do nothing and report status.
    Returns a status dict for UI feedback.
    """
    kb_url = st.secrets.get("KB_API_URL", KB_API_URL_DEFAULT)
    status = {"ok": False, "count": 0, "changed": 0, "error": None, "stale": False}
    try:
        resp = requests.get(kb_url, timeout=15)
        resp.raise_for_status()
        items = resp.json()
    except Exception as e:
        status["error"] = f"fetch-failed: {e}"
        return status

    status["count"] = len(items) if isinstance(items, list) else 0
    if not items:
        # Basic fallback: leave local snapshot untouched; mark as stale
        status["error"] = "remote-empty"
        status["stale"] = True
        return status

    kb_dir = Path("knowledge")
    kb_dir.mkdir(exist_ok=True)

    # Group items by category and merge multiple items into one file per category
    category_items = {}
    for it in items:
        try:
            category = (it.get("category") or "").strip().lower()
            if not category:
                continue
            if category not in category_items:
                category_items[category] = []
            category_items[category].append({
                "id": it.get("id"),
                "title": (it.get("title") or "").strip(),
                "content": (it.get("content") or "").rstrip(),
                "updated": (it.get("updatedAt") or "").strip(),
            })
        except Exception:
            continue

    # Hash index: track changes per category (not per ID)
    index = _load_kb_index()
    new_index = {}
    changed = 0
    
    for category, cat_items in category_items.items():
        try:
            # Sanitize category name for filename (remove spaces, special chars)
            safe_category = re.sub(r'[^\w\-]', '_', category).strip('_')
            if not safe_category:
                continue
                
            # Merge multiple items in same category with section headers
            if len(cat_items) == 1:
                # Single item: use content as-is
                merged_content = cat_items[0]["content"]
                merged_title = cat_items[0]["title"]
            else:
                # Multiple items: merge with section headers
                merged_title = f"{category.title()} Information"
                sections = []
                for item in cat_items:
                    sections.append(f"## {item['title']}\n\n{item['content']}")
                merged_content = "\n\n---\n\n".join(sections)
            
            # Get most recent update timestamp
            latest_updated = max((item["updated"] for item in cat_items if item["updated"]), default="")
            
            # Create hash from merged content
            hash_input = f"{merged_title}|{category}|{merged_content}"
            h = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()
            
            # Check if content changed
            if index.get(category) == h:
                new_index[category] = h
                continue
            
            # Write category-based filename (e.g., kb_contact.md, kb_location.md)
            md_path = kb_dir / f"kb_{safe_category}.md"
            md = textwrap.dedent(f"""
            ---
            title: {merged_title}
            category: {category}
            updated: {latest_updated}
            items: {len(cat_items)}
            ---

            {merged_content}
            """).lstrip()
            md_path.write_text(md, encoding="utf-8")
            new_index[category] = h
            changed += 1
        except Exception:
            continue
    
    # Clean up old ID-based files (kb_cmi*.md) if they exist
    try:
        for old_file in kb_dir.glob("kb_cmi*.md"):
            old_file.unlink()
    except Exception:
        pass

    # Save new index
    try:
        _save_kb_index(new_index)
    except Exception:
        pass

    # Mark success and return status
    status["ok"] = True
    status["changed"] = changed
    return status

# ========== DEAD CODE (Application Form Functions - No Longer Used) ==========
# The following functions are commented out as the application form has been moved to the website.
# These are kept for reference but are not called anywhere in the active code.

# # ========== GOOGLE SHEETS INTEGRATION ==========
# @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
# def save_to_sheet(data):
#     try:
#         creds = Credentials.from_service_account_info(
#             st.secrets["GCP_SERVICE_ACCOUNT"],
#             scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
#         )
#         sheet = gspread.authorize(creds).open("state101application").sheet1
#         sheet.append_row(data)
#         return True
#     except Exception:
#         return False

# # ========== EMAIL SENDING (REPLACES SHEETS SUBMISSION) ==========
# def send_application_email(form_data, uploaded_files, drive_folder_url: str | None = None):
#     ... (function body omitted for brevity)

# # ========== GOOGLE DRIVE BACKUP ==========
# def upload_to_drive(form_data, uploaded_files):
#     ... (function body omitted for brevity)

# # ========== VALIDATION HELPERS ==========
# def _is_valid_email(addr: str) -> Tuple[bool, str | None]:
#     ... (function body omitted for brevity)

# def _validate_ph_phone(num: str) -> Tuple[bool, str | None]:
#     ... (function body omitted for brevity)

# # ========== APPLICATION FORM ==========
# def show_application_form():
#     ... (function body omitted for brevity)

# def show_requirements():
#     ... (function body omitted for brevity)

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
    /* Force the form submit button and its inner elements to use blue text regardless of nested styling */
    /* More aggressive selector set to force blue text for submit button including nested spans */
    .stForm .stButton > button,
    .stForm .stButton > button *,
    .stForm .stButton>button span,
    .stForm .stButton>button div {{
        color: #1E90FF !important;
        -webkit-text-fill-color: #1E90FF !important;
    }}
    .stForm .stButton > button {{
        background-color: #000000 !important;
        border: 2px solid {theme['accent']} !important;
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
        layout="centered",  # center the main content for better desktop/mobile look
        initial_sidebar_state="collapsed"  # sidebar starts hidden
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
• Information & Guidance: The chatbot provides information about visas, requirements, and services.
• Application & Requirements: Users are directed to https://state101-travel-website.vercel.app/services for the official application form and detailed requirements checklist.
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

        # Center the main content with responsive max width
        st.markdown(
                """
                <style>
                    /* Center the main content with responsive max width */
                    .block-container {
                        max-width: 900px;
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

    # Hidden sidebar for admin functions (KB sync)
    with st.sidebar:
        st.markdown("### ⚙️ Admin Tools")
        st.caption("Knowledge Base Management")
        
        if st.button("🔄 Refresh Knowledgebase", use_container_width=True, key="sidebar_kb_refresh"):
            status = sync_remote_knowledgebase()
            if status.get("ok"):
                # Rebuild assistant so new files are indexed when RAG is enabled
                st.session_state.chatbot = VisaAssistant()
                st.success(f"✅ Synced {status['count']} items\n📝 Updated {status['changed']} files")
                st.session_state["last_kb_sync"] = {
                    "ts": time.strftime('%Y-%m-%d %H:%M'),
                    "count": status.get("count", 0),
                    "changed": status.get("changed", 0),
                }
            else:
                err = status.get("error") or "unknown"
                if status.get("stale") or err == "remote-empty":
                    st.warning("⚠️ KB is empty remotely. Keeping local snapshot.")
                else:
                    st.error(f"❌ KB sync failed: {err}")
        
        if st.session_state.get("last_kb_sync"):
            meta = st.session_state["last_kb_sync"]
            st.divider()
            st.caption("**Last Sync:**")
            st.caption(f"🕒 {meta['ts']}")
            st.caption(f"📊 Items: {meta['count']} | Changed: {meta['changed']}")

    # Single tab interface - chat only (application and requirements moved to website)
    st.markdown("### 💬 Chat with us about US/Canada Visa Services")
    st.caption("For applications and requirements, visit: https://state101-travel-website.vercel.app/services")
    st.divider()

    # Create a container for chat messages
    chat_container = st.container()
    
    # Display chat messages
    with chat_container:
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
    
    # Add empty space to push content up
    st.markdown("<br>" * 2, unsafe_allow_html=True)

    # Input box at the bottom
    user_prompt = st.chat_input("Ask about US and Canada visas...")
    if user_prompt:
        # Show user's message
        st.session_state.messages.append({"role": "user", "content": user_prompt})
        
        # Get assistant response with user-friendly status
        # Ensure instance has the latest method (handles rare hot-reload edge cases)
        bot = st.session_state.get("chatbot")
        if bot is None or not hasattr(bot, "generate") or not callable(getattr(bot, "generate", None)):
            st.session_state.chatbot = VisaAssistant()
            bot = st.session_state.chatbot
        
        # Show friendly thinking message while processing
        with st.spinner("💭 Thinking longer for accurate answer..."):
            bot_response = bot.generate(user_prompt)
        
        st.session_state.messages.append({"role": "assistant", "content": bot_response})
        
        # Rerun to refresh and show new messages
        st.rerun()

if __name__ == "__main__":
    main()
















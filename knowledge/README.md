# Knowledge Base for State101 Chatbot

Place your reference content here. Supported file types out of the box:

- .md (Markdown)
- .txt (Plain text)

PDFs can be enabled by installing `pypdf` and we can turn it on later.

Recommended structure:

- `faqs.md` – longer answers, talking points, policy blurbs
- `programs.md` – program descriptions, pathways, notes
- `process.md` – step-by-step guides and outlines

Notes:
- This folder is indexed at app startup when `RAG_ENABLED=true` in `.streamlit/secrets.toml`.
- Content is chunked and retrieved per user query; the top-k chunks are passed to the LLM with your canonical FACTS.
- Canonical items (address, hours, phones, email) continue to come from HARDCODED FACTS to avoid drift.

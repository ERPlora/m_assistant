# AI Assistant Module

AI-powered business assistant for ERPlora Hub. Configures the hub, manages operations, and processes documents via conversational AI.

## Features

### Chat Interface
- Real-time SSE streaming with agentic loop (up to 10 tool iterations)
- Voice input via Web Speech API
- Action confirmation for write operations (create, update, delete)
- Conversation history and action log audit trail

### AI Tools
- **13 hub core tools**: get/update config, list modules/roles/employees, create roles/employees/tax classes
- **4 setup wizard tools**: regional config, business info, tax config, complete setup
- **90+ module tools**: auto-discovered from active modules' `ai_tools.py` files

### File Upload & Document Processing

Upload any document to the chat — the assistant reads it and takes action using the appropriate module tools.

**Combined processing strategy:**
1. **PDF with text** → `pdfplumber` extracts text + tables locally (cheap, fast)
2. **Scanned PDF / photo** → `PyMuPDF` converts to PNG → GPT-5 Vision reads it
3. **Images** (jpg, png, webp) → base64 → GPT-5 Vision
4. **Text / CSV** → read directly
5. **Excel** (.xlsx) → `openpyxl` extracts cell data
6. **Word** (.docx) → `python-docx` extracts paragraphs

**Max file size:** 10 MB | **Max PDF pages:** 5 (for Vision) / 20 (for text extraction)

#### Document Use Cases

| Document | What the AI does |
|----------|-----------------|
| **Delivery note (albarán)** | Extracts products, quantities, prices → updates stock via `inventory` tools |
| **Supplier invoice** | Reads line items, amounts, VAT → creates expense or purchase order |
| **Competitor menu** | Reads dishes and prices → comparison analysis |
| **Product catalog** | Imports products into `inventory` catalog |
| **Receipt / ticket photo** | Reads sale lines → registers in accounting |
| **Employee contract** | Extracts personal data → creates profile in `staff` |
| **Work schedule** | Reads shifts → configures in `schedules` / `workforce_planning` |
| **Price list (Excel)** | Reads rows → bulk updates prices in `inventory` |
| **Order email** | Extracts products + quantities → creates `order` |
| **ID card / DNI photo** | Reads name, ID number → fills employee data |
| **Training certificate** | Registers completion in `training` module |

The assistant is not limited to these — it can process any document GPT-5 can read and map it to available module tools.

### Setup Wizard
- Special `setup` context for first-time hub configuration
- 4-step guided flow: Regional → Modules → Business → Tax
- Can be skipped for manual configuration

### Subscription Tiers

All tiers use GPT-5. Differentiated by message allowance.

| Tier | Price/mo | Messages/mo | Features |
|------|----------|-------------|----------|
| Free | €0 | 30 | chat, tools, setup, files, images |
| Basic | €11.99 | 500 | chat, tools, setup, files, images |
| Pro | €44.99 | 2,000 | chat, tools, setup, files, images |
| Enterprise | €179.99 | 8,000 | + priority support |

---

## Architecture

### Agentic Loop Flow

```
1. User sends message (+ optional files) via POST /m/assistant/chat
2. Hub processes files → builds multimodal input (text + images)
3. Browser opens SSE stream to GET /m/assistant/stream/{request_id}
4. Hub calls Cloud proxy (POST /api/hubs/me/assistant/chat/stream/)
5. Cloud forwards to GPT-5 with tools schema
6. GPT-5 returns text + function_calls
7. Hub re-emits text deltas to browser (real-time)
8. For each function_call:
   - Read tool → execute immediately, send result back to GPT
   - Write tool → create ActionLog, emit confirmation HTML, pause
   - User confirms → execute tool, log result
9. Loop until no more function_calls (max 10 iterations)
10. Emit done event with conversation_id + tier info
```

### Tool Discovery

Each module can provide `ai_tools.py` with `@register_tool` decorated classes. The assistant auto-discovers all tools from active modules at startup. Tools are filtered by:
- Module active status
- User permissions
- Context (general vs setup)
- Setup-only flag

### Cloud Proxy

Hub never calls OpenAI directly. All LLM traffic goes through Cloud:
- Hub → Cloud (`/api/hubs/me/assistant/chat/stream/`)
- Cloud → OpenAI GPT-5 (Chat Completions API with streaming)
- Cloud manages API keys, usage tracking, tier enforcement
- Conversation history stored and compressed server-side in Cloud

---

## Data Model

### AssistantConversation
Tracks conversation state per user: `openai_response_id` (for threading), `context` (general/setup).

### AssistantActionLog
Audit trail: `tool_name`, `tool_args` (JSONB), `result` (JSONB), `success`, `confirmed`, `error_message`.

---

## Routes

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Chat page |
| GET | `/chat` | Chat page (alias) |
| GET | `/history` | Conversation history |
| GET | `/logs` | Action log |
| POST | `/skip-setup` | Skip setup wizard |
| POST | `/chat` | Send message (+ files) → returns request_id |
| GET | `/stream/{request_id}` | SSE stream (agentic loop) |
| POST | `/confirm/{log_id}` | Confirm pending write action |
| POST | `/cancel/{log_id}` | Cancel pending action |

---

## File Processing Details

### Processing Pipeline

```
Upload → detect MIME type → route to handler:

image/*           → base64 encode → [input_image] for Vision
application/pdf   → pdfplumber extract text
                    → if text found (>50 chars): [input_text]
                    → if scanned: PyMuPDF → PNG → [input_image] for Vision
text/plain, csv   → read UTF-8 (fallback Latin-1) → [input_text]
xlsx              → openpyxl read cells → [input_text]
docx              → python-docx read paragraphs → [input_text]
```

### Cost Optimization

| Method | Token cost | When used |
|--------|-----------|-----------|
| Text extraction (pdfplumber) | ~$0.004/page | Digital PDFs (80% of business documents) |
| Vision (GPT-5) | ~$0.01-0.03/image | Scanned PDFs, photos, handwritten docs |

Most business documents (invoices, delivery notes, price lists) are digital PDFs → text extraction is cheap and fast. Photos from mobile phones fall back to Vision automatically.

### Dependencies

- `pdfplumber` — PDF text + table extraction (local, no API)
- `pymupdf` — PDF to image conversion (local, no API)
- `openpyxl` — Excel reading (optional, graceful fallback)
- `python-docx` — Word reading (optional, graceful fallback)

---

## Testing

```bash
cd hub-next
source .venv/bin/activate
python -m pytest modules/assistant/tests/ -v
```

**71 tests** across 8 test files:
- `test_models.py` — Model fields, table names, column existence
- `test_prompts.py` — System prompt builder (base, user, store, modules, setup context)
- `test_tools.py` — Tool registry, permissions, schema generation
- `test_config_state.py` — Selected blocks helpers
- `test_routes.py` — Confirmation text formatting, schemas, stream cache
- `test_file_processor.py` — All file types, edge cases (too large, unsupported, empty)

---

## Module Manifest

```python
MODULE_ID = "assistant"
MODULE_NAME = "AI Assistant"
MODULE_VERSION = "1.4.0"
MODULE_ICON = "sparkles-outline"
MODULE_CATEGORY = "utility"
```

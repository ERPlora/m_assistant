"""
AI Assistant routes — FastAPI router.

Handles chat page rendering, SSE streaming with agentic loop,
and action confirmation. Mounted at /m/assistant/ by ModuleRuntime.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import httpx
from cachetools import TTLCache
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app.ai.registry import TOOL_REGISTRY, get_tools_for_user, tools_to_openai_schema
from app.core.db.query import HubQuery
from app.core.db.transactions import atomic
from app.core.dependencies import CurrentUser, DbSession, HubId
from app.core.htmx import htmx_view
from app.core.sse import sse_stream

from .models import AssistantActionLog, AssistantConversation
from .prompts import build_system_prompt

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_TOOL_ITERATIONS = 10
_stream_cache: TTLCache = TTLCache(maxsize=256, ttl=120)


# ============================================================================
# PAGE VIEWS
# ============================================================================


@router.get("/")
@router.get("/chat")
@htmx_view(module_id="assistant", view_id="chat")
async def chat_page(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    hub_id: HubId,
    context: str = "general",
):
    """Main chat page."""
    if context not in ("general", "setup"):
        context = "general"

    user_id = getattr(request.state, "user_id", None)
    query = HubQuery(AssistantConversation, db, hub_id)
    conversations = (
        await query
        .filter(AssistantConversation.created_by == user_id)
        .order_by(AssistantConversation.updated_at.desc())
        .limit(10)
        .all()
    )

    return {
        "conversations": conversations,
        "context": context,
    }


@router.get("/history")
@htmx_view(module_id="assistant", view_id="history")
async def history_page(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    hub_id: HubId,
):
    """Conversation history page."""
    user_id = getattr(request.state, "user_id", None)
    query = HubQuery(AssistantConversation, db, hub_id)
    conversations = (
        await query
        .filter(AssistantConversation.created_by == user_id)
        .order_by(AssistantConversation.updated_at.desc())
        .limit(50)
        .all()
    )

    return {"conversations": conversations}


@router.get("/logs")
@htmx_view(module_id="assistant", view_id="logs")
async def logs_page(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    hub_id: HubId,
):
    """Action log page."""
    user_id = getattr(request.state, "user_id", None)
    query = HubQuery(AssistantActionLog, db, hub_id)
    logs = (
        await query
        .filter(AssistantActionLog.created_by == user_id)
        .order_by(AssistantActionLog.created_at.desc())
        .limit(100)
        .all()
    )

    return {"logs": logs}


# ============================================================================
# CHAT API — SSE STREAMING
# ============================================================================


@router.post("/skip-setup")
async def skip_setup(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    hub_id: HubId,
) -> JSONResponse:
    """Skip the setup wizard and configure manually later."""
    from app.apps.configuration.models import HubConfig, StoreConfig

    async with atomic(db) as session:
        hub_config = await HubConfig.get_config(session, hub_id)
        store_config = await StoreConfig.get_config(session, hub_id)

        if hub_config and not hub_config.is_configured:
            hub_config.is_configured = True

        if store_config and not store_config.is_configured:
            store_config.is_configured = True

    return JSONResponse({"success": True, "redirect_url": "/"})


@router.post("/chat")
async def chat(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    hub_id: HubId,
) -> JSONResponse:
    """Initiate a chat message. Returns a request_id for SSE streaming."""
    form = await request.form()
    message = (form.get("message") or "").strip()
    conversation_id = form.get("conversation_id", "")
    context = form.get("context", "general")

    # Handle file uploads
    attachments: list[dict] = []
    for key in form:
        if key.startswith("file"):
            upload = form[key]
            if hasattr(upload, "read"):
                file_bytes = await upload.read()
                if file_bytes:
                    attachments.append({
                        "bytes": file_bytes,
                        "filename": upload.filename or "file",
                        "content_type": upload.content_type or "application/octet-stream",
                    })

    if not message and not attachments:
        return JSONResponse({"error": "Please type a message or attach a file."}, status_code=400)

    user_id = getattr(request.state, "user_id", None)

    # Get or create conversation
    conversation = await _get_or_create_conversation(
        db, hub_id, user_id, conversation_id, context,
    )

    # Generate a unique request ID for this stream
    request_id = uuid.uuid4().hex[:16]

    # Store request data in cache for the stream endpoint
    _stream_cache[request_id] = {
        "message": message,
        "attachments": attachments,
        "conversation_id": str(conversation.id),
        "context": context,
        "user_id": str(user_id) if user_id else None,
        "hub_id": str(hub_id),
    }

    return JSONResponse({
        "request_id": request_id,
        "conversation_id": str(conversation.id),
    })


@router.get("/stream/{request_id}")
async def chat_stream(
    request: Request,
    request_id: str,
    db: DbSession,
    user: CurrentUser,
    hub_id: HubId,
):
    """SSE endpoint that runs the agentic loop and streams events."""
    req_data = _stream_cache.pop(request_id, None)
    if not req_data:

        async def _expired() -> AsyncGenerator[dict]:
            yield {"type": "error", "message": "Request expired or not found."}

        return await sse_stream(request, _expired())

    return await sse_stream(
        request,
        _stream_agentic_loop(req_data, request, db, hub_id),
    )


async def _stream_agentic_loop(
    req_data: dict[str, Any],
    request: Request,
    db: DbSession,
    hub_id: uuid.UUID,
) -> AsyncGenerator[dict[str, Any]]:
    """Async generator that runs the agentic loop and yields SSE events."""
    from app.apps.configuration.models import HubConfig

    message = req_data["message"]
    attachments = req_data.get("attachments", [])
    conversation_id = req_data["conversation_id"]
    context = req_data["context"]
    user_id_str = req_data["user_id"]

    # Load conversation
    query = HubQuery(AssistantConversation, db, hub_id)
    try:
        conversation = await query.get(uuid.UUID(conversation_id))
    except Exception:
        yield {"type": "error", "message": "Conversation not found."}
        return

    if not conversation:
        yield {"type": "error", "message": "Conversation not found."}
        return

    # Build system prompt and tools
    instructions = await build_system_prompt(request, context)
    user_permissions: list[str] = getattr(request.state, "user_permissions", [])
    setup_mode = context == "setup"
    available_tools = get_tools_for_user(user_permissions, setup_mode=setup_mode)
    tools_schema = tools_to_openai_schema(available_tools)

    # Cloud config
    async with atomic(db) as session:
        hub_config = await HubConfig.get_config(session, hub_id)
        if not hub_config or not hub_config.hub_jwt:
            yield {"type": "error", "message": "Hub is not connected to Cloud."}
            return
        hub_jwt = hub_config.hub_jwt
        cloud_api_url = hub_config.cloud_api_url or "https://erplora.com"

    # Build multimodal input when attachments are present
    if attachments:
        from .services.file_processor import process_file

        content_parts: list[dict] = []
        if message:
            content_parts.append({"type": "input_text", "text": message})
        for att in attachments:
            file_parts = await process_file(att["bytes"], att["filename"], att["content_type"])
            content_parts.extend(file_parts)
        initial_input: Any = content_parts
    else:
        initial_input = message

    # Agentic loop state
    openai_input: Any = initial_input
    previous_response_id = conversation.openai_response_id or None
    is_new_session = not conversation.openai_response_id
    pending_confirmation: dict | None = None
    tier_info: dict | None = None

    for iteration in range(MAX_TOOL_ITERATIONS):
        yield {"type": "thinking", "iteration": iteration + 1}

        # Build payload
        payload: dict[str, Any] = {"input": openai_input, "instructions": instructions}
        if tools_schema:
            payload["tools"] = tools_schema
        if previous_response_id:
            payload["previous_response_id"] = previous_response_id
        if is_new_session and iteration == 0:
            payload["new_session"] = True

        # Call Cloud streaming endpoint
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST",
                    f"{cloud_api_url}/api/v1/hub/device/assistant/chat/stream/",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {hub_jwt}",
                        "Content-Type": "application/json",
                    },
                ) as cloud_response:
                    if cloud_response.status_code != 200:
                        body = await cloud_response.aread()
                        error_msg = "AI service error"
                        try:
                            error_data = json.loads(body)
                            error_msg = error_data.get("error", body.decode()[:200])
                        except Exception:
                            error_msg = body.decode()[:200]

                        if cloud_response.status_code == 403:
                            error_msg = "AI Assistant subscription required."
                        elif cloud_response.status_code == 429:
                            error_msg = "Monthly usage limit reached."

                        yield {"type": "error", "message": error_msg}
                        return

                    # Extract tier info from headers
                    tier_header = cloud_response.headers.get("X-Assistant-Tier")
                    usage_header = cloud_response.headers.get("X-Assistant-Usage")
                    if tier_header:
                        tier_info = {"tier": tier_header}
                        if usage_header:
                            try:
                                tier_info.update(json.loads(usage_header))
                            except (json.JSONDecodeError, TypeError):
                                pass

                    # Parse SSE stream from Cloud
                    response_data: dict | None = None
                    function_calls: list[dict] = []
                    cloud_error: str | None = None

                    async for line in cloud_response.aiter_lines():
                        if not line or not line.startswith("data: "):
                            continue

                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break

                        try:
                            event = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue

                        event_type = event.get("type", "")

                        if event_type == "text_delta":
                            yield event
                        elif event_type == "function_call":
                            function_calls.append(event)
                        elif event_type == "response":
                            response_data = event
                        elif event_type == "error":
                            cloud_error = event.get("message", "Unknown AI error")

        except httpx.HTTPError as e:
            logger.error("[ASSISTANT] Cloud stream connection error: %s", e)
            yield {"type": "error", "message": f"Error connecting to AI service: {e!s}"}
            return

        if cloud_error:
            yield {"type": "error", "message": cloud_error}
            return

        if not response_data:
            yield {"type": "error", "message": "No response from AI service."}
            return

        # Save response ID for conversation threading
        response_id = response_data.get("id", "")
        if response_id:
            async with atomic(db) as session:
                conv = await session.get(AssistantConversation, conversation.id)
                if conv:
                    conv.openai_response_id = response_id

        # If no function calls, we're done
        if not function_calls:
            break

        # Execute function calls
        tool_results: list[dict] = []
        for fc in function_calls:
            tool_name = fc.get("name", "")
            call_id = fc.get("call_id", "")
            try:
                tool_args = json.loads(fc.get("arguments", "{}"))
            except json.JSONDecodeError:
                tool_args = {}

            tool = TOOL_REGISTRY.get(tool_name)
            if not tool:
                tool_results.append({
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps({"error": f"Unknown tool: {tool_name}"}),
                })
                continue

            # Permission check
            if tool.required_permission and tool.required_permission not in user_permissions:
                tool_results.append({
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps({"error": f"Permission denied: {tool.required_permission}"}),
                })
                continue

            # Confirmation check
            if tool.requires_confirmation:
                user_id = uuid.UUID(user_id_str) if user_id_str else None
                async with atomic(db) as session:
                    action_log = AssistantActionLog(
                        hub_id=hub_id,
                        created_by=user_id,
                        conversation_id=conversation.id,
                        tool_name=tool_name,
                        tool_args=tool_args,
                        result={},
                        success=False,
                        confirmed=False,
                    )
                    session.add(action_log)
                    await session.flush()
                    log_id = action_log.id

                pending_confirmation = {
                    "log_id": str(log_id),
                    "tool_name": tool_name,
                    "tool_args": tool_args,
                    "tool_description": tool.description,
                }
                tool_results.append({
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps({
                        "status": "pending_confirmation",
                        "message": f"Action '{tool_name}' requires user confirmation.",
                        "action_id": str(log_id),
                    }),
                })
                break
            else:
                # Execute read tool
                yield {"type": "tool", "name": tool_name, "args": tool_args}
                user_id = uuid.UUID(user_id_str) if user_id_str else None
                try:
                    result = await tool.execute(tool_args, request)
                    async with atomic(db) as session:
                        action_log = AssistantActionLog(
                            hub_id=hub_id,
                            created_by=user_id,
                            conversation_id=conversation.id,
                            tool_name=tool_name,
                            tool_args=tool_args,
                            result=result,
                            success=True,
                            confirmed=True,
                        )
                        session.add(action_log)
                    tool_results.append({
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": json.dumps(result),
                    })
                    yield {"type": "tool_result", "name": tool_name, "success": True}
                except Exception as e:
                    logger.error("[ASSISTANT] Tool %s error: %s", tool_name, e, exc_info=True)
                    async with atomic(db) as session:
                        action_log = AssistantActionLog(
                            hub_id=hub_id,
                            created_by=user_id,
                            conversation_id=conversation.id,
                            tool_name=tool_name,
                            tool_args=tool_args,
                            result={"error": str(e)},
                            success=False,
                            confirmed=True,
                            error_message=str(e),
                        )
                        session.add(action_log)
                    tool_results.append({
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": json.dumps({"error": str(e)}),
                    })
                    yield {"type": "tool_result", "name": tool_name, "success": False}

        # If pending confirmation, emit HTML and stop
        if pending_confirmation:
            confirmation_html = _render_confirmation(
                request, pending_confirmation,
            )
            yield {"type": "confirmation", "html": confirmation_html}
            # Send results back for one more LLM iteration before stopping
            openai_input = tool_results
            previous_response_id = response_id
            # Don't continue the agentic loop — wait for user confirmation
            break

        # Send tool results back for next iteration
        if tool_results:
            openai_input = tool_results
            previous_response_id = response_id
        else:
            break

    # Done
    yield {
        "type": "done",
        "conversation_id": str(conversation.id),
        "tier_info": tier_info,
    }

    logger.info(
        "[ASSISTANT] Stream completed: conversation=%s iterations=%d confirmation=%s",
        conversation.id,
        iteration + 1,
        pending_confirmation is not None,
    )


# ============================================================================
# CONFIRMATION ACTIONS
# ============================================================================


@router.post("/confirm/{log_id}")
async def confirm_action(
    request: Request,
    log_id: str,
    db: DbSession,
    user: CurrentUser,
    hub_id: HubId,
) -> HTMLResponse:
    """Confirm and execute a pending write action."""
    user_id = getattr(request.state, "user_id", None)

    query = HubQuery(AssistantActionLog, db, hub_id)
    action_log = await query.get(uuid.UUID(log_id))

    if not action_log or action_log.created_by != user_id or action_log.confirmed:
        return HTMLResponse(_render_message(request, "system", "Action not found or already processed."))

    tool = TOOL_REGISTRY.get(action_log.tool_name)
    if not tool:
        async with atomic(db) as session:
            log = await session.get(AssistantActionLog, action_log.id)
            if log:
                log.error_message = f"Tool {action_log.tool_name} not found"
        return HTMLResponse(_render_message(request, "system", f"Error: Tool {action_log.tool_name} not found.", error=True))

    try:
        result = await tool.execute(action_log.tool_args, request)
        async with atomic(db) as session:
            log = await session.get(AssistantActionLog, action_log.id)
            if log:
                log.result = result
                log.success = True
                log.confirmed = True
        return HTMLResponse(_render_message(request, "system", "Action confirmed and executed successfully.", success=True))
    except Exception as e:
        logger.error("[ASSISTANT] Confirm action error: %s", e, exc_info=True)
        async with atomic(db) as session:
            log = await session.get(AssistantActionLog, action_log.id)
            if log:
                log.result = {"error": str(e)}
                log.success = False
                log.confirmed = True
                log.error_message = str(e)
        return HTMLResponse(_render_message(request, "system", f"Error executing action: {e!s}", error=True))


@router.post("/cancel/{log_id}")
async def cancel_action(
    request: Request,
    log_id: str,
    db: DbSession,
    user: CurrentUser,
    hub_id: HubId,
) -> HTMLResponse:
    """Cancel a pending write action."""
    user_id = getattr(request.state, "user_id", None)

    try:
        query = HubQuery(AssistantActionLog, db, hub_id)
        action_log = await query.get(uuid.UUID(log_id))
        if action_log and action_log.created_by == user_id and not action_log.confirmed:
            async with atomic(db) as session:
                log = await session.get(AssistantActionLog, action_log.id)
                if log:
                    await session.delete(log)
    except Exception:
        pass

    return HTMLResponse(_render_message(request, "system", "Action cancelled."))


# ============================================================================
# HELPERS
# ============================================================================


async def _get_or_create_conversation(
    db: DbSession,
    hub_id: uuid.UUID,
    user_id: uuid.UUID | None,
    conversation_id: str,
    context: str,
) -> AssistantConversation:
    """Get existing conversation or create a new one."""
    if conversation_id:
        try:
            query = HubQuery(AssistantConversation, db, hub_id)
            conv = await query.get(uuid.UUID(conversation_id))
            if conv and conv.created_by == user_id:
                return conv
        except (ValueError, Exception):
            pass

    async with atomic(db) as session:
        conversation = AssistantConversation(
            hub_id=hub_id,
            created_by=user_id,
            context=context,
        )
        session.add(conversation)
        await session.flush()
        return conversation


def _render_confirmation(request: Request, data: dict) -> str:
    """Render confirmation HTML partial."""
    templates = request.app.state.templates
    tpl = templates.env.get_template("assistant/partials/confirmation.html")
    return tpl.render(
        log_id=data["log_id"],
        tool_name=data["tool_name"],
        tool_args=data["tool_args"],
        description=_format_confirmation_text(data["tool_name"], data["tool_args"]),
    )


def _render_message(
    request: Request,
    role: str,
    content: str,
    *,
    success: bool = False,
    error: bool = False,
) -> str:
    """Render a single message HTML."""
    templates = request.app.state.templates
    tpl = templates.env.get_template("assistant/partials/message.html")
    return tpl.render(role=role, content=content, success=success, error=error)


def _format_confirmation_text(tool_name: str, tool_args: dict) -> str:
    """Format a human-readable description of the pending action."""
    descriptions: dict[str, Any] = {
        # Hub core tools
        "update_store_config": lambda a: f"Update store: {', '.join(k for k, v in a.items() if v is not None)}",
        "select_blocks": lambda a: f"Select blocks: {', '.join(a.get('block_slugs', []))}",
        "enable_module": lambda a: f"Enable module: {a.get('module_id', '')}",
        "disable_module": lambda a: f"Disable module: {a.get('module_id', '')}",
        "create_role": lambda a: f"Create role: {a.get('display_name', a.get('name', ''))}",
        "create_employee": lambda a: f"Create employee: {a.get('name', '')} ({a.get('role_name', '')})",
        "create_tax_class": lambda a: f"Create tax: {a.get('name', '')} ({a.get('rate', '')}%)",
        "set_regional_config": lambda a: f"Set region: {', '.join(f'{k}={v}' for k, v in a.items() if v is not None)}",
        "set_business_info": lambda a: f"Set business: {a.get('business_name', '')}",
        "set_tax_config": lambda a: f"Set tax: {a.get('tax_rate', '')}% (included: {a.get('tax_included', '')})",
        "complete_setup_step": lambda a: "Complete hub setup",
        # Inventory
        "create_product": lambda a: f"Create product: {a.get('name', '')} ({a.get('price', '')})",
        "update_product": lambda a: f"Update product: {a.get('product_id', '')}",
        "create_category": lambda a: f"Create category: {a.get('name', '')}",
        "adjust_stock": lambda a: f"Adjust stock: {a.get('quantity', '')} units for product {a.get('product_id', '')}",
        # Customers
        "create_customer": lambda a: f"Create customer: {a.get('name', '')}",
        "update_customer": lambda a: f"Update customer: {a.get('customer_id', '')}",
        # Services
        "create_service": lambda a: f"Create service: {a.get('name', '')} ({a.get('price', '')})",
        # Quotes
        "create_quote": lambda a: f"Create quote: {a.get('title', '')}",
        # Leads
        "create_lead": lambda a: f"Create lead: {a.get('name', '')} ({a.get('company', '')})",
        "move_lead_stage": lambda a: f"Move lead {a.get('lead_id', '')} to stage {a.get('stage_id', '')}",
        # Purchase Orders
        "create_purchase_order": lambda a: f"Create purchase order for supplier {a.get('supplier_id', '')}",
        # Appointments
        "create_appointment": lambda a: f"Book appointment: {a.get('customer_name', '')} at {a.get('start_datetime', '')}",
        # Expenses
        "create_expense": lambda a: f"Record expense: {a.get('title', '')} ({a.get('amount', '')})",
        # Projects
        "create_project": lambda a: f"Create project: {a.get('name', '')}",
        "log_time_entry": lambda a: f"Log {a.get('hours', '')}h on project {a.get('project_id', '')}",
        # Support
        "create_ticket": lambda a: f"Create ticket: {a.get('subject', '')}",
        # Discounts
        "create_coupon": lambda a: f"Create coupon: {a.get('code', '')} ({a.get('discount_value', '')}{a.get('discount_type', '')})",
        # Loyalty
        "award_loyalty_points": lambda a: f"Award {a.get('points', '')} points to member {a.get('member_id', '')}",
        # Shipping
        "create_shipment": lambda a: f"Create shipment to {a.get('recipient_name', '')}",
        # Gift Cards
        "create_gift_card": lambda a: f"Create gift card: {a.get('initial_balance', '')} value",
    }

    formatter = descriptions.get(tool_name)
    if formatter:
        try:
            return formatter(tool_args)
        except Exception:
            pass

    args_str = ", ".join(f"{k}={v}" for k, v in tool_args.items() if v is not None)
    return f"{tool_name}({args_str})"

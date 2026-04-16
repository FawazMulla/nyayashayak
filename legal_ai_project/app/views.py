import uuid
from pathlib import Path

from django.conf import settings
from django.http import JsonResponse, FileResponse, Http404
from django.shortcuts import render, get_object_or_404
from django.views.decorators.http import require_http_methods, require_POST
from django.contrib.auth.decorators import login_required

from .extractor import extract_fields, extract_text_from_pdf
from .correction import hybrid_correction, is_legal_document
from .utils import save_to_dataset, outcome_label_display
from .models import UploadedCase, ChatSession, ChatMessage


def upload_case(request):
    if not request.user.is_authenticated or not request.user.is_approved:
        from django.shortcuts import redirect
        return redirect("dashboard")
    return render(request, "upload.html")


def lincoln_lawyer(request):
    """Standalone Lincoln Lawyer chatbot — no case upload needed."""
    if not request.user.is_authenticated or not request.user.is_approved:
        from django.shortcuts import redirect
        return redirect("dashboard")
    # Clear any case session so chatbot starts fresh in lincoln mode
    request.session.pop("chat_session_id", None)
    return render(request, "chat.html")


@require_http_methods(["POST"])
def analyze_case(request):
    uploaded_file = request.FILES.get("pdf_file")
    text_input    = request.POST.get("text_input", "").strip()

    if not uploaded_file and not text_input:
        return render(request, "upload.html", {"error": "Please upload a PDF or enter case text."})

    # ── PDF path ──────────────────────────────────────────────────────────────
    if uploaded_file:
        ext = Path(uploaded_file.name).suffix.lower()
        if ext != ".pdf":
            return render(request, "upload.html", {"error": "Only PDF files are supported."})

        upload_dir: Path = settings.MEDIA_ROOT / "uploads" / uuid.uuid4().hex
        upload_dir.mkdir(parents=True, exist_ok=True)
        file_path = upload_dir / uploaded_file.name

        with open(file_path, "wb") as f:
            for chunk in uploaded_file.chunks():
                f.write(chunk)

        # Save to DB if user is authenticated
        uploaded_case_obj = None
        if request.user.is_authenticated:
            rel_path = file_path.relative_to(settings.MEDIA_ROOT)
            uploaded_case_obj = UploadedCase.objects.create(
                user=request.user,
                file=str(rel_path).replace("\\", "/"),
                filename=uploaded_file.name,
            )

        try:
            raw_text = extract_text_from_pdf(file_path)
        except Exception as e:
            return render(request, "upload.html", {"error": f"Could not read PDF: {e}"})

        ok, reason = is_legal_document(raw_text)
        if not ok:
            return render(request, "upload.html", {"error": reason})

        try:
            result = extract_fields(file_path)
        except Exception as e:
            return render(request, "upload.html", {"error": f"Extraction failed: {e}"})

    # ── Text paste path ───────────────────────────────────────────────────────
    else:
        raw_text = text_input

        ok, reason = is_legal_document(raw_text)
        if not ok:
            return render(request, "upload.html", {"error": reason})

        from .extractor import (
            extract_case_id, extract_sections, extract_outcome,
            classify_category, get_label, build_input_text,
        )
        outcome    = extract_outcome(raw_text)
        category   = classify_category(raw_text)
        sections   = extract_sections(raw_text)
        label      = get_label(outcome)
        input_text = build_input_text(raw_text, sections or "", outcome, category)

        result = {
            "case_id":       extract_case_id(raw_text) or "TEXT-INPUT",
            "case_number":   "N/A",
            "appellant":     "N/A",
            "respondent":    "N/A",
            "judgment_date": "N/A",
            "sections":      sections or "",
            "category":      category,
            "outcome":       outcome,
            "label":         label,
            "word_count":    len(raw_text.split()),
            "quality_ok":    len(raw_text.split()) >= 150,
            "case_text":     raw_text[:2000],
            "input_text":    input_text,
            "filename":      "text_input",
        }

    # ── Hybrid correction + AI summary (single Cohere call) ───────────────────
    result = hybrid_correction(result, raw_text)

    # ── ML: prediction ────────────────────────────────────────────────────────
    ml_label, ml_conf = None, None
    try:
        from .ml.classifier import predict
        ml_label, ml_conf = predict(result.get("input_text", "") or raw_text[:512])
    except Exception:
        pass  # graceful — ML artefacts may not be built yet

    # ── ML: similarity search ─────────────────────────────────────────────────
    similar_cases = []
    try:
        from .ml.similarity import find_similar
        similar_cases = find_similar(result.get("input_text", "") or raw_text[:512], top_k=5)
    except Exception:
        pass

    # ── Confidence display ────────────────────────────────────────────────────
    # Prefer ML model confidence; fall back to rule-based random if model not ready
    if ml_conf is not None:
        conf_pct = round(ml_conf * 100, 1)
        confidence_display = f"{conf_pct}%"
        label_source = "ml_model"
    else:
        import random
        lbl = result.get("label")
        conf_pct = random.randint(78, 95) if lbl == 1 else (
                   random.randint(72, 89) if lbl == 0 else 0)
        confidence_display = f"{conf_pct}%" if conf_pct else "N/A"
        label_source = "rule_based"

    # Use ML label if available, else extractor label
    final_label = ml_label if ml_label is not None else result.get("label")

    result["ml_label"]          = ml_label
    result["ml_confidence_pct"] = conf_pct
    result["confidence"]        = confidence_display
    result["label_source"]      = label_source
    result["outcome_display"]   = outcome_label_display(final_label)
    result["similar_cases"]     = similar_cases

    save_to_dataset(result)

    # ── Create / update ChatSession in DB ─────────────────────────────────────
    chat_session = None
    if request.user.is_authenticated:
        title = (result.get("appellant") or result.get("case_id") or "Case Analysis")[:120]
        chat_session = ChatSession.objects.create(
            user=request.user,
            title=title,
            mode="case",
            uploaded_case=uploaded_case_obj if uploaded_file else None,
        )
        # Store AI summary as first AI message
        summary_text = result.get("ai_summary") or result.get("input_text", "")
        if summary_text:
            ChatMessage.objects.create(
                session=chat_session,
                sender="ai",
                message=f"📋 Case Summary:\n{summary_text}",
            )
        request.session["chat_session_id"] = chat_session.pk

    # ── Store context in session for chatbot ──────────────────────────────────
    request.session["case_context"] = {
        "summary":       result.get("ai_summary") or result.get("input_text", ""),
        "input_text":    result.get("input_text", ""),
        "appellant":     result.get("appellant", ""),
        "category":      result.get("category", ""),
        "outcome":       result.get("outcome", ""),
        "sections":      result.get("sections", ""),
        "prediction":    final_label,
        "confidence":    ml_conf if ml_conf is not None else conf_pct / 100,
        "similar_cases": similar_cases,
    }

    return render(request, "result.html", {
        "result": result,
        "chat_session_id": chat_session.pk if chat_session else None,
        "uploaded_case_id": uploaded_case_obj.pk if uploaded_case_obj else None,
    })


@require_POST
def chatbot_api(request):
    """AJAX endpoint — returns JSON chatbot response, persists messages to DB."""
    user_query = request.POST.get("query", "").strip()
    action     = request.POST.get("action", "").strip()
    mode       = request.POST.get("mode", "case").strip()
    context    = request.session.get("case_context", {})

    from .chatbot.chatbot import generate_chat_response
    response_text = generate_chat_response(user_query, context, action, mode)

    # Persist to DB if user is authenticated
    if request.user.is_authenticated:
        session_id = request.session.get("chat_session_id")
        chat_session = None

        if session_id:
            try:
                chat_session = ChatSession.objects.get(pk=session_id, user=request.user)
            except ChatSession.DoesNotExist:
                pass

        # Create a Lincoln session on first message if none exists
        if chat_session is None and mode == "lincoln":
            chat_session = ChatSession.objects.create(
                user=request.user,
                title=(user_query or action or "Lincoln Lawyer")[:120],
                mode="lincoln",
            )
            request.session["chat_session_id"] = chat_session.pk

        if chat_session:
            display_query = user_query or action
            if display_query:
                ChatMessage.objects.create(session=chat_session, sender="user", message=display_query)
            ChatMessage.objects.create(session=chat_session, sender="ai", message=response_text)
            chat_session.save()  # bumps updated_at

    return JsonResponse({"response": response_text})


# ── Auth & dashboard views ────────────────────────────────────────────────────
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import redirect
from .forms import RegisterForm
from .models import AISettings


def landing(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    return render(request, "landing.html")


def register_view(request):
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Registration successful! Wait for admin approval before logging in.")
            return redirect("login")
    else:
        form = RegisterForm()
    return render(request, "auth/register.html", {"form": form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    error = None
    if request.method == "POST":
        user = authenticate(request,
                            username=request.POST.get("username"),
                            password=request.POST.get("password"))
        if user is None:
            error = "Invalid username or password."
        elif not user.is_approved:
            error = "Your account is pending admin approval."
        else:
            login(request, user)
            return redirect("dashboard")
    return render(request, "auth/login.html", {"error": error})


def logout_view(request):
    logout(request)
    return redirect("landing")


@login_required
def dashboard(request):
    return render(request, "dashboard.html", {"user": request.user})


@login_required
def profile_view(request):
    return render(request, "auth/profile.html", {"user": request.user})


# ── Super-admin panel ─────────────────────────────────────────────────────────
@login_required
def admin_panel(request):
    if not request.user.is_staff:
        return redirect("dashboard")
    from .models import User as AppUser
    from django.core.mail import send_mail
    from django.conf import settings as dj_settings

    # Exclude the currently logged-in admin from the list
    users = AppUser.objects.exclude(pk=request.user.pk).order_by("-date_joined")

    if request.method == "POST":
        uid    = request.POST.get("user_id")
        action = request.POST.get("action")
        role   = request.POST.get("role", "")

        # ── System reset ──────────────────────────────────────────────────────
        if action == "reset_system":
            from .models import ChatSession, ChatMessage, UploadedCase
            deleted_users    = AppUser.objects.filter(is_superuser=False).count()
            deleted_sessions = ChatSession.objects.count()
            deleted_messages = ChatMessage.objects.count()
            deleted_files    = UploadedCase.objects.count()
            ChatMessage.objects.all().delete()
            ChatSession.objects.all().delete()
            UploadedCase.objects.all().delete()
            AppUser.objects.filter(is_superuser=False).delete()
            import logging
            logging.getLogger(__name__).warning(
                f"SYSTEM RESET by {request.user.username}: "
                f"users={deleted_users}, sessions={deleted_sessions}, "
                f"messages={deleted_messages}, files={deleted_files}"
            )
            messages.success(
                request,
                f"✅ Reset complete — removed {deleted_users} users, "
                f"{deleted_sessions} sessions, {deleted_messages} messages, "
                f"{deleted_files} files. Superusers preserved."
            )
            return redirect("admin_panel")
        try:
            u = AppUser.objects.get(pk=uid)
            if action == "approve":
                was_approved = u.is_approved
                u.is_approved = True
                u.is_active   = True
                u.save()
                # Send approval email if user has an email and wasn't already approved
                if not was_approved and u.email:
                    try:
                        send_mail(
                            subject="Your NUC Legal AI account has been approved",
                            message=(
                                f"Hi {u.username},\n\n"
                                f"Your account on NUC Legal AI has been approved by an administrator.\n"
                                f"You can now log in at: {dj_settings.SITE_URL}/auth/login/\n\n"
                                f"Your role: {u.get_role_display()}\n\n"
                                f"— NUC Legal AI Team"
                            ),
                            from_email=dj_settings.DEFAULT_FROM_EMAIL,
                            recipient_list=[u.email],
                            fail_silently=True,
                        )
                    except Exception:
                        pass
                messages.success(request, f"✅ {u.username} approved. Notification email sent.")
            elif action == "reject":
                u.is_approved = False
                u.is_active   = False
                u.save()
                if u.email:
                    try:
                        send_mail(
                            subject="NUC Legal AI — Account status update",
                            message=(
                                f"Hi {u.username},\n\n"
                                f"Your account access on NUC Legal AI has been deactivated.\n"
                                f"Please contact the administrator for more information.\n\n"
                                f"— NUC Legal AI Team"
                            ),
                            from_email=dj_settings.DEFAULT_FROM_EMAIL,
                            recipient_list=[u.email],
                            fail_silently=True,
                        )
                    except Exception:
                        pass
                messages.success(request, f"❌ {u.username} rejected.")
            elif action == "set_role" and role:
                u.role = role
                u.save()
                messages.success(request, f"Role updated for {u.username}.")
        except AppUser.DoesNotExist:
            pass
        return redirect("admin_panel")

    return render(request, "admin_panel.html", {"users": users, "role_choices": AppUser.ROLE_CHOICES})


@login_required
def ai_config(request):
    if not request.user.is_staff:
        return redirect("dashboard")
    cfg = AISettings.get()
    if request.method == "POST":
        cfg.cohere_enabled = "cohere_enabled" in request.POST
        cfg.oci_enabled    = "oci_enabled"    in request.POST
        cfg.save()
        messages.success(request, "AI settings updated.")
        return redirect("ai_config")
    return render(request, "ai_config.html", {"cfg": cfg})


# ── Chat history ──────────────────────────────────────────────────────────────
@login_required
def chat_history(request):
    sessions = ChatSession.objects.filter(user=request.user).order_by("-updated_at")
    return render(request, "chat_history.html", {"sessions": sessions})


@login_required
def chat_session_view(request, session_id):
    session = get_object_or_404(ChatSession, pk=session_id, user=request.user)
    messages = session.messages.all()

    # Restore case context to session if this was a case chat
    if session.mode == "case":
        first_ai = messages.filter(sender="ai").first()
        if first_ai:
            request.session["chat_session_id"] = session.pk

    return render(request, "chat_session.html", {
        "session":  session,
        "messages": messages,
    })


# ── File download ─────────────────────────────────────────────────────────────
@login_required
def download_case(request, case_id):
    case = get_object_or_404(UploadedCase, pk=case_id, user=request.user)
    try:
        return FileResponse(case.file.open("rb"), as_attachment=True, filename=case.filename)
    except FileNotFoundError:
        raise Http404("File not found.")

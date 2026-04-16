import logging
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, AISettings, ChatSession, ChatMessage, UploadedCase

logger = logging.getLogger(__name__)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display  = ("username", "email", "role", "is_approved", "is_active", "date_joined")
    list_filter   = ("role", "is_approved", "is_active")
    list_editable = ("is_approved", "is_active", "role")
    fieldsets     = BaseUserAdmin.fieldsets + (
        ("NUC Legal AI", {"fields": ("role", "is_approved")}),
    )
    actions = ["approve_users", "reject_users", "reset_system_data"]

    @admin.action(description="✅ Approve selected users")
    def approve_users(self, request, queryset):
        queryset.update(is_approved=True, is_active=True)

    @admin.action(description="❌ Reject / deactivate selected users")
    def reject_users(self, request, queryset):
        queryset.update(is_approved=False, is_active=False)

    @admin.action(description="🗑️ RESET SYSTEM — delete all non-superuser data")
    def reset_system_data(self, request, queryset):
        """
        Deletes all non-superuser users + all chat/file data.
        Superusers are always preserved.
        """
        deleted_users    = User.objects.filter(is_superuser=False).count()
        deleted_sessions = ChatSession.objects.count()
        deleted_messages = ChatMessage.objects.count()
        deleted_files    = UploadedCase.objects.count()

        ChatMessage.objects.all().delete()
        ChatSession.objects.all().delete()
        UploadedCase.objects.all().delete()
        User.objects.filter(is_superuser=False).delete()

        logger.warning(
            f"SYSTEM RESET by {request.user.username}: "
            f"users={deleted_users}, sessions={deleted_sessions}, "
            f"messages={deleted_messages}, files={deleted_files}"
        )
        self.message_user(
            request,
            f"✅ Reset complete — removed {deleted_users} users, "
            f"{deleted_sessions} chat sessions, {deleted_messages} messages, "
            f"{deleted_files} uploaded files. Superusers preserved.",
        )


@admin.register(AISettings)
class AISettingsAdmin(admin.ModelAdmin):
    list_display = ("cohere_enabled", "oci_enabled", "updated_at")


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display  = ("title", "user", "mode", "created_at", "updated_at")
    list_filter   = ("mode",)
    raw_id_fields = ("user",)


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ("session", "sender", "message", "created_at")
    list_filter  = ("sender",)


@admin.register(UploadedCase)
class UploadedCaseAdmin(admin.ModelAdmin):
    list_display = ("filename", "user", "uploaded_at")

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    ROLE_CHOICES = [
        ("case_analyzer", "Case Analyzer"),
        ("lincoln_lawyer", "Lincoln Lawyer"),
        ("both", "Both"),
    ]
    role        = models.CharField(max_length=20, choices=ROLE_CHOICES, default="case_analyzer")
    is_approved = models.BooleanField(default=False)

    def can_analyze(self):
        return self.is_approved and self.role in ("case_analyzer", "both")

    def can_chat(self):
        return self.is_approved and self.role in ("lincoln_lawyer", "both")

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"


class AISettings(models.Model):
    cohere_enabled = models.BooleanField(default=True)
    oci_enabled    = models.BooleanField(default=True)
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "AI Settings"

    def __str__(self):
        return f"AI Settings (Cohere={'ON' if self.cohere_enabled else 'OFF'}, OCI={'ON' if self.oci_enabled else 'OFF'})"

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class UploadedCase(models.Model):
    user        = models.ForeignKey(User, on_delete=models.CASCADE, related_name="uploaded_cases")
    file        = models.FileField(upload_to="cases/")
    filename    = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.filename} — {self.user.username}"

    def save(self, *args, **kwargs):
        if not self.filename and self.file:
            self.filename = self.file.name.split("/")[-1]
        super().save(*args, **kwargs)


class ChatSession(models.Model):
    MODE_CHOICES = [("case", "Case Analyzer"), ("lincoln", "Lincoln Lawyer")]
    user          = models.ForeignKey(User, on_delete=models.CASCADE, related_name="chat_sessions")
    title         = models.CharField(max_length=255, blank=True)
    mode          = models.CharField(max_length=10, choices=MODE_CHOICES, default="case")
    uploaded_case = models.ForeignKey(UploadedCase, null=True, blank=True, on_delete=models.SET_NULL)
    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.title or 'Untitled'} — {self.user.username}"


class ChatMessage(models.Model):
    SENDER_CHOICES = [("user", "User"), ("ai", "AI")]
    session    = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name="messages")
    sender     = models.CharField(max_length=5, choices=SENDER_CHOICES)
    message    = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"[{self.sender}] {self.message[:60]}"

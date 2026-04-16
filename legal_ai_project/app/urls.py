from django.urls import path
from . import views

urlpatterns = [
    # Landing
    path("",            views.landing,       name="landing"),

    # Core app
    path("upload/",     views.upload_case,   name="upload"),
    path("analyze/",    views.analyze_case,  name="analyze"),
    path("chatbot/",    views.chatbot_api,   name="chatbot"),
    path("chat/",       views.lincoln_lawyer, name="lincoln_lawyer"),

    # Auth
    path("auth/register/", views.register_view, name="register"),
    path("auth/login/",    views.login_view,    name="login"),
    path("auth/logout/",   views.logout_view,   name="logout"),
    path("auth/profile/",  views.profile_view,  name="profile"),

    # Dashboard
    path("dashboard/",  views.dashboard,     name="dashboard"),

    # Admin panel (custom, not Django admin)
    path("admin-panel/", views.admin_panel,  name="admin_panel"),
    path("ai-config/",   views.ai_config,    name="ai_config"),

    # Chat history & file download
    path("history/",                    views.chat_history,      name="chat_history"),
    path("history/<int:session_id>/",   views.chat_session_view, name="chat_session"),
    path("download/<int:case_id>/",     views.download_case,     name="download_case"),
]

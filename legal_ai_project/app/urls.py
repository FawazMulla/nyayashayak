from django.urls import path
from . import views

urlpatterns = [
    path("", views.upload_case, name="upload"),
    path("analyze/", views.analyze_case, name="analyze"),
    path("chatbot/", views.chatbot_api, name="chatbot"),
    path("chat/", views.lincoln_lawyer, name="lincoln_lawyer"),
]

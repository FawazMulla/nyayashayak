from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User


class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True)
    role  = forms.ChoiceField(choices=User.ROLE_CHOICES)

    class Meta:
        model  = User
        fields = ("username", "email", "role", "password1", "password2")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email      = self.cleaned_data["email"]
        user.role       = self.cleaned_data["role"]
        user.is_active  = False   # blocked until admin approves
        user.is_approved = False
        if commit:
            user.save()
        return user

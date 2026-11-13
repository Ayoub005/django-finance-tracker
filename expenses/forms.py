from django import forms
from .models import Expense
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm

class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = ['amount', 'currency', 'date', 'category', 'project', 'payment_method', 'notes', 'receipt']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'w-full p-2 border rounded'}),
            'amount': forms.NumberInput(attrs={'class': 'w-full p-2 border rounded', 'step': '0.01'}),
            'category': forms.Select(attrs={'class': 'w-full p-2 border rounded'}),
            'payment_method': forms.Select(attrs={'class': 'w-full p-2 border rounded'}),
            'notes': forms.TextInput(attrs={'class': 'w-full p-2 border rounded', 'placeholder': 'Optional details'}),
        }

class CustomRegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True, help_text="We will send a verification code to this address.")

    class Meta:
        model = User
        fields = ('username', 'email')
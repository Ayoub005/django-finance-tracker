import requests
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import random
from django.db.models.signals import post_save
from django.dispatch import receiver

class EmailVerificationOTP(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)

    def generate_otp(self):
        self.otp = str(random.randint(100000, 999999))
        self.save()

class Expense(models.Model):
    CATEGORY_CHOICES = [
        ('Food & Dining', 'Food & Dining'),
        ('Housing & Utilities', 'Housing & Utilities'),
        ('Academics', 'Academics'),
        ('Transportation', 'Transportation'),
        ('Lifestyle & Entertainment', 'Lifestyle & Entertainment'),
    ]

    PAYMENT_CHOICES = [
        ('WeChat Pay', 'WeChat Pay'),
        ('Alipay', 'Alipay'),
        ('Bank Card', 'Bank Card'),
        ('Cash', 'Cash'),
    ]

    CURRENCY_CHOICES = [
        ('CNY', 'Chinese Yuan (Base)'),
        ('SGD', 'Singapore Dollar'),
        ('MAD', 'Moroccan Dirham'),
        ('EUR', 'Euro'),
        ('USD', 'US Dollar'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default='CNY')
    amount_in_cny = models.DecimalField(max_digits=10, decimal_places=2, default=0, editable=False)

    date = models.DateField(default=timezone.now)
    category = models.CharField(max_length=100)
    project = models.CharField(max_length=100, blank=True, null=True)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_CHOICES, blank=True, null=True)
    notes = models.CharField(max_length=255, blank=True, null=True)
    receipt = models.FileField(upload_to='receipts/', blank=True, null=True) # <--- MAKE SURE THIS IS HERE
    is_deleted = models.BooleanField(default=False)

    is_deleted = models.BooleanField(default=False)

    class Meta:
        ordering = ['-date']

    def save(self, *args, **kwargs):
        if self.currency == 'CNY':
            self.amount_in_cny = self.amount
        else:
            try:
                response = requests.get('https://api.exchangerate-api.com/v4/latest/CNY')
                response.raise_for_status()
                data = response.json()
                foreign_rate = data['rates'].get(self.currency)
                if foreign_rate:
                    self.amount_in_cny = float(self.amount) / float(foreign_rate)
                else:
                    self.amount_in_cny = self.amount
            except requests.RequestException:
                fallback_rates = {'SGD': 5.45, 'MAD': 0.72, 'EUR': 7.85, 'USD': 7.15}
                conversion_rate = fallback_rates.get(self.currency, 1.0)
                self.amount_in_cny = float(self.amount) * conversion_rate
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.date} - {self.category} - {self.amount} {self.currency}"


class Contact(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class SocialLedger(models.Model):
    TYPE_CHOICES = (
        ('LENT', 'I lent them money (They owe me)'),
        ('BORROWED', 'I borrowed money (I owe them)'),
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name='ledgers')
    transaction_type = models.CharField(max_length=10, choices=TYPE_CHOICES)

    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.CharField(max_length=255)
    date = models.DateField(default=timezone.now)
    is_settled = models.BooleanField(default=False)
    receipt = models.FileField(upload_to='receipts/', blank=True, null=True)
    is_deleted = models.BooleanField(default=False)

    due_date = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"{self.contact.name} - {self.get_transaction_type_display()} : {self.amount}"

class LedgerRepayment(models.Model):
    ledger = models.ForeignKey(SocialLedger, on_delete=models.CASCADE, related_name='repayments')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField(default=timezone.now)
    notes = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"Repayment of {self.amount} for {self.ledger.description}"


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    image = models.ImageField(upload_to='avatars/', blank=True, null=True)
    
    # New System Preferences
    default_currency = models.CharField(max_length=3, default='CNY')
    timezone = models.CharField(max_length=50, default='Asia/Shanghai')
    monthly_reports = models.BooleanField(default=True)
    trust_vault_reminders = models.BooleanField(default=False)
    
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    occupation = models.CharField(max_length=100, blank=True, null=True)
    website = models.URLField(max_length=200, blank=True, null=True)
    bio = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.user.username

# Automatically create a profile when a new user is created
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    instance.profile.save()
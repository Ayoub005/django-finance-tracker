from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from expenses.models import SocialLedger
from django.core.mail import send_mail

class Command(BaseCommand):
    help = 'Sends automated email alerts for Trust Vault ledgers due in 48 hours.'

    def handle(self, *args, **kwargs):
        # Calculate exactly 48 hours from today
        target_date = timezone.now().date() + timedelta(days=2)

        # Query the database for ledgers matching our exact conditions
        ledgers = SocialLedger.objects.filter(
            due_date=target_date,
            is_deleted=False,
            user__profile__trust_vault_reminders=True # Only send if they enabled the toggle
        )

        sent_count = 0

        for ledger in ledgers:
            # We skip this if you already added an "is_settled" field and it's True
            if hasattr(ledger, 'is_settled') and ledger.is_settled:
                continue

            user = ledger.user
            action = "repay" if ledger.transaction_type == "BORROWED" else "collect"

            subject = "Finance Tracker Alert: Trust Vault Deadline Approaching"

            # Premium HTML Email formatting
            html_message = f"""
            <div style="font-family: Arial, sans-serif; padding: 20px; color: #333;">
                <h2 style="color: #0f172a;">Trust Vault Reminder</h2>
                <p>Hello <strong>{user.username}</strong>,</p>
                <p>This is an automated alert. You have a Trust Vault agreement due in exactly 48 hours.</p>
                <div style="background-color: #f8fafc; border-left: 4px solid #06b6d4; padding: 15px; margin: 20px 0;">
                    <p style="margin: 0 0 10px 0;"><strong>Contact:</strong> {ledger.contact.name}</p>
                    <p style="margin: 0 0 10px 0;"><strong>Type:</strong> You {ledger.transaction_type}</p>
                    <p style="margin: 0 0 10px 0;"><strong>Amount:</strong> {ledger.amount}</p>
                    <p style="margin: 0;"><strong>Due Date:</strong> {ledger.due_date}</p>
                </div>
                <p>Please log in to your dashboard to settle this ledger.</p>
            </div>
            """

            try:
                send_mail(
                    subject,
                    "Trust Vault deadline approaching. Please check your dashboard.",
                    'Finance Tracker <hmdelmokhtar05@gmail.com>',
                    [user.email],
                    fail_silently=False,
                    html_message=html_message
                )
                sent_count += 1
            except Exception as e:
                self.stderr.write(f"Failed to send to {user.email}: {e}")

        self.stdout.write(self.style.SUCCESS(f'Successfully sent {sent_count} reminders.'))
from rest_framework import serializers
from .models import Expense, Contact, SocialLedger, LedgerRepayment, UserProfile


class ExpenseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Expense
        fields = [
            'id', 'amount', 'currency', 'amount_in_cny', 'date',
            'category', 'project', 'payment_method', 'notes',
            'receipt', 'is_deleted'
        ]
        read_only_fields = ['id', 'amount_in_cny']


class ContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contact
        fields = ['id', 'name', 'created_at']
        read_only_fields = ['id', 'created_at']


class LedgerRepaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = LedgerRepayment
        fields = ['id', 'ledger', 'amount', 'date', 'notes']
        read_only_fields = ['id']


class SocialLedgerSerializer(serializers.ModelSerializer):
    contact_name = serializers.CharField(source='contact.name', read_only=True)
    repayments = LedgerRepaymentSerializer(many=True, read_only=True)

    class Meta:
        model = SocialLedger
        fields = [
            'id', 'contact', 'contact_name', 'transaction_type',
            'amount', 'description', 'date', 'is_settled',
            'receipt', 'is_deleted', 'due_date', 'repayments'
        ]
        read_only_fields = ['id']


class UserProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)

    class Meta:
        model = UserProfile
        fields = [
            'username', 'email', 'image', 'default_currency',
            'timezone', 'monthly_reports', 'trust_vault_reminders',
            'phone_number', 'occupation', 'website', 'bio'
        ]
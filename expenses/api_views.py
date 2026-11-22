from rest_framework import viewsets, generics
from rest_framework.permissions import IsAuthenticated
from .models import Expense, Contact, SocialLedger, LedgerRepayment
from .serializers import (
    ExpenseSerializer,
    ContactSerializer,
    SocialLedgerSerializer,
    LedgerRepaymentSerializer,
    UserProfileSerializer,
)


class ExpenseViewSet(viewsets.ModelViewSet):
    serializer_class = ExpenseSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Expense.objects.filter(user=self.request.user, is_deleted=False)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class ContactViewSet(viewsets.ModelViewSet):
    serializer_class = ContactSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Contact.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class SocialLedgerViewSet(viewsets.ModelViewSet):
    serializer_class = SocialLedgerSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return SocialLedger.objects.filter(user=self.request.user, is_deleted=False)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class LedgerRepaymentViewSet(viewsets.ModelViewSet):
    serializer_class = LedgerRepaymentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return LedgerRepayment.objects.filter(ledger__user=self.request.user)


class UserProfileAPIView(generics.RetrieveUpdateAPIView):
    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user.profile
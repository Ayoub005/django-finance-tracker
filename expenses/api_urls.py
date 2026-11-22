from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api_views import (
    ExpenseViewSet,
    ContactViewSet,
    SocialLedgerViewSet,
    LedgerRepaymentViewSet,
    UserProfileAPIView,
)

router = DefaultRouter()
router.register(r'expenses', ExpenseViewSet, basename='api-expenses')
router.register(r'contacts', ContactViewSet, basename='api-contacts')
router.register(r'ledgers', SocialLedgerViewSet, basename='api-ledgers')
router.register(r'repayments', LedgerRepaymentViewSet, basename='api-repayments')

urlpatterns = [
    path('', include(router.urls)),
    path('profile/', UserProfileAPIView.as_view(), name='api-profile'),
]
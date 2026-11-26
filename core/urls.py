from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from expenses import views
from django.conf import settings
from django.conf.urls.static import static
from rest_framework.authtoken.views import obtain_auth_token
from .views import health_check


urlpatterns = [
    
    path("api/health/", health_check, name="health_check"),
    
    path('api/login/', obtain_auth_token, name='api_login'),
    path('api/', include('expenses.api_urls')),

    path('', views.home, name='home'),

    path('quick-entry/', views.quick_entry, name='quick_entry'),

    path('dashboard/', views.dashboard, name='dashboard'),
    path('export/', views.export_monthly_report, name='export_report'),
    path('delete/<int:expense_id>/', views.delete_expense, name='delete_expense'),
    path('recycle-bin/', views.recycle_bin, name='recycle_bin'),
    path('restore/<int:expense_id>/', views.restore_expense, name='restore_expense'),
    path('permanent-delete/<int:expense_id>/', views.permanent_delete, name='permanent_delete'),

    # Auth paths
    path('login/', auth_views.LoginView.as_view(template_name='expenses/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),

    path('register/', views.register, name='register'),

    path('export-pdf/', views.export_pdf_report, name='export_pdf_report'),

    path('verify-otp/', views.verify_otp_view, name='verify_otp'),

    # --- UPGRADED PASSWORD RESET ROUTING ---
    path('reset_password/', auth_views.PasswordResetView.as_view(
        template_name="expenses/password_reset.html",
        html_email_template_name="expenses/password_reset_email.html",  # Triggers the premium HTML email
        subject_template_name="expenses/password_reset_subject.txt"     # Triggers the professional subject line
    ), name="reset_password"),

    path('reset_password_sent/', auth_views.PasswordResetDoneView.as_view(
        template_name="expenses/password_reset_sent.html"
    ), name="password_reset_done"),

    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name="expenses/password_reset_form.html"
    ), name="password_reset_confirm"),

    path('reset_password_complete/', auth_views.PasswordResetCompleteView.as_view(
        template_name="expenses/password_reset_done.html"
    ), name="password_reset_complete"),

    path('admin-control/', admin.site.urls),
    path('', include('expenses.urls')),

    path('vault/', views.trust_vault, name='trust_vault'),

    path('vault/save/', views.save_ledger, name='save_ledger'),
    path('vault/delete/<int:ledger_id>/', views.delete_ledger, name='delete_ledger'),

    path('vault/restore/<int:ledger_id>/', views.restore_ledger, name='restore_ledger'),
    path('vault/permanent-delete/<int:ledger_id>/', views.permanent_delete_ledger, name='permanent_delete_ledger'),

    path('settings/', views.account_settings, name='settings'),

    path('upload-avatar/', views.upload_avatar, name='upload_avatar'),

    path('api/request-otp/', views.request_otp, name='request_otp'),
    path('api/verify-update/', views.verify_and_update, name='verify_and_update'),

    path('api/verify-otp-only/', views.verify_otp_only, name='verify_otp_only'),

    path('api/update-preferences/', views.update_preferences, name='update_preferences'),

    path('api/trigger-reminders/', views.trigger_reminders, name='trigger_reminders'),

    path('update-profile/', views.update_profile, name='update_profile'),


]+ static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

from django.urls import path
from . import views

urlpatterns = [
    path('', views.quick_entry, name='quick_entry'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('export/', views.export_monthly_report, name='export_report'),
    path('delete/<int:expense_id>/', views.delete_expense, name='delete_expense'),
    path('recycle-bin/', views.recycle_bin, name='recycle_bin'),
    path('restore/<int:expense_id>/', views.restore_expense, name='restore_expense'),
    path('permanent-delete/<int:expense_id>/', views.permanent_delete, name='permanent_delete'),
]
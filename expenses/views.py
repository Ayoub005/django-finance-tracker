from django.shortcuts import render, redirect, get_object_or_404
from .models import Expense, Contact, SocialLedger, LedgerRepayment, EmailVerificationOTP
from .forms import ExpenseForm, CustomRegistrationForm
from django.http import HttpResponse, FileResponse
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, F, Case, When, Value, FloatField, Q
from django.utils import timezone
from django.contrib.auth import login
from django.core.cache import cache
import urllib.request
import json
import io
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
import random
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _
from django.contrib.auth.hashers import check_password
from django.http import JsonResponse
from .models import UserProfile
from django.core.management import call_command
from django.http import HttpResponse
import datetime
import zoneinfo
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required


class PreventPasswordReuseValidator:
    def validate(self, password, user=None):
        if user and check_password(password, user.password):
            raise ValidationError(
                _("For your security, you cannot use your current password. Please choose a new one."),
                code='password_reused',
            )
    def get_help_text(self):
        return _("Your new password cannot be the same as your current password.")

def get_live_exchange_rates():
    rates = cache.get('live_currency_rates')
    if not rates:
        try:
            url = 'https://open.er-api.com/v6/latest/CNY'
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode())
                api_rates = data.get('rates', {})
                rates = {
                    'MAD': 1 / api_rates.get('MAD', 1.40),
                    'EUR': 1 / api_rates.get('EUR', 0.12),
                    'USD': 1 / api_rates.get('USD', 0.13),
                    'SGD': 1 / api_rates.get('SGD', 0.18),
                }
                cache.set('live_currency_rates', rates, 43200)
        except Exception:
            rates = {'MAD': 0.72, 'EUR': 7.85, 'USD': 7.20, 'SGD': 5.35}
    return rates

@login_required
def settings_view(request):
    # Ensure profile always exists for the current user
    profile, created = UserProfile.objects.get_or_create(user=request.user)
    return render(request, 'expenses/settings.html', {'profile': profile})

@login_required
def quick_entry(request):
    if request.method == 'POST':
        form = ExpenseForm(request.POST, request.FILES)
        if form.is_valid():
            expense = form.save(commit=False)
            expense.user = request.user
            expense.save()

            exp_month = str(expense.date)[:7]
            display_currency = request.POST.get('currency', 'CNY')
            return redirect(f'/dashboard/?display_currency={display_currency}&month={exp_month}')
        else:
            # FORCE Django to tell us exactly what is wrong
            return JsonResponse({"error": True, "messages": form.errors}, status=400)

    else:
        form = ExpenseForm()
    return render(request, 'expenses/entry_form.html', {'form': form})


@login_required
def dashboard(request):
    import datetime
    live_rates = get_live_exchange_rates()
    
    display_currency = request.GET.get('display_currency')

    if not display_currency or display_currency == 'null':
        try:
            profile = UserProfile.objects.get(user=request.user)
            display_currency = profile.default_currency if profile.default_currency else 'CNY'
        except UserProfile.DoesNotExist:
            display_currency = 'CNY'

    symbols = {'CNY': '¥', 'USD': '$', 'EUR': '€', 'MAD': 'د.م.', 'SGD': '$'}
    currency_symbol = symbols.get(display_currency, '¥')

    if display_currency == 'CNY':
        display_multiplier = 1.0
    else:
        display_multiplier = 1.0 / live_rates.get(display_currency, 1.0)

    expenses_qs = Expense.objects.filter(user=request.user, is_deleted=False).annotate(
        live_cny_amount=Case(
            When(currency='CNY', then=F('amount')),
            When(currency='MAD', then=F('amount') * Value(live_rates['MAD'])),
            When(currency='EUR', then=F('amount') * Value(live_rates['EUR'])),
            When(currency='USD', then=F('amount') * Value(live_rates['USD'])),
            When(currency='SGD', then=F('amount') * Value(live_rates['SGD'])),
            default=F('amount'),
            output_field=FloatField()
        )
    ).annotate(
        display_amount=F('live_cny_amount') * Value(display_multiplier)
    ).order_by('-date', '-id')

    search_query = request.GET.get('search', '').strip()
    if search_query:
        expenses_qs = expenses_qs.filter(
            Q(category__icontains=search_query) |
            Q(project__icontains=search_query) |
            Q(notes__icontains=search_query) |
            Q(payment_method__icontains=search_query)
        )

    selected_month = request.GET.get('month')

    if selected_month == 'all':
        filtered_expenses = expenses_qs
    elif selected_month:
        try:
            year, month = map(int, selected_month.split('-'))
            filtered_expenses = expenses_qs.filter(date__year=year, date__month=month)
        except ValueError:
            filtered_expenses = expenses_qs
    else:
        current_year = timezone.now().year
        current_month = timezone.now().month
        filtered_expenses = expenses_qs.filter(date__year=current_year, date__month=current_month)
        selected_month = f"{current_year}-{current_month:02d}"

    total_spent = filtered_expenses.aggregate(total=Sum('display_amount'))['total'] or 0

    top_category_data = (
        filtered_expenses.values('category')
        .annotate(cat_total=Sum('display_amount'))
        .order_by('-cat_total')
        .first()
    )
    highest_category = top_category_data['category'] if top_category_data else "None"

    distinct_dates = filtered_expenses.values('date').distinct().count()
    daily_average = (total_spent / distinct_dates) if distinct_dates > 0 else 0

    category_breakdown = (
        filtered_expenses.values('category')
        .annotate(total=Sum('display_amount'))
        .order_by('-total')
    )
    chart_labels = [item['category'] for item in category_breakdown]
    chart_data = [float(item['total']) for item in category_breakdown]

    # Bypasses SQLite completely to guarantee new months always appear in the dropdown
    raw_dates = Expense.objects.filter(user=request.user, is_deleted=False).values_list('date', flat=True)
    available_months = sorted(list(set(datetime.date(d.year, d.month, 1) for d in raw_dates if d)), reverse=True)

    context = {
        'expenses': filtered_expenses[:50],
        'total_spent': total_spent,
        'highest_category': highest_category,
        'daily_average': daily_average,
        'selected_month': selected_month,
        'available_months': available_months,
        'chart_labels': chart_labels,
        'chart_data': chart_data,
        'search_query': search_query,
        'display_currency': display_currency,
        'currency_symbol': currency_symbol,
    }
    return render(request, 'expenses/dashboard.html', context)

@login_required
def trust_vault(request):
    live_rates = get_live_exchange_rates()
    
    display_currency = request.GET.get('display_currency')
    if not display_currency or display_currency == 'null':
        try:
            profile = UserProfile.objects.get(user=request.user)
            display_currency = profile.default_currency if profile.default_currency else 'CNY'
        except UserProfile.DoesNotExist:
            display_currency = 'CNY'

    symbols = {'CNY': '¥', 'USD': '$', 'EUR': '€', 'MAD': 'د.م.', 'SGD': '$'}
    currency_symbol = symbols.get(display_currency, '¥')

    if display_currency == 'CNY':
        display_multiplier = 1.0
    else:
        display_multiplier = 1.0 / live_rates.get(display_currency, 1.0)

    ledgers = SocialLedger.objects.filter(user=request.user, is_deleted=False).order_by('-date', '-id')

    # Convert individual ledger amounts for display
    for ledger in ledgers:
        ledger.display_amount = float(ledger.amount) * display_multiplier

    # Calculate base totals and convert them
    base_total_lent = sum(l.amount for l in ledgers if l.transaction_type == 'LENT' and not l.is_settled)
    base_total_borrowed = sum(l.amount for l in ledgers if l.transaction_type == 'BORROWED' and not l.is_settled)

    total_lent = float(base_total_lent) * display_multiplier
    total_borrowed = float(base_total_borrowed) * display_multiplier
    net_balance = total_lent - total_borrowed

    context = {
        'ledgers': ledgers,
        'total_lent': total_lent,
        'total_borrowed': total_borrowed,
        'net_balance': net_balance,
        'display_currency': display_currency,
        'currency_symbol': currency_symbol,
    }
    return render(request, 'expenses/trust_vault.html', context)

@login_required
def save_ledger(request):
    if request.method == 'POST':
        ledger_id = request.POST.get('ledger_id')
        contact_name = request.POST.get('contact_name')

        amount_str = request.POST.get('amount', '0').replace(',', '')
        try:
            amount = float(amount_str)
        except ValueError:
            amount = 0.00

        contact = Contact.objects.filter(user=request.user, name=contact_name).first()
        if not contact:
            contact = Contact.objects.create(user=request.user, name=contact_name)

        # Handle the new due_date field (convert empty string to None)
        due_date_input = request.POST.get('due_date')
        due_date = due_date_input if due_date_input else None

        if ledger_id:
            ledger = SocialLedger.objects.get(id=ledger_id, user=request.user)
            ledger.contact = contact
            ledger.transaction_type = request.POST.get('transaction_type')
            ledger.amount = amount
            ledger.date = request.POST.get('date')
            ledger.due_date = due_date
            ledger.description = request.POST.get('description')
            if request.FILES.get('receipt'):
                ledger.receipt = request.FILES.get('receipt')
            ledger.save()
        else:
            SocialLedger.objects.create(
                user=request.user, contact=contact,
                transaction_type=request.POST.get('transaction_type'),
                amount=amount,
                date=request.POST.get('date'),
                due_date=due_date,
                description=request.POST.get('description'),
                receipt=request.FILES.get('receipt')
            )
    return redirect('trust_vault')

@login_required
def export_monthly_report(request):
    display_currency = request.GET.get('display_currency', 'CNY')
    live_rates = get_live_exchange_rates()
    symbols = {'CNY': '¥', 'USD': '$', 'EUR': '€', 'MAD': 'MAD', 'SGD': '$'}
    currency_symbol = symbols.get(display_currency, '¥')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    queryset = Expense.objects.filter(user=request.user, is_deleted=False)

    if start_date:
        queryset = queryset.filter(date__gte=start_date)
    if end_date:
        queryset = queryset.filter(date__lte=end_date)

    queryset = queryset.order_by('-date', '-id')

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Financial Statement"
    ws.views.sheetView[0].showGridLines = True

    font_title = Font(name="Segoe UI", size=15, bold=True, color="0F172A")
    font_meta = Font(name="Segoe UI", size=9, italic=True, color="64748B")
    font_header = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
    font_data = Font(name="Segoe UI", size=10, color="334155")
    font_amount = Font(name="Segoe UI", size=10, bold=True, color="047857")
    font_total = Font(name="Segoe UI", size=11, bold=True, color="0F172A")

    fill_header = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
    fill_date = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    fill_category = PatternFill(start_color="EFF6FF", end_color="EFF6FF", fill_type="solid")
    fill_project = PatternFill(start_color="F5F3FF", end_color="F5F3FF", fill_type="solid")
    fill_amount = PatternFill(start_color="ECFDF5", end_color="ECFDF5", fill_type="solid")
    fill_method = PatternFill(start_color="F0FDFA", end_color="F0FDFA", fill_type="solid")
    fill_total = PatternFill(start_color="E2E8F0", end_color="E2E8F0", fill_type="solid")

    align_center = Alignment(horizontal="center", vertical="center")

    border_thin = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )
    border_total = Border(
        top=Side(style='thin', color='0F172A'),
        bottom=Side(style='double', color='0F172A'),
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1')
    )

    ws['A1'] = "PREMIUM FINANCIAL STATEMENT"
    ws['A1'].font = font_title
    ws.row_dimensions[1].height = 28
    ws['A2'] = f"Currency: {display_currency} | Generated For: {request.user.username} | Date: {timezone.now().strftime('%B %d, %Y')}"
    ws['A2'].font = font_meta
    ws.row_dimensions[2].height = 18
    ws.row_dimensions[3].height = 12

    has_projects = any(exp.project and exp.project != 'None' and exp.project.strip() != '' for exp in queryset)
    if has_projects:
        headers = ['Date', 'Category', 'Project', f'Amount ({display_currency})', 'Method']
        amount_col_idx = 4
    else:
        headers = ['Date', 'Category', f'Amount ({display_currency})', 'Method']
        amount_col_idx = 3

    for col_idx, header in enumerate(headers, 1):
        cell = ws.cell(row=4, column=col_idx, value=header)
        cell.font = font_header
        cell.fill = fill_header
        cell.border = border_thin
        cell.alignment = align_center
    ws.row_dimensions[4].height = 26

    start_row = 5
    for idx, exp in enumerate(queryset):
        amount_float = float(exp.amount)
        if exp.currency == 'CNY':
            cny_val = amount_float
        elif exp.currency in live_rates:
            cny_val = amount_float * float(live_rates[exp.currency])
        else:
            cny_val = amount_float

        if display_currency == 'CNY':
            final_amount = cny_val
        else:
            final_amount = cny_val / float(live_rates.get(display_currency, 1.0))

        date_str = str(exp.date)
        category = exp.category
        method = exp.payment_method

        if has_projects:
            project_text = exp.project if exp.project and exp.project != 'None' and exp.project.strip() != '' else '-'
            row_data = [date_str, category, project_text, round(final_amount, 2), method]
        else:
            row_data = [date_str, category, round(final_amount, 2), method]

        current_row = start_row + idx
        ws.append(row_data)
        ws.row_dimensions[current_row].height = 22

        for col_idx in range(1, len(row_data) + 1):
            cell = ws.cell(row=current_row, column=col_idx)
            cell.border = border_thin
            cell.alignment = align_center

            if col_idx == 1:
                cell.fill = fill_date
                cell.font = font_data
            elif col_idx == 2:
                cell.fill = fill_category
                cell.font = font_data
            elif has_projects and col_idx == 3:
                cell.fill = fill_project
                cell.font = font_data
            elif col_idx == amount_col_idx:
                cell.fill = fill_amount
                cell.font = font_amount
                cell.number_format = f'"{currency_symbol} "#,##0.00'
            else:
                cell.fill = fill_method
                cell.font = font_data

    last_data_row = start_row + len(queryset) - 1
    total_row = last_data_row + 1
    ws.row_dimensions[total_row].height = 25

    amount_col_letter = openpyxl.utils.get_column_letter(amount_col_idx)
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=total_row, column=col_idx)
        cell.font = font_total
        cell.fill = fill_total
        cell.border = border_total
        cell.alignment = align_center

        if col_idx == 1:
            cell.value = "TOTAL"
        elif col_idx == amount_col_idx:
            cell.value = f"=SUM({amount_col_letter}{start_row}:{amount_col_letter}{last_data_row})"
            cell.number_format = f'"{currency_symbol} "#,##0.00'
        else:
            cell.value = ""

    for col in ws.columns:
        max_len = 0
        col_letter = openpyxl.utils.get_column_letter(col[0].column)
        for cell in col:
            if cell.row < 4:
                continue
            try:
                if cell.value:
                    max_len = max(max_len, len(str(cell.value)))
            except:
                pass
        ws.column_dimensions[col_letter].width = max(max_len + 12, 20)

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    response = HttpResponse(buffer.getvalue(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="Expense_Statement_{display_currency}.xlsx"'
    return response

@login_required
def export_pdf_report(request):
    display_currency = request.GET.get('display_currency', 'CNY')
    live_rates = get_live_exchange_rates()
    symbols = {'CNY': '¥', 'USD': '$', 'EUR': '€', 'MAD': 'DH', 'SGD': '$'}
    currency_symbol = symbols.get(display_currency, '¥')

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    elements = []
    styles = getSampleStyleSheet()

    title_style = styles['Heading1']
    title_style.textColor = colors.HexColor("#0F172A")
    title_style.alignment = 1

    meta_style = styles['Normal']
    meta_style.textColor = colors.HexColor("#64748B")

    elements.append(Paragraph("PREMIUM FINANCIAL STATEMENT", title_style))
    elements.append(Spacer(1, 8))
    elements.append(Paragraph(f"<b>Generated For:</b> {request.user.username} &nbsp;|&nbsp; <b>Currency:</b> {display_currency} ({currency_symbol}) &nbsp;|&nbsp; <b>Date:</b> {timezone.now().strftime('%B %d, %Y')}", meta_style))
    elements.append(Spacer(1, 15))

    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    queryset = Expense.objects.filter(user=request.user, is_deleted=False)

    if start_date:
        queryset = queryset.filter(date__gte=start_date)
    if end_date:
        queryset = queryset.filter(date__lte=end_date)

    queryset = queryset.order_by('-date', '-id')

    has_projects = any(exp.project and exp.project != 'None' and exp.project.strip() != '' for exp in queryset)

    if has_projects:
        headers = ['Date', 'Category', 'Project', f'Amount ({display_currency})', 'Method']
        col_widths = [80, 140, 100, 100, 90]
        amount_col_idx = 3
    else:
        headers = ['Date', 'Category', f'Amount ({display_currency})', 'Method']
        col_widths = [100, 180, 130, 120]
        amount_col_idx = 2

    data = [headers]
    total_sum = 0

    for exp in queryset:
        amount_float = float(exp.amount)
        if exp.currency == 'CNY':
            cny_val = amount_float
        elif exp.currency in live_rates:
            cny_val = amount_float * float(live_rates[exp.currency])
        else:
            cny_val = amount_float

        if display_currency == 'CNY':
            final_amount = cny_val
        else:
            final_amount = cny_val / float(live_rates.get(display_currency, 1.0))

        total_sum += final_amount
        amount_text = f"{currency_symbol} {final_amount:,.2f}"

        if has_projects:
            project_text = exp.project if exp.project and exp.project != 'None' and exp.project.strip() != '' else '-'
            data.append([str(exp.date), exp.category, project_text, amount_text, exp.payment_method])
        else:
            data.append([str(exp.date), exp.category, amount_text, exp.payment_method])

    if has_projects:
        data.append(['TOTAL', '', '', f"{currency_symbol} {total_sum:,.2f}", ''])
    else:
        data.append(['TOTAL', '', f"{currency_symbol} {total_sum:,.2f}", ''])

    table = Table(data, colWidths=col_widths, repeatRows=1)
    table_styles = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#0F172A")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('TOPPADDING', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TEXTCOLOR', (0, 1), (-1, -2), colors.HexColor("#334155")),
        ('FONTNAME', (0, 1), (-1, -2), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -2), 9),
        ('TOPPADDING', (0, 1), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 7),
        ('BACKGROUND', (0, 1), (0, -2), colors.HexColor("#F8FAFC")),
        ('BACKGROUND', (1, 1), (1, -2), colors.HexColor("#EFF6FF")),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ('BACKGROUND', (amount_col_idx, 1), (amount_col_idx, -2), colors.HexColor("#ECFDF5")),
        ('TEXTCOLOR', (amount_col_idx, 1), (amount_col_idx, -2), colors.HexColor("#047857")),
        ('FONTNAME', (amount_col_idx, 1), (amount_col_idx, -2), 'Helvetica-Bold'),
        ('BACKGROUND', (0, len(data)-1), (-1, len(data)-1), colors.HexColor("#E2E8F0")),
        ('FONTNAME', (0, len(data)-1), (-1, len(data)-1), 'Helvetica-Bold'),
        ('TEXTCOLOR', (0, len(data)-1), (-1, len(data)-1), colors.HexColor("#0F172A")),
        ('TEXTCOLOR', (amount_col_idx, len(data)-1), (amount_col_idx, len(data)-1), colors.HexColor("#047857")),
        ('LINEABOVE', (0, len(data)-1), (-1, len(data)-1), 1, colors.HexColor("#0F172A")),
        ('LINEBELOW', (0, len(data)-1), (-1, len(data)-1), 2, colors.HexColor("#0F172A")),
    ]

    if has_projects:
        table_styles.append(('BACKGROUND', (2, 1), (2, -2), colors.HexColor("#F5F3FF")))

    table.setStyle(TableStyle(table_styles))
    elements.append(table)

    def add_footer(canvas_obj, doc_obj):
        canvas_obj.saveState()
        canvas_obj.setFont('Helvetica', 8)
        canvas_obj.setFillColor(colors.HexColor("#64748B"))
        canvas_obj.drawRightString(572, 25, f"Page {doc_obj.page} | Confidential Financial Report")
        canvas_obj.restoreState()

    doc.build(elements, onFirstPage=add_footer, onLaterPages=add_footer)
    buffer.seek(0)
    return FileResponse(buffer, as_attachment=True, filename=f'Financial_Statement_{display_currency}.pdf')

@login_required
def delete_expense(request, expense_id):
    expense = get_object_or_404(Expense, id=expense_id, user=request.user)
    expense.is_deleted = True
    expense.save()
    return redirect('dashboard')

@login_required
def recycle_bin(request):
    deleted_expenses = Expense.objects.filter(user=request.user, is_deleted=True).order_by('-date', '-id')
    deleted_ledgers = SocialLedger.objects.filter(user=request.user, is_deleted=True).order_by('-date', '-id')
    return render(request, 'expenses/recycle_bin.html', {
        'expenses': deleted_expenses,
        'ledgers': deleted_ledgers
    })

@login_required(login_url='/accounts/login/')
def restore_expense(request, expense_id):
    expense = get_object_or_404(Expense, id=expense_id, user=request.user)
    expense.is_deleted = False
    expense.save()
    return redirect('recycle_bin')

@login_required(login_url='/accounts/login/')
def permanent_delete(request, expense_id):
    expense = get_object_or_404(Expense, id=expense_id, user=request.user)
    expense.delete()
    return redirect('recycle_bin')

def register(request):
    if request.method == 'POST':
        form = CustomRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = False
            user.save()
            otp_obj, created = EmailVerificationOTP.objects.get_or_create(user=user)
            otp_obj.generate_otp()
            send_mail(
                'Your Finance Tracker Verification Code',
                f'Hello {user.username},\n\nYour 6-digit code is: {otp_obj.otp}',
                None,
                [user.email],
                fail_silently=False,
            )
            request.session['verifying_user_id'] = user.id
            return redirect('verify_otp')
    else:
        form = CustomRegistrationForm()
    return render(request, 'expenses/register.html', {'form': form})

def verify_otp_view(request):
    if request.method == 'POST':
        entered_otp = request.POST.get('otp')
        user_id = request.session.get('verifying_user_id')
        if user_id:
            try:
                user = User.objects.get(id=user_id)
                otp_obj = EmailVerificationOTP.objects.get(user=user)
                if otp_obj.otp == entered_otp:
                    user.is_active = True
                    user.save()
                    otp_obj.delete()
                    request.session.pop('verifying_user_id', None)
                    login(request, user)
                    return redirect('dashboard')
                else:
                    return render(request, 'expenses/verify_otp.html', {'error': 'Invalid code. Try again.'})
            except (User.DoesNotExist, EmailVerificationOTP.DoesNotExist):
                pass
        return redirect('register')
    return render(request, 'expenses/verify_otp.html')

@login_required
def restore_ledger(request, ledger_id):
    ledger = get_object_or_404(SocialLedger, id=ledger_id, user=request.user)
    ledger.is_deleted = False
    ledger.save()
    return redirect('recycle_bin')

@login_required
def permanent_delete_ledger(request, ledger_id):
    ledger = get_object_or_404(SocialLedger, id=ledger_id, user=request.user)
    ledger.delete()
    return redirect('recycle_bin')

@login_required
def delete_ledger(request, ledger_id):
    ledger = get_object_or_404(SocialLedger, id=ledger_id, user=request.user)
    ledger.is_deleted = True
    ledger.save()
    return redirect('trust_vault')

def home(request):
    return render(request, 'expenses/home.html')

@login_required
def account_settings(request):
    profile = None
    if hasattr(request.user, 'userprofile'):
        profile = request.user.userprofile

    # Generate a sorted list of all standard global timezones (e.g., 'Asia/Shanghai')
    # We filter for '/' to exclude obscure system timezones like 'Zulu' or 'Factory'
    all_tzs = sorted([tz for tz in zoneinfo.available_timezones() if '/' in tz])

    context = {
        'all_timezones': all_tzs,
        'current_tz': profile.timezone if profile else None,
    }
    return render(request, 'expenses/settings.html', context)

@login_required
def upload_avatar(request):
    if request.method == 'POST' and request.FILES.get('avatar'):
        # Get or create the profile
        profile, created = UserProfile.objects.get_or_create(user=request.user)

        # Save the new image
        profile.image = request.FILES['avatar']
        profile.save()

        return JsonResponse({'success': True, 'image_url': profile.image.url})

    return JsonResponse({'success': False, 'error': 'No file uploaded'})

@login_required
def request_otp(request):
    if request.method == 'POST':
        action = request.POST.get('action') # Will be 'email' or 'password'

        # Security Check
        if action == 'password':
            current_password = request.POST.get('current_password')
            if not request.user.check_password(current_password):
                return JsonResponse({'success': False, 'error': 'Incorrect current password. Please try again.'})

        # 1. Generate a 6-digit OTP
        otp = str(random.randint(100000, 999999))

        # 2. Store OTP and action type securely in the server session
        request.session['auth_otp'] = otp
        request.session['auth_action'] = action

        # 3. Build the Premium HTML Email Template
        subject = f"Finance Tracker: Update your {action}"

        # We use a strict <table> structure because email clients (like Gmail) require it for perfect centering and styling
        html_message = f"""
        <!DOCTYPE html>
        <html>
        <body style="background-color: #f4f4f5; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; padding: 40px 0; margin: 0;">
            <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #f4f4f5;">
                <tr>
                    <td align="center" style="padding: 40px 0;">

                        <!-- Main White Card -->
                        <table width="600" border="0" cellspacing="0" cellpadding="0" style="background-color: #ffffff; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); overflow: hidden;">
                            <tr>
                                <td align="center" style="padding: 30px 20px; border-bottom: 1px solid #f3f4f6;">
                                    <h1 style="margin: 0; color: #0f172a; font-size: 24px; font-weight: 900;">Finance Tracker</h1>
                                </td>
                            </tr>
                            <tr>
                                <td style="padding: 40px 30px;">
                                    <h2 style="margin-top: 0; color: #1e293b; font-size: 20px;">Security Verification</h2>
                                    <p style="color: #475569; font-size: 16px;">Hello <strong>{request.user.username}</strong>,</p>
                                    <p style="color: #475569; font-size: 16px; line-height: 1.5;">We received a request to update the {action} for your Finance Tracker account. Use the 6-digit verification code below to securely authorize this change.</p>

                                    <!-- Cyan OTP Badge -->
                                    <div style="text-align: center; margin: 35px 0;">
                                        <span style="display: inline-block; background-color: #06b6d4; color: #ffffff; font-size: 32px; font-weight: bold; letter-spacing: 12px; padding: 15px 30px 15px 42px; border-radius: 8px;">{otp}</span>
                                    </div>

                                    <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 30px 0;">
                                    <p style="color: #64748b; font-size: 14px; line-height: 1.5; margin-bottom: 0;">If you did not request this, you can safely ignore this email. Your account remains fully secure.</p>
                                </td>
                            </tr>
                        </table>

                        <!-- Footer -->
                        <table width="600" border="0" cellspacing="0" cellpadding="0">
                            <tr>
                                <td align="center" style="padding-top: 20px;">
                                    <p style="color: #94a3b8; font-size: 12px;">&copy; {timezone.now().year} Finance Tracker. Secure automated message.</p>
                                </td>
                            </tr>
                        </table>

                    </td>
                </tr>
            </table>
        </body>
        </html>
        """

        # Plain text fallback for extremely old email clients or smart watches
        plain_message = f"Your 6-digit verification code to update your {action} is: {otp}\n\nIf you did not request this, please secure your account."

        try:
            send_mail(
                subject,
                plain_message,
                'Finance Tracker <hmdelmokhtar05@gmail.com>',
                [request.user.email],
                fail_silently=False,
                html_message=html_message # This forces Gmail to render the UI
            )
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False, 'error': 'Invalid request method'})


@login_required
def verify_and_update(request):
    if request.method == 'POST':
        user_input_otp = request.POST.get('otp')
        action = request.session.get('auth_action')
        saved_otp = request.session.get('auth_otp')

        # 1. Validate the OTP
        if not saved_otp or user_input_otp != saved_otp:
            return JsonResponse({'success': False, 'error': 'Invalid or expired verification code.'})

        # 2. Execute the requested change
        try:
            if action == 'email':
                new_email = request.POST.get('new_email')
                request.user.email = new_email
                request.user.save()

            elif action == 'password':
                new_password = request.POST.get('new_password')
                request.user.set_password(new_password)
                request.user.save()
                # Keeps the user logged in after password change
                update_session_auth_hash(request, request.user)

            # 3. Clear the session data so the OTP cannot be reused
            del request.session['auth_otp']
            del request.session['auth_action']

            return JsonResponse({'success': True})

        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False, 'error': 'Invalid request method'})

@login_required
def verify_otp_only(request):
    if request.method == 'POST':
        user_input_otp = request.POST.get('otp')
        saved_otp = request.session.get('auth_otp')

        if not saved_otp or user_input_otp != saved_otp:
            return JsonResponse({'success': False, 'error': 'Invalid or expired verification code.'})

        return JsonResponse({'success': True})
    return JsonResponse({'success': False, 'error': 'Invalid request method'})

@login_required
def update_preferences(request):
    if request.method == 'POST':
        try:
            # 1. Handle both JSON and standard Form Data
            if 'application/json' in request.content_type:
                import json
                data = json.loads(request.body)
            else:
                data = request.POST

            profile, created = UserProfile.objects.get_or_create(user=request.user)

            # 2. Catch every possible name the HTML select might be using
            raw_currency = (
                data.get('currency') or 
                data.get('default_currency') or 
                data.get('default_base_currency') or 
                data.get('display_currency')
            )
            
            # 3. Strip to a clean 3-letter code (e.g. "EUR") and save
            if raw_currency:
                profile.default_currency = str(raw_currency)[:3].upper()
            
            profile.timezone = data.get('timezone', profile.timezone)
            profile.save()
            
            return JsonResponse({'success': True})
        except Exception as e:
            print("SAVE ERROR:", str(e)) # Prints to your VS Code terminal
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False, 'error': 'Invalid request method'})

@login_required
def update_profile(request):
    if request.method == 'POST':
        try:
            if 'application/json' in request.content_type:
                import json
                data = json.loads(request.body)
            else:
                data = request.POST

            user = request.user
            profile, created = UserProfile.objects.get_or_create(user=user)

            # Update username if provided
            new_username = data.get('username')
            if new_username:
                user.username = new_username
                user.save()

            # Update profile fields safely only if sent in the payload
            if 'phone' in data:
                profile.phone_number = data.get('phone')
            if 'occupation' in data:
                profile.occupation = data.get('occupation')
            if 'website' in data:
                profile.website = data.get('website')
            if 'bio' in data:
                profile.bio = data.get('bio')
                
            profile.save()

            return JsonResponse({'success': True})
        except Exception as e:
            print("PROFILE SAVE ERROR:", str(e))
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False, 'error': 'Invalid request method'})



def trigger_reminders(request):
    # Security: Only run the script if this secret key is in the URL
    if request.GET.get('cron_key') != 'super_secret_ayoub_key_2026':
        return HttpResponse("Unauthorized", status=401)

    try:
        # This executes the script you built in the management/commands folder
        call_command('send_due_reminders')
        return HttpResponse("Reminders executed successfully.")
    except Exception as e:
        return HttpResponse(f"Error: {e}", status=500)
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.chart import BarChart, Reference
import io

def generate_excel_report(queryset):
    wb = openpyxl.Workbook()
    ws_summary = wb.active
    ws_summary.title = "Summary Dashboard"
    ws_data = wb.create_sheet(title="Raw Data")

    # 1. Custom colors based on the payment table image
    black_fill = PatternFill(start_color="000000", end_color="000000", fill_type="solid")
    pink_fill = PatternFill(start_color="FFC0CB", end_color="FFC0CB", fill_type="solid")
    yellow_fill = PatternFill(start_color="FFFACD", end_color="FFFACD", fill_type="solid")
    green_fill = PatternFill(start_color="D5E8D4", end_color="D5E8D4", fill_type="solid")
    cyan_fill = PatternFill(start_color="E0F7FA", end_color="E0F7FA", fill_type="solid") # Light blue row background
    
    white_header_font = Font(color="FFFFFF", bold=True, size=14) 
    black_header_font = Font(color="000000", bold=True, size=14)
    data_font = Font(size=14) 
    price_font = Font(color="0D6511", size=14, bold=True) # Specific dark green price color

    thin_border = Border(left=Side(style='thin', color='B0B0B0'),
                         right=Side(style='thin', color='B0B0B0'),
                         top=Side(style='thin', color='B0B0B0'),
                         bottom=Side(style='thin', color='B0B0B0'))
    center_aligned = Alignment(horizontal="center", vertical="center", wrap_text=True)

    # 2. Raw Data Headers with alternating header colors
    headers = ["Date", "Amount (CNY)", "Category", "Payment Method", "Notes"]
    ws_data.append(headers)
    
    header_styles = [
        (black_fill, white_header_font),
        (pink_fill, black_header_font),
        (yellow_fill, black_header_font),
        (green_fill, black_header_font),
        (green_fill, black_header_font),
    ]
    
    for col_num, cell in enumerate(ws_data[1]):
        fill, font = header_styles[col_num]
        cell.fill, cell.font, cell.alignment, cell.border = fill, font, center_aligned, thin_border
    ws_data.row_dimensions[1].height = 35 

    categories = ["Food & Dining", "Housing & Utilities", "Academics", "Transportation", "Lifestyle & Entertainment"]
    category_totals = {cat: 0 for cat in categories}
    
    data_rows = []
    for exp in queryset:
        val = float(exp.amount)
        data_rows.append([exp.date, val, exp.category, exp.payment_method, exp.notes])
        category_totals[exp.category] += val

    # 3. Format Data Rows
    for i, row_data in enumerate(data_rows, start=2):
        for j, value in enumerate(row_data, start=1):
            cell = ws_data.cell(row=i, column=j, value=value)
            cell.border, cell.alignment = thin_border, center_aligned
            cell.fill = cyan_fill # Light cyan blue for all data rows
            
            if j == 2: # Amount column logic
                cell.number_format = '¥#,##0.00'
                cell.font = price_font
            else:
                cell.font = data_font
                if j == 1 and hasattr(value, 'strftime'):
                    cell.number_format = 'YYYY-MM-DD'
        ws_data.row_dimensions[i].height = 30 

    for col, width in {"A": 20, "B": 22, "C": 38, "D": 28, "E": 45}.items():
        ws_data.column_dimensions[col].width = width
    ws_data.freeze_panes = "A2"

    # 4. Summary Dashboard
    ws_summary.append(["Category Summary", "Total Spent"])
    ws_summary.cell(row=1, column=1).fill, ws_summary.cell(row=1, column=1).font = black_fill, white_header_font
    ws_summary.cell(row=1, column=2).fill, ws_summary.cell(row=1, column=2).font = green_fill, black_header_font
    for cell in ws_summary[1]:
        cell.alignment, cell.border = center_aligned, thin_border
    ws_summary.row_dimensions[1].height = 35

    cat_row = 2
    for cat, total in category_totals.items():
        # ONLY display if the category total is greater than 0
        if total > 0: 
            c_cell = ws_summary.cell(row=cat_row, column=1, value=cat)
            val_cell = ws_summary.cell(row=cat_row, column=2, value=total)
            
            val_cell.number_format = '¥#,##0.00'
            val_cell.font = price_font
            c_cell.font = data_font
            
            for c in (c_cell, val_cell):
                c.border, c.alignment, c.fill = thin_border, center_aligned, cyan_fill
            ws_summary.row_dimensions[cat_row].height = 30
            cat_row += 1

    # 5. Bar Chart Generation
    if cat_row > 2: 
        bar = BarChart()
        bar.type = "col"
        bar.style = 10
        bar.title = "Expenses by Category"
        bar.y_axis.title = "Amount (CNY)"
        bar.x_axis.title = "Category"
        bar.width, bar.height = 20, 12

        # FIX: Point exactly to the numbers and names, skipping the header row entirely
        data = Reference(ws_summary, min_col=2, min_row=2, max_row=cat_row-1)
        labels = Reference(ws_summary, min_col=1, min_row=2, max_row=cat_row-1)
        
        bar.add_data(data, titles_from_data=False)
        bar.set_categories(labels)
        
        # Force the names to the bottom and numbers to the left
        bar.x_axis.tickLblPos = "low"
        bar.y_axis.tickLblPos = "low"
        bar.legend = None 
        
        ws_summary.add_chart(bar, "D2")

    ws_summary.column_dimensions["A"].width = 38
    ws_summary.column_dimensions["B"].width = 25
    ws_summary.sheet_view.showGridLines = False

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()
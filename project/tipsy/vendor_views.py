from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse
from .forms import ProductForm, VendorProfileForm
from .models import Product, OrderItem, Order, CustomUser
from django.views import View
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from django.urls import reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils.decorators import method_decorator
from django.db.models import Sum, DecimalField, ExpressionWrapper, Count, F, Value
from django.db.models.functions import Coalesce, TruncMonth
from django.utils import timezone
from .decorators import vendor_required
from datetime import timedelta, datetime
from io import BytesIO


@method_decorator(vendor_required, name='dispatch')
class VendorDashboardView(LoginRequiredMixin, ListView):
    model = Product
    template_name = 'Vendor/vendor_dashboard.html'
    context_object_name = 'products'

    def get_queryset(self):
        return Product.objects.filter(vendor=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        line_total_expr = ExpressionWrapper(
            F('price') * F('quantity'),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )

        delivered_items = OrderItem.objects.filter(
            product__vendor=self.request.user,
            order__status='Delivered',
        )

        total_sales = delivered_items.aggregate(
            amount=Coalesce(
                Sum(line_total_expr),
                Value(0),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            )
        )['amount']

        sales_last_30_days = delivered_items.filter(
            order__created_at__gte=timezone.now() - timedelta(days=30)
        ).aggregate(
            amount=Coalesce(
                Sum(line_total_expr),
                Value(0),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            )
        )['amount']

        units_sold = delivered_items.aggregate(
            quantity=Coalesce(Sum('quantity'), Value(0))
        )['quantity']

        delivered_orders_count = delivered_items.values('order_id').distinct().count()

        monthly_sales = delivered_items.annotate(
            month=TruncMonth('order__created_at')
        ).values('month').annotate(
            total_sales=Coalesce(
                Sum(line_total_expr),
                Value(0),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            ),
            total_units=Coalesce(Sum('quantity'), Value(0)),
            orders=Count('order', distinct=True),
        ).order_by('-month')[:6]

        context['sales_summary'] = {
            'total_sales': total_sales,
            'sales_last_30_days': sales_last_30_days,
            'units_sold': units_sold,
            'delivered_orders_count': delivered_orders_count,
        }
        context['monthly_sales'] = monthly_sales
        return context


@vendor_required
def vendor_export_report(request):
    """Export vendor sales report as PDF."""
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    
    # Create the HttpResponse object with PDF header
    buffer = BytesIO()
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="vendor_sales_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf"'
    
    # Create PDF document
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=50, leftMargin=50, topMargin=50, bottomMargin=50)
    elements = []
    
    # Styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#5D3931'),
        spaceAfter=30,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor('#5D3931'),
        spaceAfter=12,
        spaceBefore=20,
        fontName='Helvetica-Bold'
    )
    
    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#6B6B6B')
    )
    
    # Title
    elements.append(Paragraph("VENDOR SALES REPORT", title_style))
    elements.append(Spacer(1, 0.2*inch))
    
    # Header info
    header_data = [
        ['Generated:', datetime.now().strftime("%B %d, %Y at %I:%M %p")],
        ['Vendor:', f"{request.user.first_name} {request.user.last_name}"],
        ['Email:', request.user.email]
    ]
    
    header_table = Table(header_data, colWidths=[1.5*inch, 4.5*inch])
    header_table.setStyle(TableStyle([
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#8B7B73')),
        ('TEXTCOLOR', (1, 0), (1, -1), colors.HexColor('#5D3931')),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 0.3*inch))
    
    # Calculate statistics
    line_total_expr = ExpressionWrapper(
        F('price') * F('quantity'),
        output_field=DecimalField(max_digits=12, decimal_places=2),
    )
    
    delivered_items = OrderItem.objects.filter(
        product__vendor=request.user,
        order__status='Delivered',
    ).select_related('product', 'order', 'order__user')
    
    total_sales = delivered_items.aggregate(
        amount=Coalesce(
            Sum(line_total_expr),
            Value(0),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )
    )['amount']
    
    sales_last_30_days = delivered_items.filter(
        order__created_at__gte=timezone.now() - timedelta(days=30)
    ).aggregate(
        amount=Coalesce(
            Sum(line_total_expr),
            Value(0),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )
    )['amount']
    
    units_sold = delivered_items.aggregate(
        quantity=Coalesce(Sum('quantity'), Value(0))
    )['quantity']
    
    delivered_orders_count = delivered_items.values('order_id').distinct().count()
    
    # Sales Summary Section
    elements.append(Paragraph("SALES SUMMARY", heading_style))
    
    summary_data = [
        ['Total Orders Completed', str(delivered_orders_count)],
        ['Total Sales (All Time)', f"NPR {total_sales:,.2f}"],
        ['Sales (Last 30 Days)', f"NPR {sales_last_30_days:,.2f}"],
        ['Total Units Sold', str(units_sold)]
    ]
    
    summary_table = Table(summary_data, colWidths=[3*inch, 3*inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#FBF7F2')),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#5D3931')),
        ('TEXTCOLOR', (1, 0), (1, -1), colors.HexColor('#C9A356')),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E8E8E8')),
        ('TOPPADDING', (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 0.3*inch))
    
    # Monthly Sales Breakdown
    monthly_sales = delivered_items.annotate(
        month=TruncMonth('order__created_at')
    ).values('month').annotate(
        total_sales=Coalesce(
            Sum(line_total_expr),
            Value(0),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        ),
        total_units=Coalesce(Sum('quantity'), Value(0)),
        orders=Count('order', distinct=True),
    ).order_by('-month')[:12]
    
    if monthly_sales:
        elements.append(Paragraph("MONTHLY SALES BREAKDOWN (Last 12 Months)", heading_style))
        
        monthly_data = [['Month', 'Orders', 'Units Sold', 'Total Sales (NPR)']]
        for month_data in monthly_sales:
            monthly_data.append([
                month_data['month'].strftime('%B %Y'),
                str(month_data['orders']),
                str(month_data['total_units']),
                f"NPR {month_data['total_sales']:,.2f}"
            ])
        
        monthly_table = Table(monthly_data, colWidths=[2*inch, 1.2*inch, 1.2*inch, 1.8*inch])
        monthly_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#5D3931')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (3, 1), (3, -1), 'RIGHT'),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F9F9F9')]),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E8E8E8')),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        elements.append(monthly_table)
        elements.append(Spacer(1, 0.3*inch))
    
    # Product Performance
    product_stats = delivered_items.values('product__name').annotate(
        total_quantity=Sum('quantity'),
        total_revenue=Sum(line_total_expr)
    ).order_by('-total_revenue')[:20]  # Top 20 products
    
    if product_stats:
        elements.append(Paragraph("TOP SELLING PRODUCTS", heading_style))
        
        product_data = [['Product Name', 'Units Sold', 'Total Revenue (NPR)']]
        for product in product_stats:
            product_data.append([
                product['product__name'][:40],  # Truncate long names
                str(product['total_quantity']),
                f"NPR {product['total_revenue']:,.2f}"
            ])
        
        product_table = Table(product_data, colWidths=[3*inch, 1.5*inch, 1.7*inch])
        product_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#5D3931')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (2, 1), (2, -1), 'RIGHT'),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F9F9F9')]),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E8E8E8')),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        elements.append(product_table)
    
    # Build PDF
    doc.build(elements)
    
    # Get the value of the BytesIO buffer and write it to the response
    pdf = buffer.getvalue()
    buffer.close()
    response.write(pdf)
    
    return response


@vendor_required
def vendor_export_new_orders(request):
    """Export new orders (Pending) as PDF."""
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    
    # Get all pending order items for this vendor's products
    vendor_order_items = (
        OrderItem.objects
        .filter(product__vendor=request.user, order__status='Pending')
        .select_related('order', 'order__user', 'product')
        .order_by('-order__created_at')
    )
    
    buffer = BytesIO()
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="new_orders_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf"'
    
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=50, leftMargin=50, topMargin=50, bottomMargin=50)
    elements = []
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#5D3931'),
        spaceAfter=30,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor('#5D3931'),
        spaceAfter=12,
        spaceBefore=20,
        fontName='Helvetica-Bold'
    )
    
    # Title
    elements.append(Paragraph("NEW ORDERS REPORT (Pending)", title_style))
    elements.append(Spacer(1, 0.2*inch))
    
    # Header info
    header_data = [
        ['Generated:', datetime.now().strftime("%B %d, %Y at %I:%M %p")],
        ['Vendor:', f"{request.user.first_name} {request.user.last_name}"],
        ['Total Pending Orders:', str(vendor_order_items.values('order_id').distinct().count())]
    ]
    
    header_table = Table(header_data, colWidths=[1.5*inch, 4.5*inch])
    header_table.setStyle(TableStyle([
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#8B7B73')),
        ('TEXTCOLOR', (1, 0), (1, -1), colors.HexColor('#5D3931')),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 0.3*inch))
    
    # Orders Table
    if vendor_order_items:
        elements.append(Paragraph("ORDER DETAILS", heading_style))
        
        orders_data = [['Order ID', 'Order Date', 'Customer', 'Product', 'Qty', 'Price (NPR)', 'Subtotal (NPR)']]
        for item in vendor_order_items:
            orders_data.append([
                f"#{item.order.id}",
                item.order.created_at.strftime("%m/%d/%Y"),
                f"{item.order.user.first_name} {item.order.user.last_name}"[:20],
                item.product.name[:25],
                str(item.quantity),
                f"{item.price:.2f}",
                f"{item.subtotal:.2f}"
            ])
        
        orders_table = Table(orders_data, colWidths=[0.8*inch, 1*inch, 1.2*inch, 1.2*inch, 0.5*inch, 0.9*inch, 0.9*inch])
        orders_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#5D3931')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('ALIGN', (3, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (5, 1), (-1, -1), 'RIGHT'),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F9F9F9')]),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E8E8E8')),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
        ]))
        elements.append(orders_table)
    else:
        elements.append(Paragraph("No pending orders found.", heading_style))
    
    # Build PDF
    doc.build(elements)
    pdf = buffer.getvalue()
    buffer.close()
    response.write(pdf)
    
    return response


@vendor_required
def vendor_export_orders_to_deliver(request):
    """Export orders to deliver (Confirmed) as PDF."""
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    
    # Get all confirmed order items for this vendor's products
    vendor_order_items = (
        OrderItem.objects
        .filter(product__vendor=request.user, order__status='Confirmed')
        .select_related('order', 'order__user', 'product')
        .order_by('-order__created_at')
    )
    
    buffer = BytesIO()
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="orders_to_deliver_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf"'
    
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=50, leftMargin=50, topMargin=50, bottomMargin=50)
    elements = []
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#5D3931'),
        spaceAfter=30,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor('#5D3931'),
        spaceAfter=12,
        spaceBefore=20,
        fontName='Helvetica-Bold'
    )
    
    # Title
    elements.append(Paragraph("ORDERS TO DELIVER REPORT (Confirmed)", title_style))
    elements.append(Spacer(1, 0.2*inch))
    
    # Header info
    header_data = [
        ['Generated:', datetime.now().strftime("%B %d, %Y at %I:%M %p")],
        ['Vendor:', f"{request.user.first_name} {request.user.last_name}"],
        ['Total Orders to Deliver:', str(vendor_order_items.values('order_id').distinct().count())]
    ]
    
    header_table = Table(header_data, colWidths=[1.5*inch, 4.5*inch])
    header_table.setStyle(TableStyle([
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#8B7B73')),
        ('TEXTCOLOR', (1, 0), (1, -1), colors.HexColor('#5D3931')),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 0.3*inch))
    
    # Orders Table
    if vendor_order_items:
        elements.append(Paragraph("ORDER DETAILS", heading_style))
        
        orders_data = [['Order ID', 'Order Date', 'Customer', 'Product', 'Qty', 'Price (NPR)', 'Subtotal (NPR)']]
        for item in vendor_order_items:
            orders_data.append([
                f"#{item.order.id}",
                item.order.created_at.strftime("%m/%d/%Y"),
                f"{item.order.user.first_name} {item.order.user.last_name}"[:20],
                item.product.name[:25],
                str(item.quantity),
                f"{item.price:.2f}",
                f"{item.subtotal:.2f}"
            ])
        
        orders_table = Table(orders_data, colWidths=[0.8*inch, 1*inch, 1.2*inch, 1.2*inch, 0.5*inch, 0.9*inch, 0.9*inch])
        orders_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#5D3931')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('ALIGN', (3, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (5, 1), (-1, -1), 'RIGHT'),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F9F9F9')]),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E8E8E8')),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
        ]))
        elements.append(orders_table)
    else:
        elements.append(Paragraph("No orders to deliver found.", heading_style))
    
    # Build PDF
    doc.build(elements)
    pdf = buffer.getvalue()
    buffer.close()
    response.write(pdf)
    
    return response


@vendor_required
def vendor_export_delivered_orders(request):
    """Export delivered orders as PDF."""
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    
    # Get all delivered order items for this vendor's products
    vendor_order_items = (
        OrderItem.objects
        .filter(product__vendor=request.user, order__status='Delivered')
        .select_related('order', 'order__user', 'product')
        .order_by('-order__created_at')
    )
    
    buffer = BytesIO()
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="delivered_orders_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf"'
    
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=50, leftMargin=50, topMargin=50, bottomMargin=50)
    elements = []
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#5D3931'),
        spaceAfter=30,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor('#5D3931'),
        spaceAfter=12,
        spaceBefore=20,
        fontName='Helvetica-Bold'
    )
    
    # Title
    elements.append(Paragraph("DELIVERED ORDERS REPORT", title_style))
    elements.append(Spacer(1, 0.2*inch))
    
    # Header info
    header_data = [
        ['Generated:', datetime.now().strftime("%B %d, %Y at %I:%M %p")],
        ['Vendor:', f"{request.user.first_name} {request.user.last_name}"],
        ['Total Delivered Orders:', str(vendor_order_items.values('order_id').distinct().count())]
    ]
    
    header_table = Table(header_data, colWidths=[1.5*inch, 4.5*inch])
    header_table.setStyle(TableStyle([
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#8B7B73')),
        ('TEXTCOLOR', (1, 0), (1, -1), colors.HexColor('#5D3931')),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 0.3*inch))
    
    # Orders Table
    if vendor_order_items:
        elements.append(Paragraph("ORDER DETAILS", heading_style))
        
        orders_data = [['Order ID', 'Order Date', 'Customer', 'Product', 'Qty', 'Price (NPR)', 'Subtotal (NPR)']]
        for item in vendor_order_items:
            orders_data.append([
                f"#{item.order.id}",
                item.order.created_at.strftime("%m/%d/%Y"),
                f"{item.order.user.first_name} {item.order.user.last_name}"[:20],
                item.product.name[:25],
                str(item.quantity),
                f"{item.price:.2f}",
                f"{item.subtotal:.2f}"
            ])
        
        orders_table = Table(orders_data, colWidths=[0.8*inch, 1*inch, 1.2*inch, 1.2*inch, 0.5*inch, 0.9*inch, 0.9*inch])
        orders_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#5D3931')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('ALIGN', (3, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (5, 1), (-1, -1), 'RIGHT'),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F9F9F9')]),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E8E8E8')),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
        ]))
        elements.append(orders_table)
    else:
        elements.append(Paragraph("No delivered orders found.", heading_style))
    
    # Build PDF
    doc.build(elements)
    pdf = buffer.getvalue()
    buffer.close()
    response.write(pdf)
    
    return response


@method_decorator(vendor_required, name='dispatch')
class VendorOrdersView(LoginRequiredMixin, View):
    """Show all orders that contain products belonging to this vendor."""

    def get(self, request, *args, **kwargs):
        # Get all order items for this vendor's products
        vendor_order_items = (
            OrderItem.objects
            .filter(product__vendor=request.user)
            .select_related('order', 'order__user', 'product')
            .order_by('-order__created_at')
        )

        # Group by order
        orders_dict = {}
        for item in vendor_order_items:
            order = item.order
            if order.id not in orders_dict:
                orders_dict[order.id] = {
                    'order': order,
                    'customer': order.user,
                    'items': [],
                    'vendor_total': 0,
                }
            orders_dict[order.id]['items'].append(item)
            orders_dict[order.id]['vendor_total'] += item.subtotal

        vendor_orders = list(orders_dict.values())

        # Categorize orders by status
        pending_orders = [o for o in vendor_orders if o['order'].status == 'Pending']
        confirmed_orders = [o for o in vendor_orders if o['order'].status == 'Confirmed']
        delivered_orders = [o for o in vendor_orders if o['order'].status == 'Delivered']

        return render(request, 'Vendor/vendor_orders.html', {
            'pending_orders': pending_orders,
            'confirmed_orders': confirmed_orders,
            'delivered_orders': delivered_orders,
        })


@method_decorator(vendor_required, name='dispatch')
class VendorUpdateOrderStatusView(LoginRequiredMixin, View):
    """Allow vendor to update the status of an order."""

    def post(self, request, order_id, *args, **kwargs):
        order = get_object_or_404(Order, id=order_id)

        # Verify this vendor has products in this order
        has_items = OrderItem.objects.filter(
            order=order, product__vendor=request.user
        ).exists()

        if not has_items:
            messages.error(request, "You don't have permission to update this order.")
            return redirect('vendor_orders')

        new_status = request.POST.get('status')
        if new_status in ['Pending', 'Confirmed', 'Delivered']:
            old_status = order.status
            order.status = new_status
            order.save()
            # Note: Notifications are created automatically via signals in signals.py
            messages.success(request, f"Order #{order.id} status updated to {new_status}.")
        else:
            messages.error(request, "Invalid status.")

        return redirect('vendor_orders')


@method_decorator(vendor_required, name='dispatch')
class VendorNewOrdersView(LoginRequiredMixin, View):
    """Show new orders (Pending status) for this vendor."""

    def get(self, request, *args, **kwargs):
        # Get all pending order items for this vendor's products
        vendor_order_items = (
            OrderItem.objects
            .filter(product__vendor=request.user, order__status='Pending')
            .select_related('order', 'order__user', 'product')
            .order_by('-order__created_at')
        )

        # Group by order
        orders_dict = {}
        for item in vendor_order_items:
            order = item.order
            if order.id not in orders_dict:
                orders_dict[order.id] = {
                    'order': order,
                    'customer': order.user,
                    'items': [],
                    'vendor_total': 0,
                }
            orders_dict[order.id]['items'].append(item)
            orders_dict[order.id]['vendor_total'] += item.subtotal

        pending_orders = list(orders_dict.values())

        context = {
            'orders': pending_orders,
            'status': 'Pending',
            'count': len(pending_orders),
        }
        return render(request, 'Vendor/vendor_new_orders.html', context)


@method_decorator(vendor_required, name='dispatch')
class VendorOrdersToDeliverView(LoginRequiredMixin, View):
    """Show orders to be delivered (Confirmed status) for this vendor."""

    def get(self, request, *args, **kwargs):
        # Get all confirmed order items for this vendor's products
        vendor_order_items = (
            OrderItem.objects
            .filter(product__vendor=request.user, order__status='Confirmed')
            .select_related('order', 'order__user', 'product')
            .order_by('-order__created_at')
        )

        # Group by order
        orders_dict = {}
        for item in vendor_order_items:
            order = item.order
            if order.id not in orders_dict:
                orders_dict[order.id] = {
                    'order': order,
                    'customer': order.user,
                    'items': [],
                    'vendor_total': 0,
                }
            orders_dict[order.id]['items'].append(item)
            orders_dict[order.id]['vendor_total'] += item.subtotal

        confirmed_orders = list(orders_dict.values())

        context = {
            'orders': confirmed_orders,
            'status': 'Confirmed',
            'count': len(confirmed_orders),
        }
        return render(request, 'Vendor/vendor_orders_to_deliver.html', context)


@method_decorator(vendor_required, name='dispatch')
class VendorDeliveredOrdersView(LoginRequiredMixin, View):
    """Show delivered orders for this vendor."""

    def get(self, request, *args, **kwargs):
        # Get all delivered order items for this vendor's products
        vendor_order_items = (
            OrderItem.objects
            .filter(product__vendor=request.user, order__status='Delivered')
            .select_related('order', 'order__user', 'product')
            .order_by('-order__created_at')
        )

        # Group by order
        orders_dict = {}
        for item in vendor_order_items:
            order = item.order
            if order.id not in orders_dict:
                orders_dict[order.id] = {
                    'order': order,
                    'customer': order.user,
                    'items': [],
                    'vendor_total': 0,
                }
            orders_dict[order.id]['items'].append(item)
            orders_dict[order.id]['vendor_total'] += item.subtotal

        delivered_orders = list(orders_dict.values())

        context = {
            'orders': delivered_orders,
            'status': 'Delivered',
            'count': len(delivered_orders),
        }
        return render(request, 'Vendor/vendor_delivered_orders.html', context)


@method_decorator(vendor_required, name='dispatch')
class VendorProductsView(LoginRequiredMixin, ListView):
    """Vendor page to view and manage their products with CRUD operations."""
    model = Product
    template_name = 'Vendor/vendor_products.html'
    context_object_name = 'products'
    paginate_by = 10

    def get_queryset(self):
        all_products = Product.objects.filter(vendor=self.request.user).order_by('-created_at')
        filter_type = self.request.GET.get('filter', 'all')
        
        if filter_type == 'active':
            return all_products.filter(stock__gt=10)
        elif filter_type == 'low':
            return all_products.filter(stock__lte=10, stock__gt=0)
        elif filter_type == 'out':
            return all_products.filter(stock=0)
        else:
            return all_products

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        all_products = Product.objects.filter(vendor=self.request.user)
        
        context['total_products'] = all_products.count()
        
        # Count low stock products (stock <= 10 but > 0)
        context['low_stock_count'] = all_products.filter(stock__lte=10, stock__gt=0).count()
        
        # Calculate total inventory value and add to each product
        total_value = 0
        products_with_value = []
        for product in context['products']:
            product_value = float(product.price) * product.stock
            total_value += product_value
            product.item_value = product_value
            products_with_value.append(product)
        
        context['products'] = products_with_value
        context['total_value'] = total_value
        context['current_filter'] = self.request.GET.get('filter', 'all')
        return context


@vendor_required
def vendor_export_products_pdf(request):
    """Export vendor's products as PDF with name, price, and stock details."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    
    # Get vendor's products
    products = Product.objects.filter(vendor=request.user).order_by('name')
    
    # Create the HttpResponse object with PDF header
    buffer = BytesIO()
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="products_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf"'
    
    # Create PDF document
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=50, bottomMargin=50)
    elements = []
    
    # Styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=20,
        textColor=colors.HexColor('#5D3931'),
        spaceAfter=12,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#8B7B73'),
        alignment=TA_CENTER,
        spaceAfter=20
    )
    
    # Title
    elements.append(Paragraph("PRODUCT INVENTORY", title_style))
    elements.append(Paragraph(f"Vendor: {request.user.business_name or request.user.get_full_name()}", subtitle_style))
    elements.append(Paragraph(f"Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}", subtitle_style))
    elements.append(Spacer(1, 0.2*inch))
    
    if products.exists():
        # Product table
        product_data = [['Product Name', 'Price (NPR)', 'Stock', 'Category', 'Created Date']]
        
        for product in products:
            category_name = product.category.name if product.category else 'Uncategorized'
            product_data.append([
                product.name[:35],  # Truncate long names
                f"NPR {product.price:,.2f}",
                str(product.stock),
                category_name[:20],
                product.created_at.strftime('%d-%m-%Y')
            ])
        
        product_table = Table(product_data, colWidths=[2.2*inch, 1.3*inch, 0.9*inch, 1.3*inch, 1.2*inch])
        product_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#5D3931')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (0, 1), (0, -1), 'LEFT'),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F9F9F9')]),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E8E8E8')),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
        ]))
        elements.append(product_table)
        elements.append(Spacer(1, 0.2*inch))
        
        # Summary
        total_value = sum(float(p.price * p.stock) for p in products)
        summary_style = ParagraphStyle(
            'Summary',
            parent=styles['Normal'],
            fontSize=9,
            textColor=colors.HexColor('#5D3931'),
            alignment=TA_CENTER,
        )
        elements.append(Paragraph(
            f"<b>Total Products:</b> {products.count()} | "
            f"<b>Total Stock Value:</b> NPR {total_value:,.2f}",
            summary_style
        ))
    else:
        elements.append(Paragraph("No products found.", styles['Normal']))
    
    # Build PDF
    doc.build(elements)
    
    # Get the value of the BytesIO buffer and write it to the response
    pdf = buffer.getvalue()
    buffer.close()
    response.write(pdf)
    
    return response


@method_decorator(vendor_required, name='dispatch')
class ProductCreateView(LoginRequiredMixin, CreateView):
    model = Product
    form_class = ProductForm
    template_name = 'product_form.html'
    success_url = reverse_lazy('vendor_dashboard')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['action'] = 'Add'
        return context

    def form_valid(self, form):
        form.instance.vendor = self.request.user
        return super().form_valid(form)


@method_decorator(vendor_required, name='dispatch')
class ProductUpdateView(LoginRequiredMixin, UpdateView):
    model = Product
    form_class = ProductForm
    template_name = 'product_form.html'
    success_url = reverse_lazy('vendor_dashboard')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['action'] = 'Edit'
        return context

    def get_queryset(self):
        return Product.objects.filter(vendor=self.request.user)


@method_decorator(vendor_required, name='dispatch')
class ProductDeleteView(LoginRequiredMixin, DeleteView):
    model = Product
    template_name = 'product_confirm_delete.html'
    success_url = reverse_lazy('vendor_dashboard')

    def get_queryset(self):
        return Product.objects.filter(vendor=self.request.user)


@method_decorator(vendor_required, name='dispatch')
class VendorProfileUpdateView(LoginRequiredMixin, UpdateView):
    model = CustomUser
    form_class = VendorProfileForm
    template_name = 'profile_update.html'
    success_url = reverse_lazy('vendor_dashboard')

    def get_object(self, queryset=None):
        return self.request.user

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['profile_title'] = 'Vendor Profile'
        context['back_url_name'] = 'vendor_dashboard'
        return context

    def form_valid(self, form):
        messages.success(self.request, 'Profile updated successfully.')
        return super().form_valid(form)


# =====================================
# VENDOR NOTIFICATION VIEWS
# =====================================

from .models import Notification
from django.http import JsonResponse

@method_decorator(vendor_required, name='dispatch')
class VendorNotificationListView(LoginRequiredMixin, ListView):
    """Display all notifications for the vendor"""
    model = Notification
    template_name = 'Vendor/vendor_notifications.html'
    context_object_name = 'notifications'
    paginate_by = 20
    
    def get_queryset(self):
        return Notification.objects.filter(recipient=self.request.user).order_by('-created_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user_notifications = Notification.objects.filter(recipient=self.request.user)
        context['unread_count'] = user_notifications.filter(is_read=False).count()
        context['total_count'] = user_notifications.count()
        return context


@method_decorator(vendor_required, name='dispatch')
class VendorNotificationDetailView(LoginRequiredMixin, DetailView):
    """Display a single notification and mark as read"""
    model = Notification
    template_name = 'Vendor/vendor_notification_detail.html'
    context_object_name = 'notification'
    
    def get_queryset(self):
        return Notification.objects.filter(recipient=self.request.user)
    
    def get_object(self, queryset=None):
        notification = super().get_object(queryset)
        notification.mark_as_read()
        return notification


@method_decorator(vendor_required, name='dispatch')
class VendorUnreadNotificationCountView(LoginRequiredMixin, View):
    """Get unread notification count (AJAX endpoint)"""
    
    def get(self, request, *args, **kwargs):
        unread_count = Notification.objects.filter(recipient=request.user, is_read=False).count()
        return JsonResponse({'unread_count': unread_count})


from django.utils import timezone
from .models import Chat, Notification

@method_decorator(vendor_required, name='dispatch')
class VendorChatListView(LoginRequiredMixin, ListView):
    model = Chat
    template_name = 'Vendor/vendor_chat_list.html'
    context_object_name = 'chats'
    
    def get_queryset(self):
        return Chat.objects.filter(vendor=self.request.user)

@method_decorator(vendor_required, name='dispatch')
class VendorChatDetailView(LoginRequiredMixin, View):
    def get(self, request, chat_id):
        chat = get_object_or_404(Chat, id=chat_id, vendor=request.user)

        # Mark chat notifications as read when vendor opens the chat
        Notification.objects.filter(
            recipient=request.user,
            chat=chat,
            notification_type='chat_message',
            is_read=False,
        ).update(is_read=True, read_at=timezone.now())

        context = {
            'chat': chat,
            'customer': chat.customer
        }
        return render(request, 'Vendor/vendor_chat.html', context)

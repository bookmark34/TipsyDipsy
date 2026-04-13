from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings
from django.http import HttpResponse
from .forms import AdminSetUserPasswordForm
from .models import CustomUser, Product, Category, Order, OrderItem
from django.views import View
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils.decorators import method_decorator
from django.db.models import Count, F, Sum, DecimalField, ExpressionWrapper, Value
from django.db.models.functions import Coalesce, TruncMonth
from django.utils import timezone
from django.utils.timezone import now
from .decorators import admin_required
import json
from datetime import timedelta, datetime, date


@method_decorator(admin_required, name='dispatch')
class AdminDashboardView(LoginRequiredMixin, View):
    template_name = 'Admin/AdminDashboard.html'

    def get(self, request, *args, **kwargs):
        now = timezone.now()

        # Build a 6-month sequence (oldest to latest) for chart axes.
        months = []
        year = now.year
        month = now.month
        for _ in range(6):
            months.append((year, month))
            month -= 1
            if month == 0:
                month = 12
                year -= 1
        months.reverse()

        month_labels = [datetime(y, m, 1).strftime('%b %Y') for y, m in months]
        month_keys = [f'{y:04d}-{m:02d}' for y, m in months]
        oldest_start = date(months[0][0], months[0][1], 1)

        monthly_orders_qs = (
            Order.objects.filter(created_at__date__gte=oldest_start)
            .annotate(month=TruncMonth('created_at'))
            .values('month')
            .annotate(
                total_orders=Count('id'),
                total_revenue=Coalesce(
                    Sum('total_price'),
                    Value(0),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                ),
            )
            .order_by('month')
        )

        monthly_signups_qs = (
            CustomUser.objects.filter(date_joined__date__gte=oldest_start)
            .annotate(month=TruncMonth('date_joined'))
            .values('month')
            .annotate(total_signups=Count('id'))
            .order_by('month')
        )

        orders_map = {row['month'].strftime('%Y-%m'): row['total_orders'] for row in monthly_orders_qs}
        revenue_map = {row['month'].strftime('%Y-%m'): float(row['total_revenue']) for row in monthly_orders_qs}
        signups_map = {row['month'].strftime('%Y-%m'): row['total_signups'] for row in monthly_signups_qs}

        monthly_orders = [orders_map.get(key, 0) for key in month_keys]
        monthly_revenue = [revenue_map.get(key, 0) for key in month_keys]
        monthly_signups = [signups_map.get(key, 0) for key in month_keys]

        order_status_qs = Order.objects.values('status').annotate(total=Count('id'))
        order_status_map = {row['status']: row['total'] for row in order_status_qs}
        order_status_labels = ['Pending', 'Confirmed', 'Delivered']
        order_status_data = [order_status_map.get(label, 0) for label in order_status_labels]

        line_total_expr = ExpressionWrapper(
            F('price') * F('quantity'),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )
        top_vendors = (
            OrderItem.objects.filter(order__status='Delivered')
            .values('product__vendor__username')
            .annotate(
                total_sales=Coalesce(
                    Sum(line_total_expr),
                    Value(0),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                ),
                orders_count=Count('order', distinct=True),
            )
            .order_by('-total_sales')[:5]
        )

        new_users_last_30_days = CustomUser.objects.filter(
            date_joined__gte=now - timedelta(days=30)
        ).count()

        context = {
            'total_users': CustomUser.objects.count(),
            'total_customers': CustomUser.objects.filter(role='CUSTOMER').count(),
            'total_vendors': CustomUser.objects.filter(role='VENDOR').count(),
            'pending_vendors': CustomUser.objects.filter(role='VENDOR', vendor_status='PENDING').count(),
            'approved_vendors': CustomUser.objects.filter(role='VENDOR', vendor_status='APPROVED').count(),
            'rejected_vendors': CustomUser.objects.filter(role='VENDOR', vendor_status='REJECTED').count(),
            'total_products': Product.objects.count(),
            'total_orders': Order.objects.count(),
            'total_categories': Category.objects.count(),
            'recent_orders': Order.objects.select_related('user').order_by('-created_at')[:8],
            'recent_signups': CustomUser.objects.order_by('-date_joined')[:8],
            'new_users_last_30_days': new_users_last_30_days,
            'top_vendors': top_vendors,
            'monthly_labels_json': json.dumps(month_labels),
            'monthly_orders_json': json.dumps(monthly_orders),
            'monthly_revenue_json': json.dumps(monthly_revenue),
            'monthly_signups_json': json.dumps(monthly_signups),
            'order_status_labels_json': json.dumps(order_status_labels),
            'order_status_data_json': json.dumps(order_status_data),
        }
        return render(request, self.template_name, context)


@admin_required
def admin_export_report_pdf(request):
    """Export admin dashboard snapshot as a PDF report."""
    from io import BytesIO
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER

    now = timezone.now()
    generated_at = now.strftime('%B %d, %Y at %I:%M %p')

    total_users = CustomUser.objects.count()
    total_customers = CustomUser.objects.filter(role='CUSTOMER').count()
    pending_vendors = CustomUser.objects.filter(role='VENDOR', vendor_status='PENDING').count()
    approved_vendors = CustomUser.objects.filter(role='VENDOR', vendor_status='APPROVED').count()
    rejected_vendors = CustomUser.objects.filter(role='VENDOR', vendor_status='REJECTED').count()
    total_products = Product.objects.count()
    total_orders = Order.objects.count()

    monthly_orders = (
        Order.objects.annotate(month=TruncMonth('created_at'))
        .values('month')
        .annotate(
            count=Count('id'),
            revenue=Coalesce(
                Sum('total_price'),
                Value(0),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            ),
        )
        .order_by('-month')[:12]
    )

    buffer = BytesIO()
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="admin_monthly_report_{now.strftime("%Y%m%d_%H%M%S")}.pdf"'

    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    elements = []

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'TitleStyle',
        parent=styles['Heading1'],
        fontSize=20,
        textColor=colors.HexColor("#673518"),
        alignment=TA_CENTER,
        spaceAfter=18,
    )

    elements.append(Paragraph('TipsyDipsy Admin Report', title_style))
    elements.append(Paragraph(f'Generated: {generated_at}', styles['Normal']))
    elements.append(Spacer(1, 0.2 * inch))

    summary_data = [
        ['Metric', 'Value'],
        ['Total Users', str(total_users)],
        ['Total Customers', str(total_customers)],
        ['Pending Vendors', str(pending_vendors)],
        ['Approved Vendors', str(approved_vendors)],
        ['Rejected Vendors', str(rejected_vendors)],
        ['Total Products', str(total_products)],
        ['Total Orders', str(total_orders)],
    ]
    summary_table = Table(summary_data, colWidths=[3.5 * inch, 3.2 * inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#723907")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#D6DEE5')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F5F8FA')]),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 0.25 * inch))

    monthly_data = [['Month', 'Orders', 'Revenue (NPR)']]
    for row in monthly_orders:
        monthly_data.append([
            row['month'].strftime('%b %Y'),
            str(row['count']),
            f"{row['revenue']:,.2f}",
        ])

    monthly_table = Table(monthly_data, colWidths=[2.3 * inch, 1.8 * inch, 2.6 * inch])
    monthly_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#723907")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#D6DEE5')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F5F8FA')]),
        ('ALIGN', (1, 1), (2, -1), 'RIGHT'),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
    ]))
    elements.append(Paragraph('Monthly Performance (Last 12 Months)', styles['Heading3']))
    elements.append(monthly_table)

    doc.build(elements)
    response.write(buffer.getvalue())
    buffer.close()
    return response


@method_decorator(admin_required, name='dispatch')
class AdminVendorsView(LoginRequiredMixin, View):
    template_name = 'Admin/AdminVendors.html'

    def get(self, request, *args, **kwargs):
        context = {
            'pending_vendors': CustomUser.objects.filter(role='VENDOR', vendor_status='PENDING').order_by('-date_joined'),
            'approved_vendors': CustomUser.objects.filter(role='VENDOR', vendor_status='APPROVED').order_by('-date_joined'),
            'rejected_vendors': CustomUser.objects.filter(role='VENDOR', vendor_status='REJECTED').order_by('-date_joined'),
        }
        return render(request, self.template_name, context)


@method_decorator(admin_required, name='dispatch')
class AdminApproveVendorView(LoginRequiredMixin, View):
    def post(self, request, user_id, *args, **kwargs):
        vendor = get_object_or_404(CustomUser, id=user_id, role='VENDOR')
        vendor.vendor_status = 'APPROVED'
        vendor.save(update_fields=['vendor_status'])
        
        # Send vendor approval email
        subject = 'Your TipsyDipsy Vendor Account Has Been Approved!'
        message = f"""Hello {vendor.first_name},

Great news! Your vendor account on TipsyDipsy has been approved by our admin team.

You can now log in with your credentials and start adding your products to our platform.

Login Details:
- Username: {vendor.username}
- Email: {vendor.email}

Visit https://tipsydipsy.com to log in and get started.

We're excited to have you on board!

Best regards,
TipsyDipsy Team"""
        send_mail(
            subject,
            message,
            settings.EMAIL_HOST_USER,
            [vendor.email],
            fail_silently=True,
        )
        messages.success(request, f"Vendor {vendor.username} approved and notified via email.")
        return redirect('admin_vendors')


@method_decorator(admin_required, name='dispatch')
class AdminRejectVendorView(LoginRequiredMixin, View):
    def post(self, request, user_id, *args, **kwargs):
        vendor = get_object_or_404(CustomUser, id=user_id, role='VENDOR')
        vendor.vendor_status = 'REJECTED'
        vendor.save(update_fields=['vendor_status'])
        
        # Send vendor rejection email
        subject = 'TipsyDipsy Vendor Account Application - Status Update'
        message = f"""Hello {vendor.first_name},

Thank you for your interest in becoming a vendor on TipsyDipsy.

Unfortunately, after reviewing your application, our admin team has decided not to approve your vendor account at this time.

This decision may be based on various factors including compliance requirements or platform standards.

If you have any questions or would like more information about why your application was not approved, please contact our support team at support@tipsydipsy.com

We encourage you to try again in the future!

Best regards,
TipsyDipsy Team"""
        send_mail(
            subject,
            message,
            settings.EMAIL_HOST_USER,
            [vendor.email],
            fail_silently=True,
        )
        messages.success(request, f"Vendor {vendor.username} rejected and notified via email.")
        return redirect('admin_vendors')


@method_decorator(admin_required, name='dispatch')
class AdminRemoveVendorView(LoginRequiredMixin, View):
    def post(self, request, user_id, *args, **kwargs):
        vendor = get_object_or_404(CustomUser, id=user_id, role='VENDOR', vendor_status='APPROVED')
        username = vendor.username
        vendor.delete()
        messages.success(request, f"Approved vendor {username} has been removed.")
        return redirect('admin_vendors')


@method_decorator(admin_required, name='dispatch')
class AdminProductsView(LoginRequiredMixin, ListView):
    model = Product
    template_name = 'Admin/AdminProducts.html'
    context_object_name = 'products'

    def get_queryset(self):
        return Product.objects.select_related('vendor', 'category').order_by('-created_at')


@method_decorator(admin_required, name='dispatch')
class AdminOrdersView(LoginRequiredMixin, ListView):
    model = Order
    template_name = 'Admin/AdminOrders.html'
    context_object_name = 'orders'

    def get_queryset(self):
        return Order.objects.select_related('user').order_by('-created_at')


@method_decorator(admin_required, name='dispatch')
class AdminCustomersView(LoginRequiredMixin, ListView):
    model = CustomUser
    template_name = 'Admin/AdminCustomers.html'
    context_object_name = 'customers'

    def get_queryset(self):
        return CustomUser.objects.filter(role='CUSTOMER').order_by('-date_joined')


@method_decorator(admin_required, name='dispatch')
class AdminChangeUserPasswordView(LoginRequiredMixin, View):
    template_name = 'Admin/AdminChangeUserPassword.html'

    def get_target_user(self, user_id):
        return get_object_or_404(CustomUser, id=user_id, role__in=['CUSTOMER', 'VENDOR'])

    def get(self, request, user_id, *args, **kwargs):
        target_user = self.get_target_user(user_id)
        form = AdminSetUserPasswordForm(user=target_user)
        return render(request, self.template_name, {'form': form, 'target_user': target_user})

    def post(self, request, user_id, *args, **kwargs):
        target_user = self.get_target_user(user_id)
        form = AdminSetUserPasswordForm(request.POST, user=target_user)

        if form.is_valid():
            new_password = form.cleaned_data['new_password1']
            target_user.set_password(new_password)
            target_user.save(update_fields=['password'])

            recipient_name = target_user.first_name or target_user.username
            subject = 'TipsyDipsy Account Password Updated'
            message = f"""Hello {recipient_name},

Your account password was changed by an administrator.

Account details:
- Username: {target_user.username}
- Role: {target_user.get_role_display()}
- New Password: {new_password}

If this change was expected, you can now log in with your new password.
For security, please change this password after your next login.
If you did not expect this change, please contact support immediately.

Best regards,
TipsyDipsy Team"""
            send_mail(
                subject,
                message,
                settings.EMAIL_HOST_USER,
                [target_user.email],
                fail_silently=True,
            )

            messages.success(request, f"Password updated successfully for {target_user.username}.")

            if target_user.role == 'VENDOR':
                return redirect('admin_vendors')
            return redirect('admin_customers')

        return render(request, self.template_name, {'form': form, 'target_user': target_user})

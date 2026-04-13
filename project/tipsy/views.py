from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.tokens import default_token_generator
from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.http import HttpResponse, JsonResponse
import requests
from .forms import (
    SignUpForm,
    LoginForm,
    ProductForm,
    AdminSetUserPasswordForm,
    CustomerProfileForm,
    VendorProfileForm,
)
from .models import CustomUser, Payment, Product, Category, Cart, CartItem, Order, OrderItem, FAQ
from django.views import View
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse_lazy, reverse
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils.decorators import method_decorator
from django.db.models import Count, F, Sum, DecimalField, ExpressionWrapper, Value
from django.db.models.functions import Coalesce, TruncMonth
from django.utils import timezone
from django.utils.timezone import now
from .decorators import vendor_required, customer_required, admin_required
import json
import math
from datetime import timedelta, datetime, date

def calculate_distance(lat1, lon1, lat2, lon2):
    if not all([lat1, lon1, lat2, lon2]):
        return float('inf')
    lon1, lat1, lon2, lat2 = map(math.radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    r = 6371
    return c * r


def customer_can_purchase(user, minimum_age=18):
    return user.is_customer() and user.is_age_verified(minimum_age)

class SignUpView(CreateView):
    form_class = SignUpForm
    template_name = 'signup.html'
    success_url = reverse_lazy('home')

    def form_valid(self, form):
        user = form.save()
        password = self.request.POST.get('password1')
        
        if user.is_vendor():
            user.vendor_status = 'PENDING'
            user.save(update_fields=['vendor_status'])
            # Send vendor signup confirmation email
            subject = 'Welcome to TipsyDipsy - Vendor Account Pending Review'
            message = f"""Hello {user.first_name},

Thank you for signing up as a vendor on TipsyDipsy!

Your vendor account has been created with the following details:
- Username: {user.username}
- Email: {user.email}
- Password: {password}

Your account is currently pending admin approval. Once approved, you will be able to log in and start adding your products.

We will notify you via email once your account has been reviewed.

Best regards,
TipsyDipsy Team"""
            send_mail(
                subject,
                message,
                settings.EMAIL_HOST_USER,
                [user.email],
                fail_silently=True,
            )
            messages.info(
                self.request,
                'Vendor signup submitted. Please wait for admin approval before logging in. A confirmation email has been sent to your email address.'
            )
            return redirect('login')

        # Send customer verification email
        token = default_token_generator.make_token(user)
        user.email_verification_token = token
        user.save(update_fields=['email_verification_token'])
        
        verification_link = self.request.build_absolute_uri(
            reverse('verify_email', kwargs={
                'uidb64': urlsafe_base64_encode(force_bytes(user.pk)),
                'token': token
            })
        )
        
        subject = 'Verify Your Email - TipsyDipsy'
        message = f"""Hello {user.first_name},

Welcome to TipsyDipsy! Your customer account has been successfully created.

Your account details:
- Username: {user.username}
- Email: {user.email}
- Password: {password}

To complete your registration and start shopping, please verify your email by clicking the link below:

{verification_link}

This link will expire in 24 hours.

If you did not create this account, please ignore this email.

Best regards,
TipsyDipsy Team"""
        send_mail(
            subject,
            message,
            settings.EMAIL_HOST_USER,
            [user.email],
            fail_silently=True,
        )
        messages.info(
            self.request,
            'Account created! Please check your email to verify your account before logging in.'
        )
        return redirect('login')

class UserLoginView(LoginView):
    form_class = LoginForm
    template_name = 'login.html'

    def form_valid(self, form):
        user = form.get_user()

        if user.is_vendor() and user.vendor_status != 'APPROVED':
            if user.vendor_status == 'PENDING':
                message = 'Your vendor account is pending admin approval.'
            else:
                message = 'Your vendor account was rejected. Please contact the admin.'

            form.add_error(None, message)
            messages.error(self.request, message)
            return self.form_invalid(form)
        
        if user.is_customer() and not user.email_verified:
            message = 'Please verify your email before logging in. Check your inbox for the verification link.'
            form.add_error(None, message)
            messages.error(self.request, message)
            return self.form_invalid(form)

        return super().form_valid(form)

    def get_success_url(self):
        user = self.request.user
        if user.is_admin():
            return reverse_lazy('admin_dashboard')
        if user.is_vendor():
            return reverse_lazy('vendor_dashboard')
        else:
            return reverse_lazy('customer_dashboard')

class UserLogoutView(LogoutView):
    next_page = reverse_lazy('home')


class EmailVerificationView(View):
    def get(self, request, uidb64, token, *args, **kwargs):
        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            user = CustomUser.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, CustomUser.DoesNotExist):
            user = None

        if user is not None and default_token_generator.check_token(user, token):
            user.email_verified = True
            user.email_verification_token = ''
            user.save(update_fields=['email_verified', 'email_verification_token'])
            messages.success(request, 'Email verified successfully! You can now log in.')
            return redirect('login')
        else:
            messages.error(request, 'Email verification link is invalid or expired.')
            return redirect('signup')


class HomeView(ListView):
    model = Product
    template_name = 'home.html'
    context_object_name = 'products'

    def get_queryset(self):
        return Product.objects.all()[:8]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = Category.objects.all()
        context['total_products'] = Product.objects.count()
        context['total_vendors'] = CustomUser.objects.filter(role='VENDOR', vendor_status='APPROVED').count()
        context['total_categories'] = Category.objects.count()
        return context

class ProductDetailView(DetailView):
    model = Product
    template_name = 'product_detail.html'
    context_object_name = 'product'

    def get_object(self, queryset=None):
        return get_object_or_404(Product, id=self.kwargs.get('id'))


class FAQView(ListView):
    model = FAQ
    template_name = 'faq.html'
    context_object_name = 'faqs'
    
    def get_queryset(self):
        return FAQ.objects.filter(is_active=True).order_by('order', '-created_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Group FAQs by category
        faqs_by_category = {}
        categories = [
            ('general', 'General Questions'),
            ('order', 'Orders & Delivery'),
            ('payment', 'Payment'),
            ('vendor', 'Vendor'),
            ('account', 'Account'),
        ]
        
        for cat_value, cat_name in categories:
            faqs_by_category[cat_value] = {
                'name': cat_name,
                'faqs': FAQ.objects.filter(is_active=True, category=cat_value).order_by('order', '-created_at')
            }
        
        context['faqs_by_category'] = faqs_by_category
        return context


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
    from django.http import HttpResponse
    from datetime import datetime
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
    from io import BytesIO
    
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
    from django.http import HttpResponse
    from datetime import datetime
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from io import BytesIO
    
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
    from django.http import HttpResponse
    from datetime import datetime
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from io import BytesIO
    
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
    from django.http import HttpResponse
    from datetime import datetime
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from io import BytesIO
    
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
            order.status = new_status
            order.save()
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
    from django.http import HttpResponse
    from datetime import datetime
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
    from io import BytesIO
    
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
            alignment=TA_RIGHT,
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



@method_decorator(customer_required, name='dispatch')
class CustomerDashboardView(LoginRequiredMixin, ListView):
    model = Product
    template_name = 'customer_dashboard.html'
    context_object_name = 'products'


@method_decorator(customer_required, name='dispatch')
class CustomerProfileUpdateView(LoginRequiredMixin, UpdateView):
    model = CustomUser
    form_class = CustomerProfileForm
    template_name = 'profile_update.html'
    success_url = reverse_lazy('customer_dashboard')

    def get_object(self, queryset=None):
        return self.request.user

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['profile_title'] = 'Customer Profile'
        context['back_url_name'] = 'customer_dashboard'
        return context

    def form_valid(self, form):
        messages.success(self.request, 'Profile updated successfully.')
        return super().form_valid(form)


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



class ProductListView(ListView):
    model = Product
    template_name = 'product_list.html'
    context_object_name = 'products'

    def get_queryset(self):
        queryset = super().get_queryset()
        category_id = self.request.GET.get('category')
        if category_id:
            queryset = queryset.filter(category_id=category_id)
            
        search_query = self.request.GET.get('search')
        if search_query:
            queryset = queryset.filter(name__icontains=search_query)
            
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = Category.objects.all()
        return context



@method_decorator(customer_required, name='dispatch')
class CartView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        cart, created = Cart.objects.get_or_create(user=request.user)
        cart_items = CartItem.objects.filter(cart=cart).select_related('product', 'product__category')
        total_price = sum(item.subtotal for item in cart_items)
        total_items = sum(item.quantity for item in cart_items)
        return render(request, 'cart.html', {
            'cart_items': cart_items,
            'total_price': total_price,
            'total_items': total_items,
        })

@method_decorator(customer_required, name='dispatch')
class AddToCartView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        if not customer_can_purchase(request.user):
            messages.error(request, 'Age verification required. Please update your date of birth in your profile to continue.')
            return redirect('customer_profile')

        product = get_object_or_404(Product, id=self.kwargs['product_id'])

        if product.stock <= 0:
            messages.error(request, f"{product.name} is currently out of stock.")
            return redirect('product_list')

        cart, created = Cart.objects.get_or_create(user=request.user)
        cart_item, created = CartItem.objects.get_or_create(cart=cart, product=product)
        
        if not created:
            if cart_item.quantity >= product.stock:
                messages.warning(request, f"Only {product.stock} unit(s) of {product.name} are available.")
                return redirect('view_cart')
            cart_item.quantity += 1

        if created:
            cart_item.quantity = 1

        cart_item.save()
        messages.success(request, f"{product.name} added to cart.")
        return redirect('view_cart')

@method_decorator(customer_required, name='dispatch')
class UpdateCartView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        cart_item = get_object_or_404(CartItem, id=self.kwargs['item_id'], cart__user=request.user)

        try:
            quantity = int(request.POST.get('quantity', '1'))
        except (TypeError, ValueError):
            messages.error(request, "Invalid quantity provided.")
            return redirect('view_cart')

        if quantity <= 0:
            cart_item.delete()
            messages.info(request, f"{cart_item.product.name} removed from cart.")
            return redirect('view_cart')

        if quantity > cart_item.product.stock:
            cart_item.quantity = cart_item.product.stock
            cart_item.save(update_fields=['quantity'])
            messages.warning(request, f"Quantity adjusted to available stock ({cart_item.product.stock}).")
            return redirect('view_cart')

        cart_item.quantity = quantity
        cart_item.save(update_fields=['quantity'])
        return redirect('view_cart')

@method_decorator(customer_required, name='dispatch')
class RemoveFromCartView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        cart_item = get_object_or_404(CartItem, id=self.kwargs['item_id'], cart__user=request.user)
        cart_item.delete()
        return redirect('view_cart')



@method_decorator(customer_required, name='dispatch')
class CheckoutView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        if not customer_can_purchase(request.user):
            messages.error(request, 'Age verification required before purchasing alcoholic products.')
            return redirect('customer_profile')

        cart = get_object_or_404(Cart, user=request.user)
        cart_items = CartItem.objects.filter(cart=cart).select_related('product')
        
        if not cart_items:
            return redirect('view_cart')
            
        total_price = sum(item.product.price * item.quantity for item in cart_items)
        return render(request, 'checkout.html', {'cart_items': cart_items, 'total_price': total_price})

    def post(self, request, *args, **kwargs):
        if not customer_can_purchase(request.user):
            messages.error(request, 'Age verification required before purchasing alcoholic products.')
            return redirect('customer_profile')

        cart = get_object_or_404(Cart, user=request.user)
        cart_items = CartItem.objects.filter(cart=cart).select_related('product')

        if not cart_items:
            messages.error(request, "Your cart is empty.")
            return redirect('view_cart')

        # Prevent ordering unavailable quantities if stock changed after items were added.
        for item in cart_items:
            if item.product.stock <= 0:
                messages.error(request, f"{item.product.name} is out of stock. Please update your cart.")
                return redirect('view_cart')
            if item.quantity > item.product.stock:
                item.quantity = item.product.stock
                item.save(update_fields=['quantity'])
                messages.warning(request, f"{item.product.name} quantity adjusted to available stock ({item.product.stock}).")
                return redirect('view_cart')
        
        user_lat = request.POST.get('latitude')
        user_lon = request.POST.get('longitude')
        
        if user_lat and user_lon:
            request.user.latitude = float(user_lat)
            request.user.longitude = float(user_lon)
            request.user.save(update_fields=['latitude', 'longitude'])

        shops = CustomUser.objects.filter(role='VENDOR', vendor_status='APPROVED').exclude(latitude__isnull=True, longitude__isnull=True)
        
        nearest_shop = None
        min_distance = float('inf')

        if user_lat and user_lon:
            lat = float(user_lat)
            lon = float(user_lon)
            for shop in shops:
                dist = calculate_distance(lat, lon, shop.latitude, shop.longitude)
                if dist < min_distance:
                    min_distance = dist
                    nearest_shop = shop

        DELIVERY_RADIUS_KM = 25.0
        FEE_PER_KM = 1.50

        if user_lat and user_lon and min_distance > DELIVERY_RADIUS_KM:
            messages.error(request, "Sorry, there are no shops within your delivery radius.")
            return redirect('view_cart')

        delivery_fee = round(min_distance * FEE_PER_KM, 2) if nearest_shop else 0.00

        subtotal = sum(item.product.price * item.quantity for item in cart_items)
        total_price = float(subtotal) + float(delivery_fee)
        
        # Get payment method from form
        payment_method = request.POST.get('payment_method', 'cash')
        if payment_method not in ['cash', 'khalti']:
            payment_method = 'cash'
        
        order = Order.objects.create(
            user=request.user, 
            total_price=total_price,
            delivery_fee=delivery_fee,
            distance_km=round(min_distance, 2) if nearest_shop else None,
            assigned_shop=nearest_shop
        )
        for item in cart_items:
            OrderItem.objects.create(order=order, product=item.product, quantity=item.quantity, price=item.product.price)
            item.product.stock -= item.quantity
            item.product.save(update_fields=['stock'])
        
        # Create payment record
        payment = Payment.objects.create(
            order=order,
            method=payment_method,
            amount=total_price,
            status='pending'
        )
        
        cart.delete()
        
        # Handle payment method - For Khalti, redirect to payment gateway, for Cash just confirm
        if payment_method == 'khalti':
            messages.info(request, "Proceeding to Khalti payment...")
            return redirect('khalti_payment', payment_id=payment.id)
        else:
            # For Cash on Delivery, mark order as Placed immediately
            order.status = 'Placed'
            order.save(update_fields=['status'])
            messages.success(request, f"Order placed! You selected Cash on Delivery. Delivery fee: NPR {delivery_fee}")
            return redirect('order_history')

@method_decorator(customer_required, name='dispatch')
class OrderHistoryView(LoginRequiredMixin, ListView):
    model = Order
    template_name = 'order_history.html'
    context_object_name = 'orders'

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).order_by('-created_at')


# =====================================
# KHALTI PAYMENT INTEGRATION VIEWS
# =====================================

@method_decorator(customer_required, name='dispatch')
class KhaltiPaymentView(LoginRequiredMixin, View):
    """Initiate Khalti payment for an order"""
    
    def get(self, request, payment_id, *args, **kwargs):
        payment = get_object_or_404(Payment, id=payment_id, order__user=request.user)
        order = payment.order
        
        # Prepare Khalti API request
        khalti_secret_key = settings.KHALTI_SECRET_KEY
        khalti_base_url = settings.KHALTI_BASE_URL
        
        # Build the return URL (where Khalti will redirect after payment)
        return_url = request.build_absolute_uri(reverse('khalti_verify'))
        
        payload = {
            "return_url": return_url,
            "website_url": request.build_absolute_uri('/'),
            "amount": int(order.total_price * 100),  # Convert NPR to paisa (cents)
            "purchase_order_id": str(order.id),
            "purchase_order_name": f"Order #{order.id}",
        }
        
        headers = {
            "Authorization": f"Key {khalti_secret_key}",
            "Content-Type": "application/json",
        }
        
        try:
            response = requests.post(
                khalti_base_url + "initiate/",
                json=payload,
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            # Store the pidx for later verification
            payment.pidx = data.get("pidx")
            payment.save()
            
            # Redirect to Khalti payment page
            payment_url = data.get("payment_url")
            if payment_url:
                return redirect(payment_url)
            else:
                messages.error(request, "Failed to initiate payment. Please try again.")
                return redirect('order_history')
                
        except requests.exceptions.RequestException as e:
            messages.error(request, f"Payment initiation failed: {str(e)}")
            return redirect('order_history')


@method_decorator(customer_required, name='dispatch')
class KhaltiVerifyView(LoginRequiredMixin, View):
    """Verify Khalti payment after user returns from Khalti"""
    
    def get(self, request, *args, **kwargs):
        pidx = request.GET.get("pidx")
        
        if not pidx:
            messages.error(request, "Invalid payment request.")
            return redirect('order_history')
        
        payment = get_object_or_404(Payment, pidx=pidx, order__user=request.user)
        order = payment.order
        
        khalti_secret_key = settings.KHALTI_SECRET_KEY
        khalti_base_url = settings.KHALTI_BASE_URL
        
        payload = {
            "pidx": pidx
        }
        
        headers = {
            "Authorization": f"Key {khalti_secret_key}",
            "Content-Type": "application/json",
        }
        
        try:
            response = requests.post(
                khalti_base_url + "lookup/",
                json=payload,
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            # Check payment status
            if data.get("status") == "Completed":
                payment.status = "paid"
                payment.transaction_id = data.get("transaction_id")
                payment.paid_at = now()
                payment.save()
                
                # Mark order as Placed when payment is successful
                order.status = 'Placed'
                order.save(update_fields=['status'])
                
                messages.success(
                    request, 
                    f"Payment successful! Order #{order.id} has been placed. Khalti will process the payment within 24 hours."
                )
                return redirect('order_history')
            else:
                payment.status = "pending"
                payment.save()
                messages.warning(request, "Payment is pending. Please check your order status later.")
                return redirect('order_history')
                
        except requests.exceptions.RequestException as e:
            messages.error(request, f"Payment verification failed: {str(e)}")
            return redirect('order_history')
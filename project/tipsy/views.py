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
    CustomerProfileForm,
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
from .decorators import customer_required
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
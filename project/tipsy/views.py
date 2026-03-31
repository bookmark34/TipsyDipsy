from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.tokens import default_token_generator
from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from .forms import SignUpForm, LoginForm, ProductForm
from .models import CustomUser, Product, Category, Cart, CartItem, Order, OrderItem
from django.views import View
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse_lazy, reverse
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils.decorators import method_decorator
from .decorators import vendor_required, customer_required, admin_required


class SignUpView(CreateView):
    form_class = SignUpForm
    template_name = 'signup.html'
    success_url = reverse_lazy('home')

    def form_valid(self, form):
        user = form.save()
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


@method_decorator(admin_required, name='dispatch')
class AdminDashboardView(LoginRequiredMixin, View):
    template_name = 'Admin/AdminDashboard.html'

    def get(self, request, *args, **kwargs):
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
        }
        return render(request, self.template_name, context)


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



@method_decorator(vendor_required, name='dispatch')
class VendorDashboardView(LoginRequiredMixin, ListView):
    model = Product
    template_name = 'vendor_dashboard.html'
    context_object_name = 'products'

    def get_queryset(self):
        return Product.objects.filter(vendor=self.request.user)


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

        return render(request, 'vendor_orders.html', {
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
        return render(request, 'vendor_new_orders.html', context)


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
        return render(request, 'vendor_orders_to_deliver.html', context)


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
        return render(request, 'vendor_delivered_orders.html', context)


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
        cart_items = CartItem.objects.filter(cart=cart)
        total_price = sum(item.subtotal for item in cart_items)
        return render(request, 'cart.html', {'cart_items': cart_items, 'total_price': total_price})

@method_decorator(customer_required, name='dispatch')
class AddToCartView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        product = get_object_or_404(Product, id=self.kwargs['product_id'])
        cart, created = Cart.objects.get_or_create(user=request.user)
        cart_item, created = CartItem.objects.get_or_create(cart=cart, product=product)
        
        if not created:
            cart_item.quantity += 1
        cart_item.save()
        return redirect('view_cart')

@method_decorator(customer_required, name='dispatch')
class UpdateCartView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        cart_item = get_object_or_404(CartItem, id=self.kwargs['item_id'], cart__user=request.user)
        quantity = int(request.POST.get('quantity'))
        if quantity > 0:
            cart_item.quantity = quantity
            cart_item.save()
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
        cart = get_object_or_404(Cart, user=request.user)
        cart_items = CartItem.objects.filter(cart=cart)
        
        if not cart_items:
            return redirect('view_cart')
            
        total_price = sum(item.product.price * item.quantity for item in cart_items)
        return render(request, 'checkout.html', {'cart_items': cart_items, 'total_price': total_price})

    def post(self, request, *args, **kwargs):
        cart = get_object_or_404(Cart, user=request.user)
        cart_items = CartItem.objects.filter(cart=cart)
        total_price = sum(item.product.price * item.quantity for item in cart_items)
        
        order = Order.objects.create(user=request.user, total_price=total_price)
        for item in cart_items:
            OrderItem.objects.create(order=order, product=item.product, quantity=item.quantity, price=item.product.price)
            item.product.stock -= item.quantity
            item.product.save()
        cart.delete()
        return redirect('order_history')

@method_decorator(customer_required, name='dispatch')
class OrderHistoryView(LoginRequiredMixin, ListView):
    model = Order
    template_name = 'order_history.html'
    context_object_name = 'orders'

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).order_by('-created_at')

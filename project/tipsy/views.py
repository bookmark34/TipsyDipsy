from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .forms import SignUpForm, LoginForm, ProductForm
from .models import CustomUser, Product, Category, Cart, CartItem, Order, OrderItem
from django.views import View
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils.decorators import method_decorator
from .decorators import vendor_required, customer_required


class SignUpView(CreateView):
    form_class = SignUpForm
    template_name = 'signup.html'
    success_url = reverse_lazy('home')

    def form_valid(self, form):
        user = form.save()
        login(self.request, user)
        if user.is_vendor():
            return redirect('vendor_dashboard')
        else:
            return redirect('customer_dashboard')

class UserLoginView(LoginView):
    form_class = LoginForm
    template_name = 'login.html'

    def get_success_url(self):
        user = self.request.user
        if user.is_vendor():
            return reverse_lazy('vendor_dashboard')
        else:
            return reverse_lazy('customer_dashboard')

class UserLogoutView(LogoutView):
    next_page = reverse_lazy('home')



class HomeView(ListView):
    model = Product
    template_name = 'home.html'
    context_object_name = 'products'

    def get_queryset(self):
        return Product.objects.all()[:8]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = Category.objects.all()
        return context

class ProductDetailView(DetailView):
    model = Product
    template_name = 'product_detail.html'
    context_object_name = 'product'

    def get_object(self, queryset=None):
        return get_object_or_404(Product, id=self.kwargs.get('id'))



@method_decorator(vendor_required, name='dispatch')
class VendorDashboardView(LoginRequiredMixin, ListView):
    model = Product
    template_name = 'vendor_dashboard.html'
    context_object_name = 'products'

    def get_queryset(self):
        return Product.objects.filter(vendor=self.request.user)

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

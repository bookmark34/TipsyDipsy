from django.urls import path
from .views import (
    HomeView, ProductListView, ProductDetailView,
    SignUpView, UserLoginView, UserLogoutView,
    VendorDashboardView, ProductCreateView, ProductUpdateView, ProductDeleteView,
    CustomerDashboardView,
    CartView, AddToCartView, UpdateCartView, RemoveFromCartView,
    CheckoutView, OrderHistoryView
)

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    path("signup/", SignUpView.as_view(), name="signup"),
    path("login/", UserLoginView.as_view(), name="login"),
    path("logout/", UserLogoutView.as_view(), name="logout"),
    
    # Vendor URLs
    path("vendor/dashboard/", VendorDashboardView.as_view(), name="vendor_dashboard"),
    path("vendor/product/add/", ProductCreateView.as_view(), name="add_product"),
    path("vendor/product/<int:pk>/edit/", ProductUpdateView.as_view(), name="edit_product"),
    path("vendor/product/<int:pk>/delete/", ProductDeleteView.as_view(), name="delete_product"),
    
    # Customer URLs
    path("shop/", CustomerDashboardView.as_view(), name="customer_dashboard"),
    path("products/", ProductListView.as_view(), name="product_list"),
    path("products/<int:id>/", ProductDetailView.as_view(), name="product_detail"),
    path("cart/add/<int:product_id>/", AddToCartView.as_view(), name="add_to_cart"),
    path("cart/", CartView.as_view(), name="view_cart"),
    path("cart/update/<int:item_id>/", UpdateCartView.as_view(), name="update_cart"),
    path("cart/remove/<int:item_id>/", RemoveFromCartView.as_view(), name="remove_from_cart"),
    path("checkout/", CheckoutView.as_view(), name="checkout"),
    path("orders/", OrderHistoryView.as_view(), name="order_history"),
]
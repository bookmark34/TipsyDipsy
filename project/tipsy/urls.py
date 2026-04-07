from django.urls import path
from .views import (
    HomeView, ProductListView, ProductDetailView,
    SignUpView, UserLoginView, UserLogoutView, EmailVerificationView,
    AdminDashboardView, AdminVendorsView, AdminApproveVendorView, AdminRejectVendorView, AdminRemoveVendorView,
    admin_export_report_pdf,
    AdminProductsView, AdminOrdersView, AdminCustomersView,
    VendorDashboardView, VendorOrdersView, VendorUpdateOrderStatusView,
    VendorNewOrdersView, VendorOrdersToDeliverView, VendorDeliveredOrdersView,
    ProductCreateView, ProductUpdateView, ProductDeleteView,
    CustomerDashboardView,
    CartView, AddToCartView, UpdateCartView, RemoveFromCartView,
    CheckoutView, OrderHistoryView, vendor_export_report
)

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    path("signup/", SignUpView.as_view(), name="signup"),
    path("login/", UserLoginView.as_view(), name="login"),
    path("logout/", UserLogoutView.as_view(), name="logout"),
    path("verify-email/<uidb64>/<token>/", EmailVerificationView.as_view(), name="verify_email"),

    # Custom Admin URLs
    path("control/dashboard/", AdminDashboardView.as_view(), name="admin_dashboard"),
    path("control/dashboard/export-pdf/", admin_export_report_pdf, name="admin_export_report_pdf"),
    path("control/vendors/", AdminVendorsView.as_view(), name="admin_vendors"),
    path("control/vendors/<int:user_id>/approve/", AdminApproveVendorView.as_view(), name="admin_approve_vendor"),
    path("control/vendors/<int:user_id>/reject/", AdminRejectVendorView.as_view(), name="admin_reject_vendor"),
    path("control/vendors/<int:user_id>/remove/", AdminRemoveVendorView.as_view(), name="admin_remove_vendor"),
    path("control/products/", AdminProductsView.as_view(), name="admin_products"),
    path("control/orders/", AdminOrdersView.as_view(), name="admin_orders"),
    path("control/customers/", AdminCustomersView.as_view(), name="admin_customers"),
    
    # Vendor URLs
    path("vendor/dashboard/", VendorDashboardView.as_view(), name="vendor_dashboard"),
    path("vendor/export-report/", vendor_export_report, name="vendor_export_report"),
    path("vendor/product/add/", ProductCreateView.as_view(), name="add_product"),
    path("vendor/product/<int:pk>/edit/", ProductUpdateView.as_view(), name="edit_product"),
    path("vendor/product/<int:pk>/delete/", ProductDeleteView.as_view(), name="delete_product"),
    path("vendor/orders/", VendorOrdersView.as_view(), name="vendor_orders"),
    path("vendor/orders/new/", VendorNewOrdersView.as_view(), name="vendor_new_orders"),
    path("vendor/orders/to-deliver/", VendorOrdersToDeliverView.as_view(), name="vendor_orders_to_deliver"),
    path("vendor/orders/delivered/", VendorDeliveredOrdersView.as_view(), name="vendor_delivered_orders"),
    path("vendor/orders/<int:order_id>/status/", VendorUpdateOrderStatusView.as_view(), name="vendor_update_order_status"),
    
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
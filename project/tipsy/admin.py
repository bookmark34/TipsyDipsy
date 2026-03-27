from django.contrib import admin
from .models import CustomUser, Product

@admin.register(CustomUser)
class CustomUserAdmin(admin.ModelAdmin):
    list_display = ('username', 'email', 'role', 'vendor_status', 'first_name', 'last_name')
    list_filter = ('role', 'vendor_status', 'date_joined')
    search_fields = ('username', 'email', 'first_name', 'last_name')
    actions = ('approve_vendors', 'reject_vendors')

    @admin.action(description='Approve selected vendor accounts')
    def approve_vendors(self, request, queryset):
        updated = queryset.filter(role='VENDOR').update(vendor_status='APPROVED')
        self.message_user(request, f"{updated} vendor account(s) approved.")

    @admin.action(description='Reject selected vendor accounts')
    def reject_vendors(self, request, queryset):
        updated = queryset.filter(role='VENDOR').update(vendor_status='REJECTED')
        self.message_user(request, f"{updated} vendor account(s) rejected.")

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'vendor', 'price', 'stock', 'created_at')
    list_filter = ('vendor', 'created_at')
    search_fields = ('name', 'description', 'vendor__username')

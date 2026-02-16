from django.contrib import admin
from .models import CustomUser, Product

@admin.register(CustomUser)
class CustomUserAdmin(admin.ModelAdmin):
    list_display = ('username', 'email', 'role', 'first_name', 'last_name')
    list_filter = ('role', 'date_joined')
    search_fields = ('username', 'email', 'first_name', 'last_name')

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'vendor', 'price', 'stock', 'created_at')
    list_filter = ('vendor', 'created_at')
    search_fields = ('name', 'description', 'vendor__username')

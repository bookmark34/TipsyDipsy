from django.db import models
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import UserManager
from datetime import date


class CustomUserManager(UserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields['role'] = 'ADMIN'
        return super().create_superuser(username, email=email, password=password, **extra_fields)

class CustomUser(AbstractUser):
    ROLE_CHOICES = [
        ('VENDOR', 'Vendor'),
        ('CUSTOMER', 'Customer'),
        ('ADMIN', 'Admin'),
    ]

    VENDOR_STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
    ]
    
    address = models.CharField(max_length=255, blank=True, null=True)
    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='CUSTOMER')
    vendor_status = models.CharField(max_length=10, choices=VENDOR_STATUS_CHOICES, default='PENDING')
    email_verified = models.BooleanField(default=False)
    email_verification_token = models.CharField(max_length=255, blank=True, null=True)
    latitude = models.FloatField(null=True, blank=True, help_text="Latitude for location-based delivery")
    longitude = models.FloatField(null=True, blank=True, help_text="Longitude for location-based delivery")
    business_name = models.CharField(max_length=255, blank=True, null=True, help_text="Business Name for Vendors")
    pan_number = models.CharField(max_length=20, blank=True, null=True, help_text="PAN Number for Vendors")
    tax_document = models.FileField(upload_to='vendor_documents/', blank=True, null=True, help_text="Tax Clearance Certificate Upload")
    pan_document = models.FileField(upload_to='vendor_documents/', blank=True, null=True, help_text="PAN Document Upload")
    date_of_birth = models.DateField(blank=True, null=True)
    objects = CustomUserManager()
    
    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"
    
    def is_vendor(self):
        return self.role == 'VENDOR'
    
    def is_customer(self):
        return self.role == 'CUSTOMER'

    def is_admin(self):
        return self.role == 'ADMIN' or self.is_superuser

    def is_approved_vendor(self):
        return self.is_vendor() and self.vendor_status == 'APPROVED'

    def get_age(self):
        if not self.date_of_birth:
            return None
        today = date.today()
        return today.year - self.date_of_birth.year - (
            (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
        )

    def is_age_verified(self, minimum_age=18):
        age = self.get_age()
        return age is not None and age >= minimum_age


class Category(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Categories"

class Product(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, null=True, blank=True)
    image = models.ImageField(upload_to='products/', blank=True, null=True)
    stock = models.IntegerField(default=0)
    vendor = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Cart(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.IntegerField(default=1)

    @property
    def subtotal(self):
        return self.product.price * self.quantity

class Order(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    delivery_fee = models.DecimalField(max_digits=6, decimal_places=2, default=0.00)
    distance_km = models.FloatField(null=True, blank=True, help_text="Distance from selected shop in km")
    assigned_shop = models.ForeignKey('CustomUser', on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_orders', help_text="The closest vendor matching this order")
    status = models.CharField(max_length=20, choices=[('Pending', 'Pending'), ('Placed', 'Placed'), ('Confirmed', 'Confirmed'), ('Delivered', 'Delivered')], default='Pending')
    created_at = models.DateTimeField(auto_now_add=True)

class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.IntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)

    @property
    def subtotal(self):
        return self.price * self.quantity


class FAQ(models.Model):
    question = models.CharField(max_length=500)
    answer = models.TextField()
    category = models.CharField(
        max_length=50,
        choices=[
            ('general', 'General'),
            ('order', 'Orders & Delivery'),
            ('payment', 'Payment'),
            ('vendor', 'Vendor'),
            ('account', 'Account'),
        ],
        default='general'
    )
    is_active = models.BooleanField(default=True)
    order = models.IntegerField(default=0, help_text="Order of display")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', '-created_at']
        verbose_name = "FAQ"
        verbose_name_plural = "FAQs"

    def __str__(self):
        return self.question

class Payment(models.Model):

    PAYMENT_METHOD_CHOICES = [
        ("cash", "Cash"),
        ("khalti", "Khalti"),
    ]

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("paid", "Paid"),

    ]

    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="payment")

    method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)

    amount = models.DecimalField(max_digits=10, decimal_places=2)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")

    pidx = models.CharField(max_length=100, blank=True, null=True)
    
    transaction_id = models.CharField(max_length=100, blank=True, null=True)

    paid_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"Payment for Order {self.order.id}"
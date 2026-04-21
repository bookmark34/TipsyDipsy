from django.db import models
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import UserManager
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
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


class Feedback(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='feedbacks')
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='feedbacks')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='feedbacks')

    rating = models.IntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="Optional rating from 1 to 5",
    )
    comment = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'order', 'product'], name='unique_feedback_per_user_order_product')
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"Feedback by {self.user.username} for Order #{self.order_id} - {self.product.name}"

    def clean(self):
        super().clean()

        normalized_comment = (self.comment or '').strip()

        if self.rating is None and not normalized_comment:
            raise ValidationError("Please provide at least a rating or a comment.")

        if self.rating is not None and not (1 <= int(self.rating) <= 5):
            raise ValidationError({'rating': "Rating must be between 1 and 5."})

        # Store stripped comment so blank-only comments don't pass validation
        self.comment = normalized_comment or None

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

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


class Notification(models.Model):
    """Store notifications for customers and vendors (orders + chat)."""
    
    NOTIFICATION_TYPES = [
        ('order_confirmed', 'Order Confirmed'),
        ('order_shipped', 'Order Shipped'),
        ('order_delivered', 'Order Delivered'),
        ('order_pending', 'Order Pending'),
        ('vendor_new_order', 'New Order Received'),
        ('vendor_order_cancelled', 'Order Cancelled'),
        ('chat_message', 'Chat Message'),
    ]
    
    # Recipient of the notification
    recipient = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='notifications')
    
    # Related order (optional for non-order notifications)
    order = models.ForeignKey(Order, on_delete=models.SET_NULL, related_name='notifications', null=True, blank=True)

    # Related chat (optional for non-chat notifications)
    chat = models.ForeignKey('Chat', on_delete=models.SET_NULL, related_name='notifications', null=True, blank=True)
    
    # Notification type
    notification_type = models.CharField(max_length=30, choices=NOTIFICATION_TYPES)
    
    # Message content
    title = models.CharField(max_length=255)
    message = models.TextField()
    
    # Read status
    is_read = models.BooleanField(default=False)
    
    # Timestamp
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(blank=True, null=True)
    
    class Meta:
        ordering = ['-created_at']
        
    def __str__(self):
        return f"Notification for {self.recipient.username} - {self.title}"
    
    def mark_as_read(self):
        """Mark notification as read"""
        if not self.is_read:
            from django.utils import timezone
            self.is_read = True
            self.read_at = timezone.now()
            self.save()

class Chat(models.Model):
    customer = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='customer_chats')
    vendor = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='vendor_chats')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('customer', 'vendor')
        ordering = ['-updated_at']

    def __str__(self):
        return f"Chat between {self.customer.username} and {self.vendor.username}"

class Message(models.Model):
    chat = models.ForeignKey(Chat, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"Message by {self.sender.username} at {self.timestamp}"

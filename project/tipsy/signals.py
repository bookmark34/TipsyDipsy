from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from .models import Order, Notification, OrderItem, CustomUser


@receiver(pre_save, sender=Order)
def track_order_status_change(sender, instance, **kwargs):
    """Track the old status before saving"""
    try:
        old_instance = Order.objects.get(pk=instance.pk)
        instance._old_status = old_instance.status
    except Order.DoesNotExist:
        instance._old_status = None


@receiver(post_save, sender=Order)
def create_order_notifications(sender, instance, created, **kwargs):
    """Create notifications when order status changes"""
    
    # Skip if order was just created (status is 'Pending' by default)
    if created:
        return
    
    # Get the old status
    old_status = getattr(instance, '_old_status', None)
    new_status = instance.status
    
    # Only proceed if status actually changed
    if old_status == new_status:
        return
    
    # Determine notification type and message based on status change
    notification_data = {}
    
    if new_status == 'Confirmed':
        notification_data = {
            'customer_type': 'order_confirmed',
            'customer_title': 'Order Confirmed!',
            'customer_msg': f'Your order #{instance.id} has been confirmed by the vendor.',
            'vendor_type': None,  # No vendor notification for this
        }
    elif new_status == 'Placed':
        notification_data = {
            'customer_type': None,
            'customer_msg': None,
            'vendor_type': 'vendor_new_order',
            'vendor_title': 'New Order Received',
            'vendor_msg': f'You have received a new order #{instance.id}.',
        }
    elif new_status == 'Delivered':
        notification_data = {
            'customer_type': 'order_delivered',
            'customer_title': 'Order Delivered!',
            'customer_msg': f'Your order #{instance.id} has been delivered.',
            'vendor_type': None,
        }
    
    # Create customer notification
    if notification_data.get('customer_type'):
        Notification.objects.create(
            recipient=instance.user,  # Customer
            order=instance,
            notification_type=notification_data['customer_type'],
            title=notification_data.get('customer_title', 'Order Update'),
            message=notification_data.get('customer_msg', f'Order #{instance.id} status updated to {new_status}.'),
        )
    
    # Create vendor notifications
    if notification_data.get('vendor_type'):
        # Get all vendors who have products in this order
        vendors = CustomUser.objects.filter(
            product__orderitem__order=instance
        ).distinct()
        
        for vendor in vendors:
            Notification.objects.create(
                recipient=vendor,
                order=instance,
                notification_type=notification_data['vendor_type'],
                title=notification_data.get('vendor_title', 'Order Update'),
                message=notification_data.get('vendor_msg', f'Order #{instance.id} status updated to {new_status}.'),
            )

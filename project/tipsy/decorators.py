from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import redirect

def role_required(role):
    def decorator(view_func):
        return user_passes_test(lambda u: u.is_authenticated and u.role == role, login_url='login')(view_func)
    return decorator

vendor_required = role_required('VENDOR')
customer_required = role_required('CUSTOMER')

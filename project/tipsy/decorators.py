from functools import wraps
from django.contrib.auth import logout
from django.shortcuts import redirect

def role_required(role):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            user = request.user

            if not user.is_authenticated:
                return redirect('login')

            if role == 'VENDOR':
                allowed = user.role == role and user.vendor_status == 'APPROVED'
            elif role == 'ADMIN':
                allowed = user.role == role or user.is_superuser
            else:
                allowed = user.role == role

            if not allowed:
                logout(request)
                return redirect('login')

            return view_func(request, *args, **kwargs)

        return _wrapped_view
    return decorator

vendor_required = role_required('VENDOR')
customer_required = role_required('CUSTOMER')
admin_required = role_required('ADMIN')

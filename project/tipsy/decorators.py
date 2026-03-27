from django.contrib.auth.decorators import user_passes_test

def role_required(role):
    def decorator(view_func):
        if role == 'VENDOR':
            return user_passes_test(
                lambda u: u.is_authenticated and u.role == role and u.vendor_status == 'APPROVED',
                login_url='login'
            )(view_func)

        if role == 'ADMIN':
            return user_passes_test(
                lambda u: u.is_authenticated and (u.role == role or u.is_superuser),
                login_url='login'
            )(view_func)

        return user_passes_test(
            lambda u: u.is_authenticated and u.role == role,
            login_url='login'
        )(view_func)
    return decorator

vendor_required = role_required('VENDOR')
customer_required = role_required('CUSTOMER')
admin_required = role_required('ADMIN')

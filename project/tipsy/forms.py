from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.password_validation import validate_password
from .models import CustomUser, Product
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import authenticate
from datetime import date


class SignUpForm(UserCreationForm):
    SIGNUP_ROLE_CHOICES = [
        ('VENDOR', 'Vendor'),
        ('CUSTOMER', 'Customer'),
    ]

    email = forms.EmailField(required=True)
    address = forms.CharField(max_length=255, required=False)
    phone_number = forms.CharField(max_length=15, required=False)
    date_of_birth = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
        label='Date of Birth (For Customers)'
    )
    business_name = forms.CharField(max_length=255, required=False, label="Business Name (For Vendors)")
    pan_number = forms.CharField(max_length=20, required=False, label="PAN Number (For Vendors)")
    pan_document = forms.FileField(required=False, label="PAN Document (For Vendors)")
    tax_document = forms.FileField(required=False, label="Tax Clearance Certificate (For Vendors)")
    role = forms.ChoiceField(
        choices=SIGNUP_ROLE_CHOICES,
        widget=forms.RadioSelect,
        required=True,
        label="What are you signing up as?"
    )
    
    class Meta:
        model = CustomUser
        fields = ('username', 'first_name', 'last_name', 'email', 'address', 'phone_number', 'date_of_birth', 'business_name', 'pan_number', 'pan_document', 'tax_document', 'role')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["first_name"].widget.attrs["autofocus"] = "autofocus"
        for f in self.fields.values():
            if f.widget.__class__.__name__ != 'RadioSelect':
                f.widget.attrs["class"] = "form-control"

    def clean(self):
        cleaned_data = super().clean()
        role = cleaned_data.get('role')
        business_name = cleaned_data.get('business_name')
        pan_number = cleaned_data.get('pan_number')
        pan_document = cleaned_data.get('pan_document')
        tax_document = cleaned_data.get('tax_document')
        date_of_birth = cleaned_data.get('date_of_birth')

        if role == 'CUSTOMER':
            if not date_of_birth:
                self.add_error('date_of_birth', 'Date of Birth is required for customers.')
            else:
                today = date.today()
                age = today.year - date_of_birth.year - (
                    (today.month, today.day) < (date_of_birth.month, date_of_birth.day)
                )
                if age < 18:
                    self.add_error('date_of_birth', 'You must be at least 18 years old to register as a customer.')

        if role == 'VENDOR':
            if not business_name:
                self.add_error('business_name', 'Business Name is required for Vendors.')
            if not pan_number:
                self.add_error('pan_number', 'PAN Number is required for Vendors.')
            if not pan_document:
                self.add_error('pan_document', 'PAN Document is required for Vendors.')
            if not tax_document:
                self.add_error('tax_document', 'Tax Clearance Certificate is required for Vendors.')
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.phone_number = self.cleaned_data['phone_number']
        user.address = self.cleaned_data["address"]
        user.role = self.cleaned_data['role']
        user.date_of_birth = self.cleaned_data.get('date_of_birth')
        if self.cleaned_data.get('business_name'):
            user.business_name = self.cleaned_data['business_name']
        if self.cleaned_data.get('pan_number'):
            user.pan_number = self.cleaned_data['pan_number']
        if self.cleaned_data.get('pan_document'):
            user.pan_document = self.cleaned_data['pan_document'] 
        if self.cleaned_data.get('tax_document'):
            user.tax_document = self.cleaned_data['tax_document']
        if commit:
            user.save()
        return user

    def clean_role(self):
        role = self.cleaned_data.get('role')
        allowed_roles = {choice[0] for choice in self.SIGNUP_ROLE_CHOICES}
        if role not in allowed_roles:
            raise forms.ValidationError('Invalid role selection.')
        return role

    
class LoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.widget.attrs["class"] = "form-control"

    def clean(self):
        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')

        if username is not None and password:
            # Authenticate the user
            self.user_cache = authenticate(
                self.request,
                username=username,
                password=password
            )
            
            if self.user_cache is None:
                # Authentication failed - either invalid username or password
                raise forms.ValidationError(
                    "Invalid username or password. Please check your credentials and try again.",
                    code='invalid_login',
                )
            else:
                # User authenticated successfully, check if allowed to login
                self.confirm_login_allowed(self.user_cache)
        return self.cleaned_data


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['name', 'description', 'price', 'stock', 'image', 'category']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.widget.attrs["class"] = "form-control"


class AdminSetUserPasswordForm(forms.Form):
    new_password1 = forms.CharField(
        label='New Password',
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'autocomplete': 'new-password'}),
    )
    new_password2 = forms.CharField(
        label='Confirm New Password',
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'autocomplete': 'new-password'}),
    )

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_new_password1(self):
        password1 = self.cleaned_data.get('new_password1')
        if password1:
            validate_password(password1, self.user)
        return password1

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('new_password1')
        password2 = cleaned_data.get('new_password2')

        if password1 and password2 and password1 != password2:
            self.add_error('new_password2', 'The two password fields did not match.')

        return cleaned_data


class CustomerProfileForm(forms.ModelForm):
    class Meta:
        model = CustomUser
        fields = ['first_name', 'last_name', 'email', 'phone_number', 'address', 'date_of_birth']
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name != 'date_of_birth':
                field.widget.attrs['class'] = 'form-control'


class VendorProfileForm(forms.ModelForm):
    class Meta:
        model = CustomUser
        fields = [
            'first_name',
            'last_name',
            'email',
            'phone_number',
            'address',
            'business_name',
            'pan_number',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control'
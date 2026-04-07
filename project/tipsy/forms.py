from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import CustomUser, Product
from django.contrib.auth.forms import AuthenticationForm


class SignUpForm(UserCreationForm):
    SIGNUP_ROLE_CHOICES = [
        ('VENDOR', 'Vendor'),
        ('CUSTOMER', 'Customer'),
    ]

    email = forms.EmailField(required=True)
    address = forms.CharField(max_length=255, required=False)
    phone_number = forms.CharField(max_length=15, required=False)
    pan_number = forms.CharField(max_length=20, required=False, label="PAN Number (For Vendors)")
    pan_document = forms.FileField(required=False, label="PAN Document (For Vendors)")
    role = forms.ChoiceField(
        choices=SIGNUP_ROLE_CHOICES,
        widget=forms.RadioSelect,
        required=True,
        label="What are you signing up as?"
    )
    
    class Meta:
        model = CustomUser
        fields = ('username', 'first_name', 'last_name', 'email', 'address', 'phone_number', 'pan_number', 'pan_document', 'role')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["first_name"].widget.attrs["autofocus"] = "autofocus"
        for f in self.fields.values():
            if f.widget.__class__.__name__ != 'RadioSelect':
                f.widget.attrs["class"] = "form-control"

    def clean(self):
        cleaned_data = super().clean()
        role = cleaned_data.get('role')
        pan_number = cleaned_data.get('pan_number')
        pan_document = cleaned_data.get('pan_document')

        if role == 'VENDOR':
            if not pan_number:
                self.add_error('pan_number', 'PAN Number is required for Vendors.')
            if not pan_document:
                self.add_error('pan_document', 'PAN Document is required for Vendors.')
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.phone_number = self.cleaned_data['phone_number']
        user.address = self.cleaned_data["address"]
        user.role = self.cleaned_data['role']
        if self.cleaned_data.get('pan_number'):
            user.pan_number = self.cleaned_data['pan_number']
        if self.cleaned_data.get('pan_document'):
            user.pan_document = self.cleaned_data['pan_document']
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


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['name', 'description', 'price', 'stock', 'image', 'category']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.widget.attrs["class"] = "form-control"
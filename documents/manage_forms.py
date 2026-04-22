from django import forms
from django.contrib.auth.password_validation import validate_password

from accounts.models import User
from documents.models import Company, LetterTemplate


class UserCreateForm(forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
        validators=[validate_password],
    )
    confirm_password = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
    )

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "role", "department", "is_active"]
        widgets = {
            "username": forms.TextInput(attrs={"class": "form-control"}),
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "role": forms.Select(attrs={"class": "form-select"}),
            "department": forms.TextInput(attrs={"class": "form-control"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("password") != cleaned.get("confirm_password"):
            self.add_error("confirm_password", "Passwords do not match.")
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
        if commit:
            user.save()
        return user


class UserEditForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "role", "department", "is_active"]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "role": forms.Select(attrs={"class": "form-select"}),
            "department": forms.TextInput(attrs={"class": "form-control"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class CompanyForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = [
            "name", "short_name", "registered_address", "cin", "gstin",
            "logo", "signatory_name", "signatory_designation", "is_active",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "short_name": forms.TextInput(attrs={"class": "form-control"}),
            "registered_address": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "cin": forms.TextInput(attrs={"class": "form-control"}),
            "gstin": forms.TextInput(attrs={"class": "form-control"}),
            "logo": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "signatory_name": forms.TextInput(attrs={"class": "form-control"}),
            "signatory_designation": forms.TextInput(attrs={"class": "form-control"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class LetterTemplateCreateForm(forms.ModelForm):
    extra_variables_schema = forms.JSONField(
        required=False,
        initial=dict,
        widget=forms.Textarea(attrs={"class": "form-control font-monospace", "rows": 6}),
        help_text='JSON dict of template-specific fields. Example: {"field_name": {"type": "text", "label": "Label", "required": true}}',
    )

    class Meta:
        model = LetterTemplate
        fields = ["name", "html_content", "extra_variables_schema", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={
                "class": "form-control",
                "list": "template-name-suggestions",
                "placeholder": "e.g. Offer Letter, Promotion Letter…",
                "autocomplete": "off",
            }),
            "html_content": forms.Textarea(attrs={"class": "form-control font-monospace", "rows": 20}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
        help_texts = {
            "html_content": "Use Django template syntax. Variables: {{ company }}, {{ employee }}, {{ issue_date }}, etc.",
        }

    def clean_extra_variables_schema(self):
        value = self.cleaned_data.get("extra_variables_schema")
        return value if value is not None else {}

from django import forms
from documents.models import Company, LetterTemplate


class GenerateDocumentForm(forms.Form):
    """
    Top-level document generation form.
    Dynamic per-template fields are rendered via HTMX partials —
    they are NOT defined here but are collected from POST in the view.
    """
    company = forms.ModelChoiceField(
        queryset=Company.objects.filter(is_active=True),
        empty_label="— Select Company —",
        widget=forms.Select(attrs={
            "class": "form-select",
            "id": "id_company",
            # On company change: refresh employee search scope
            "hx-get": "",
            "hx-trigger": "change",
        }),
    )
    template = forms.ModelChoiceField(
        queryset=LetterTemplate.objects.filter(is_active=True),
        empty_label="— Select Template Type —",
        widget=forms.Select(attrs={
            "class": "form-select",
            "id": "id_template",
        }),
    )
    # Hidden — set by the HTMX employee autocomplete widget
    employee_id = forms.UUIDField(
        widget=forms.HiddenInput(attrs={"id": "id_employee_id"}),
        required=False,
    )
    # Visible display-only field for the selected employee name
    employee_name = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "id": "id_employee_name",
            "placeholder": "Type name or employee code to search…",
            "autocomplete": "off",
            "hx-get": "/documents/api/employees/",
            "hx-trigger": "keyup changed delay:300ms",
            "hx-target": "#employee-results",
            "hx-include": "#id_company",
        }),
    )


class VoidDocumentForm(forms.Form):
    reason = forms.CharField(
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "rows": 3,
            "placeholder": "Required: explain why this document is being voided…",
        }),
        min_length=10,
        error_messages={"min_length": "Please provide at least 10 characters for the reason."},
    )

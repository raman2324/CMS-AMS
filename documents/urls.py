from django.urls import path
from documents import views, manage_views

app_name = "documents"

urlpatterns = [
    # Main views
    path("", views.DocumentListView.as_view(), name="list"),
    path("audit/", views.AuditLogView.as_view(), name="audit"),
    path("generate/", views.GenerateDocumentView.as_view(), name="generate"),
    path("<uuid:pk>/", views.DocumentDetailView.as_view(), name="detail"),
    path("<uuid:pk>/download/", views.document_download, name="download"),

    # HTMX fragment endpoints
    path("api/employees/", views.employee_search, name="employee_search"),
    path("api/template-fields/<uuid:template_id>/", views.template_fields, name="template_fields"),
    path("api/preview/", views.preview_letter, name="preview"),

    # Finance Head management panel
    path("manage/", manage_views.manage_dashboard, name="manage_dashboard"),
    path("manage/users/", manage_views.manage_users, name="manage_users"),
    path("manage/users/add/", manage_views.manage_user_add, name="manage_user_add"),
    path("manage/users/<uuid:user_id>/edit/", manage_views.manage_user_edit, name="manage_user_edit"),
    path("manage/users/<uuid:user_id>/deactivate/", manage_views.manage_user_deactivate, name="manage_user_deactivate"),
    path("manage/companies/", manage_views.manage_companies, name="manage_companies"),
    path("manage/companies/add/", manage_views.manage_company_add, name="manage_company_add"),
    path("manage/companies/<uuid:company_id>/edit/", manage_views.manage_company_edit, name="manage_company_edit"),
    path("manage/templates/", manage_views.manage_templates, name="manage_templates"),
    path("manage/templates/add/", manage_views.manage_template_add, name="manage_template_add"),
    path("manage/templates/<uuid:template_id>/edit/", manage_views.manage_template_edit, name="manage_template_edit"),
    path("manage/templates/<uuid:template_id>/delete/", manage_views.manage_template_delete, name="manage_template_delete"),
    path("manage/templates/<uuid:template_id>/activate/", manage_views.manage_template_activate, name="manage_template_activate"),
    path("manage/templates/convert-docx/", manage_views.manage_template_convert_docx, name="manage_template_convert_docx"),

    # Contract Lens
    path("contract-lens/cadient/", views.cadient_talent_view, name="cadient_talent"),
    path("contract-lens/api/extract/", views.cadient_talent_extract, name="cadient_talent_extract"),
    path("contract-lens/api/analyse-group/", views.cadient_talent_analyse_group, name="cadient_talent_analyse_group"),
    path("contract-lens/api/merge/", views.cadient_talent_merge, name="cadient_talent_merge"),
]

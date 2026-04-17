from django.urls import path
from documents import views

app_name = "documents"

urlpatterns = [
    # Main views
    path("", views.DocumentListView.as_view(), name="list"),
    path("generate/", views.GenerateDocumentView.as_view(), name="generate"),
    path("<uuid:pk>/", views.DocumentDetailView.as_view(), name="detail"),
    path("<uuid:pk>/download/", views.document_download, name="download"),

    # HTMX fragment endpoints
    path("api/employees/", views.employee_search, name="employee_search"),
    path("api/template-fields/<uuid:template_id>/", views.template_fields, name="template_fields"),
    path("api/preview/", views.preview_letter, name="preview"),
]

from django.urls import path
from . import views

app_name = "uploads"

urlpatterns = [
    path("", views.UploadedDocumentListView.as_view(), name="list"),
    path("upload/", views.UploadDocumentView.as_view(), name="upload"),
    path("<uuid:pk>/", views.UploadedDocumentDetailView.as_view(), name="detail"),
    path("<uuid:pk>/download/", views.uploaded_document_download, name="download"),
]

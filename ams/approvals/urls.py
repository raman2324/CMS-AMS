from django.urls import path
from . import views

app_name = 'ams_approvals'

urlpatterns = [
    path('new/', views.request_new, name='request_new'),
    path('inbox/', views.inbox, name='inbox'),
    path('my/', views.all_requests, name='my_requests'),
    path('all/', views.all_requests, name='all_requests'),
    path('<int:pk>/', views.request_detail, name='request_detail'),
    path('<int:pk>/approve/', views.action_approve, name='action_approve'),
    path('<int:pk>/reject/', views.action_reject, name='action_reject'),
    path('<int:pk>/renew/', views.action_renew, name='action_renew'),
    path('<int:pk>/terminate/', views.action_terminate, name='action_terminate'),
]

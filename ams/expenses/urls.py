from django.urls import path
from . import views

app_name = 'ams_expenses'

urlpatterns = [
    path('new/', views.expense_new, name='expense_new'),
    path('', views.expense_list, name='expense_list'),
]

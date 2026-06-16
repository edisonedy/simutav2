from django.contrib import admin
from django.urls import path, include

from django.contrib.auth import views as auth_views
from core.views import dashboard

urlpatterns = [
    path('', dashboard, name='dashboard'),
    path('accounts/login/', auth_views.LoginView.as_view(), name='login'),
    path('accounts/logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('admin/', admin.site.urls),
    path('core/', include('core.urls')),
    path('academico/', include('academico.urls')),
    path('simulador/', include('simulador.urls')),
    path('seguridad/', include('seguridad.urls')),
]

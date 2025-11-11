"""
URL configuration for SIC project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path
from SIC import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.transacciones, name='transacciones'),
    path('resultados/', views.resultados, name='resultados'),
    path('comprobacion/', views.BalanceC, name='comprobacion'),
    path('general/', views.BalanceG, name='general'),
    path('costos/', views.costos, name='costos'),
    path('capital/', views.EstadoCapital, name='capital'),
    path('estados/', views.EstadoFinancieros, name='estados'),
    path('mayor/', views.libroMayor, name='mayor'),
    path('estimacion/', views.estimacion_ifpug, name='estimacion'),
    path('catalogo/', views.catalogo, name='catalogo'),
    path('mod/', views.mod, name='mod'),
    path('cif/', views.cif, name='cif'),
    path('cerrar_periodo/', views.cerrar_periodo_view, name='cerrar_periodo'),
]

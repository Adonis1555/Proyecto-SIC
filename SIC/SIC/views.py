from django.shortcuts import render

def transacciones(request):
    return render(request, 'transacciones.html')

def resultados(request):
    return render(request, 'resultados.html')
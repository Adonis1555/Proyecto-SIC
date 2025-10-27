from django.shortcuts import render

def transacciones(request):
    return render(request, 'transacciones.html')

def resultados(request):
    return render(request, 'resultados.html')

def BalanceC(request):
    return render(request, 'BalanceC.html')

def BalanceG(request):
    return render(request, 'BalanceG.html')

def EstadoCapital(request):
    return render(request, 'EstadoCapital.html')

def EstadoFinancieros(request):
    return render(request, 'EstadosFinancieros.html')

def libroMayor(request):
    return render(request, 'libroMayor.html')

def costos(request):
    return render(request, 'costos.html')
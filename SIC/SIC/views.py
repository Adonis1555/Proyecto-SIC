from django.shortcuts import render, redirect
from .models import Transaccion, Cuenta
from .forms import TransaccionForm

def transacciones(request):
    if request.method == 'POST':
        form = TransaccionForm(request.POST)
        if form.is_valid():
            form.save()  # Guarda la transacción en la base de datos
            return redirect('transacciones')  # Refresca la página
    else:
        form = TransaccionForm()

    # Obtener todas las cuentas para el combobox
    cuentas = Cuenta.objects.all().order_by('codigo')
    transacciones_list = Transaccion.objects.all().order_by('-fecha')  # Lista todas las transacciones
    
    return render(request, 'transacciones.html', {
        'form': form,
        'cuentas': cuentas,
        'transacciones': transacciones_list
    })

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

def catalogo(request):
    return render(request, 'catalogo.html')

def cif(request):
    return render(request, 'cif.html')

def mod(request):
    return render(request, 'mod.html')

def estimacion(request):
    return render(request, 'estimacion.html')
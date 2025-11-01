from django.shortcuts import render, redirect
from .models import Transaccion, Cuenta
from .forms import TransaccionForm
from django.db.models import Sum

def transacciones(request):
    if request.method == 'POST':
        form = TransaccionForm(request.POST)
        if form.is_valid():
            form.save() 
            return redirect('transacciones')  
    else:
        form = TransaccionForm()

    cuentas = Cuenta.objects.all().order_by('codigo')
    transacciones_list = Transaccion.objects.all().order_by('-fecha')  
    resultado_debe = Transaccion.objects.filter(tipo='Debe').aggregate(Sum('monto'))
    total_debe = resultado_debe.get('monto__sum') or 0.00
    resultado_haber = Transaccion.objects.filter(tipo='Haber').aggregate(Sum('monto')) 
    total_haber = resultado_haber.get('monto__sum') or 0.00
    return render(request, 'transacciones.html', { 'form': form, 'cuentas': cuentas, 'transacciones': transacciones_list, 'total_debe':total_debe, 'total_haber':total_haber, })

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
    cuentas = Cuenta.objects.all().order_by('codigo')
    transacciones_list = Transaccion.objects.all().order_by('-fecha') 
    resultado_debe = Transaccion.objects.filter(tipo='Debe').aggregate(Sum('monto'))
    total_debe = resultado_debe.get('monto__sum') or 0.00

    resultado_haber = Transaccion.objects.filter(tipo='Haber').aggregate(Sum('monto'))
    total_haber = resultado_haber.get('monto__sum') or 0.00
    
    context = {
        'cuentas': cuentas,
        'transacciones': transacciones_list,
        'total_debe': total_debe,     
        'total_haber': total_haber,   
    }
    
    return render(request, 'libroMayor.html', context)
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
from django.shortcuts import render, redirect
from .models import Transaccion, Cuenta,Periodo,BalanceComprobacion
from .forms import TransaccionForm
from django.db.models import Sum
from django.utils import timezone
from decimal import Decimal
from datetime import date, timedelta
from calendar import monthrange

def transacciones(request):
    periodo_abierto = Periodo.objects.filter(cerrado=False).order_by('-fecha_inicio').first()
    
    if periodo_abierto:
        primer_dia = periodo_abierto.fecha_inicio
        ultimo_dia = periodo_abierto.fecha_fin
    else:
        hoy = timezone.now().date()
        primer_dia = hoy.replace(day=1)
        ultimo_dia = hoy.replace(day=monthrange(hoy.year, hoy.month)[1])
    if request.method == 'POST':
        form = TransaccionForm(request.POST, primer_dia=primer_dia, ultimo_dia=ultimo_dia)
        if form.is_valid():
            form.save() 
            return redirect('transacciones')  
    else:
        form = TransaccionForm(primer_dia=primer_dia, ultimo_dia=ultimo_dia)
    
    cuentas = Cuenta.objects.all().order_by('codigo')
    transacciones_list = Transaccion.objects.filter(periodo__isnull=True).order_by('-fecha')  

    resultado_debe = transacciones_list.filter(tipo='Debe').aggregate(Sum('monto'))
    total_debe = resultado_debe.get('monto__sum') or Decimal('0.00')

    resultado_haber = transacciones_list.filter(tipo='Haber').aggregate(Sum('monto')) 
    total_haber = resultado_haber.get('monto__sum') or Decimal('0.00')
    return render(request, 'transacciones.html', { 
        'form': form, 
        'cuentas': cuentas, 
        'transacciones': transacciones_list, 
        'total_debe': total_debe, 
        'total_haber': total_haber,
        'primer_dia': primer_dia,
        'ultimo_dia': ultimo_dia
    })

def resultados(request):
    return render(request, 'resultados.html')

def BalanceC(request):
    periodos = Periodo.objects.filter(cerrado=True).order_by('-fecha_inicio')

    periodo_id = request.GET.get('periodo')
    if periodo_id:
        try:
            periodo_seleccionado = Periodo.objects.get(id=periodo_id, cerrado=True)
        except Periodo.DoesNotExist:
            periodo_seleccionado = periodos.first()
    else:
        periodo_seleccionado = periodos.first()

    cierres = BalanceComprobacion.objects.filter(periodo=periodo_seleccionado).order_by('cuenta__codigo') if periodo_seleccionado else []

    totales = cierres.aggregate(
        total_debe=Sum('debe'),
        total_haber=Sum('haber')
    ) if cierres else {'total_debe': 0, 'total_haber': 0}

    return render(request, 'BalanceC.html', {
        'periodos': periodos,
        'periodo_seleccionado': periodo_seleccionado,
        'cierres': cierres,
        'total_debe': totales['total_debe'],
        'total_haber': totales['total_haber']
    })
def BalanceG(request):
    return render(request, 'BalanceG.html')

def EstadoCapital(request):
    return render(request, 'EstadoCapital.html')

def EstadoFinancieros(request):
    return render(request, 'EstadosFinancieros.html')

def libroMayor(request):
    periodo_id = request.GET.get('periodo') 
    if periodo_id:
        transacciones_list = Transaccion.objects.filter(periodo_id=periodo_id).order_by('-fecha')
    else:
        
        transacciones_list = Transaccion.objects.filter(periodo__isnull=True).order_by('-fecha')

    total_debe = transacciones_list.filter(tipo='Debe').aggregate(Sum('monto'))['monto__sum'] or Decimal('0.00')
    total_haber = transacciones_list.filter(tipo='Haber').aggregate(Sum('monto'))['monto__sum'] or Decimal('0.00')


    periodos = Periodo.objects.filter(cerrado=True).order_by('-fecha_inicio')
    periodo_seleccionado = None
    if periodo_id:
        try:
            periodo_seleccionado = Periodo.objects.get(id=periodo_id)
        except Periodo.DoesNotExist:
            periodo_seleccionado = None

    context = {
        'transacciones': transacciones_list,
        'total_debe': total_debe,
        'total_haber': total_haber,
        'periodos': periodos,
        'periodo_seleccionado': periodo_seleccionado
    }

    return render(request, 'libroMayor.html', context)


def costos(request):
    return render(request, 'costos.html')

def catalogo(request):
    cuentas = Cuenta.objects.all().order_by('codigo')
    
    return render(request, 'catalogo.html', {
        'cuentas': cuentas
    })
    return render(request, 'catalogo.html')

def cif(request):
    return render(request, 'cif.html')

def mod(request):
    return render(request, 'mod.html')

def estimacion(request):
    return render(request, 'estimacion.html')

def cerrar_periodo(periodo):

    transacciones = Transaccion.objects.filter(periodo__isnull=True)
    
    cuentas_resumen = {}
    for t in transacciones:
        key = t.cuenta.id
        if key not in cuentas_resumen:
            cuentas_resumen[key] = {'debe': Decimal('0.00'), 'haber': Decimal('0.00')}
        if t.tipo == 'Debe':
            cuentas_resumen[key]['debe'] += t.monto
        else:
            cuentas_resumen[key]['haber'] += t.monto
    
    transacciones.update(periodo=periodo)
    
    return cuentas_resumen


    
def siguiente_mes(fecha_actual):
    """Retorna el primer día del mes siguiente."""
    if fecha_actual.month == 12:
        return date(fecha_actual.year + 1, 1, 1)
    else:
        return date(fecha_actual.year, fecha_actual.month + 1, 1)


def cerrar_periodo_view(request):
    if request.method == "POST":
        periodo_abierto = Periodo.objects.filter(cerrado=False).order_by('-fecha_inicio').first()

        if periodo_abierto:
            fecha_base = periodo_abierto.fecha_inicio
            ultimo_dia = monthrange(fecha_base.year, fecha_base.month)[1]
            periodo_abierto.fecha_fin = fecha_base.replace(day=ultimo_dia)
            periodo_abierto.cerrado = True
            periodo_abierto.nombre = f"Cierre {fecha_base.strftime('%B %Y')}"
            periodo_abierto.save()
            periodo_cerrado = periodo_abierto
        else:
 
            fecha_base = timezone.now().date()
            ultimo_dia = monthrange(fecha_base.year, fecha_base.month)[1]
            periodo_cerrado = Periodo.objects.create(
                nombre=f"Cierre {fecha_base.strftime('%B %Y')}",
                fecha_inicio=fecha_base.replace(day=1),
                fecha_fin=fecha_base.replace(day=ultimo_dia),
                cerrado=True
            )

  
        for cuenta in Cuenta.objects.all():
       
            trans_cuenta = Transaccion.objects.filter(cuenta=cuenta, periodo__isnull=True)
            total_debe = trans_cuenta.filter(tipo='Debe').aggregate(Sum('monto'))['monto__sum'] or Decimal('0.00')
            total_haber = trans_cuenta.filter(tipo='Haber').aggregate(Sum('monto'))['monto__sum'] or Decimal('0.00')
            
            BalanceComprobacion.objects.create(
                periodo=periodo_cerrado,
                cuenta=cuenta,
                debe=total_debe,
                haber=total_haber
            )
            cuenta.saldo = Decimal('0.00')
            cuenta.save()
            
            trans_cuenta.update(periodo=periodo_cerrado)
     
        Transaccion.objects.filter(periodo__isnull=True).update(periodo=periodo_cerrado)
      
        primer_dia_siguiente_mes = siguiente_mes(periodo_cerrado.fecha_inicio)
        ultimo_dia_siguiente_mes = monthrange(primer_dia_siguiente_mes.year, primer_dia_siguiente_mes.month)[1]

        nuevo_periodo = Periodo.objects.create(
            nombre=f"Periodo {primer_dia_siguiente_mes.strftime('%B %Y')}",
            fecha_inicio=primer_dia_siguiente_mes,
            fecha_fin=primer_dia_siguiente_mes.replace(day=ultimo_dia_siguiente_mes),
            cerrado=False
        )
        periodos = Periodo.objects.all().order_by('-fecha_inicio')
        return render(request, 'EstadosFinancieros.html', {
            'periodo': periodo_cerrado,
            'periodos': periodos,
            'periodo_seleccionado': periodo_cerrado
        })

    else:
        periodos = Periodo.objects.all().order_by('-fecha_inicio')
        return render(request, 'EstadosFinancieros.html', {
            'periodos': periodos
        })
# --- Imports Resueltos ---
from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import TransaccionForm
from .models import (
    BalanceComprobacion, Cif, Cuenta, ModEmpleado, Periodo, Transaccion
)
# --- Fin Imports Resueltos ---


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
            # --- Bloque de HEAD (Tus cambios de IVA y Periodo) ---
            transaccion = form.save(commit=False)
            transaccion.periodo = periodo_abierto
            transaccion.save()
            print("exento_iva:", transaccion.exento_iva)
            print("tipo_cuenta:", transaccion.cuenta.tipo)
            print(
                "exento_iva:", transaccion.exento_iva,
                "tipo_cuenta:", transaccion.cuenta.tipo,
                "cuenta_id:", transaccion.cuenta.id
            )
            if (
                not transaccion.exento_iva and 
                transaccion.cuenta.tipo in ['ACT', 'PAS']
            ):
              iva_rate = Decimal('0.13')  # 13% IVA, ajusta según país
              iva_monto = transaccion.monto * iva_rate
              transaccion.monto = iva_monto + transaccion.monto
              transaccion.save(update_fields=['monto']) 
     
              if transaccion.tipo == 'Haber':
                  # Transacción de Debito → IVA va al Debito
                  iva_cuenta = Cuenta.objects.get(codigo='2110')  # IVA débito
                  print("iva",iva_cuenta)
                  Transaccion.objects.create(
                      fecha=transaccion.fecha,
                      cuenta=iva_cuenta,
                      descripcion="Aplicando IVA",
                      monto=iva_monto,
                      tipo='Debe',
                      periodo=periodo_abierto,
                  )
              else:
               iva_cuenta = Cuenta.objects.get(codigo='1108')  
               Transaccion.objects.create(
                   fecha=transaccion.fecha,
                   cuenta=iva_cuenta,
                   descripcion="Aplicando IVA",
                   monto=iva_monto,
                   tipo='Haber',
                   periodo=periodo_abierto,
               )
            return redirect('transacciones')  
            # --- Fin Bloque de HEAD ---
    else:
        form = TransaccionForm(primer_dia=primer_dia, ultimo_dia=ultimo_dia)
    
    cuentas = Cuenta.objects.filter(automatica=False).order_by('codigo')
    transacciones_list = Transaccion.objects.filter(periodo=periodo_abierto).order_by('-fecha')

    # --- Bloque de HEAD (Tu lógica de totales) ---
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
    # --- Fin Bloque de HEAD ---


def resultados(request):
    return render(request, 'resultados.html')


def BalanceC(request):
    # --- Bloque de HEAD (Tu nueva vista) ---
    periodos = Periodo.objects.filter(cerrado=True).order_by('-fecha_inicio')

    # Obtener el periodo seleccionado desde GET
    periodo_id = request.GET.get('periodo')
    if periodo_id:
        try:
            periodo_seleccionado = Periodo.objects.get(id=periodo_id, cerrado=True)
        except Periodo.DoesNotExist:
            periodo_seleccionado = periodos.first()
    else:
        periodo_seleccionado = periodos.first()

    # Obtener los registros de BalanceComprobacion solo para el periodo seleccionado
    cierres = BalanceComprobacion.objects.filter(periodo=periodo_seleccionado).order_by('cuenta__codigo') if periodo_seleccionado else []

    # Calcular totales solo si hay cierres
    if cierres:
        totales = cierres.aggregate(
            total_debe=Sum('debe'),
            total_haber=Sum('haber')
        )
    else:
        totales = {'total_debe': 0, 'total_haber': 0}

    return render(request, 'BalanceC.html', {
        'periodos': periodos,
        'periodo_seleccionado': periodo_seleccionado,
        'cierres': cierres,
        'total_debe': totales['total_debe'],
        'total_haber': totales['total_haber']
    })
    # --- Fin Bloque de HEAD ---


def BalanceG(request):
    return render(request, 'BalanceG.html')


def EstadoCapital(request):
    return render(request, 'EstadoCapital.html')


def EstadoFinancieros(request):
    return render(request, 'EstadosFinancieros.html')


def libroMayor(request):
    # --- Bloque de HEAD (Tu lógica de periodo) ---
    periodo_id = request.GET.get('periodo')

    periodo_abierto = Periodo.objects.filter(cerrado=False).order_by('-fecha_inicio').first()
    if periodo_id:
        # Mostrar transacciones de un periodo cerrado
        transacciones_list = Transaccion.objects.filter(periodo_id=periodo_id).order_by('-fecha')
    else:
        # Mostrar transacciones del periodo en curso (abierto)
        transacciones_list = Transaccion.objects.filter(periodo=periodo_abierto).order_by('-fecha') if periodo_abierto else []
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
    # --- Fin Bloque de HEAD ---
    return render(request, 'libroMayor.html', context)


def costos(request):
    return render(request, 'costos.html')


def catalogo(request):
    cuentas = Cuenta.objects.all().order_by('codigo')
    
    return render(request, 'catalogo.html', {
        'cuentas': cuentas
    })
    # Nota: esta línea de abajo estaba duplicada en tu código, la he quitado.
    # return render(request, 'catalogo.html')


# --- INICIO BLOQUE ADONIS (cif y mod) ---
# --- CIF: VISTA CRUD ---
def cif(request):
    """
    Pantalla de CIF:
      - Crear:  POST action=create  con nombre, monto, notas
      - Editar: POST action=update  con id, nombre, monto, notas
      - Borrar: POST action=delete  con id
    """
    if request.method == 'POST':
        action = (request.POST.get('action') or 'create').strip()

        if action == 'create':
            nombre = (request.POST.get('nombre') or '').strip()
            monto = Decimal(request.POST.get('monto') or '0')
            notas = (request.POST.get('notas') or '').strip()
            if nombre and monto >= 0:
                Cif.objects.create(nombre=nombre, monto=monto, notas=notas)
            return redirect('cif')

        if action == 'update':
            obj = get_object_or_404(Cif, pk=request.POST.get('id'))
            obj.nombre = (request.POST.get('nombre') or '').strip()
            obj.monto = Decimal(request.POST.get('monto') or '0')
            obj.notas = (request.POST.get('notas') or '').strip()
            obj.save()
            return redirect('cif')

        if action == 'delete':
            obj = get_object_or_404(Cif, pk=request.POST.get('id'))
            obj.delete()
            return redirect('cif')

    # GET: listar y totalizar
    cifs = Cif.objects.order_by('id')
    total = cifs.aggregate(total=Sum('monto'))['total'] or Decimal('0')
    return render(request, 'cif.html', {'cifs': cifs, 'total_cif': total})
# --- FIN CIF ---


# === MOD: VISTA CRUD ===
def mod(request):
    """
    Pantalla de MOD:
      - Crear:  POST action=create  con nombre, cargo, salario
      - Editar: POST action=update  con id, nombre, cargo, salario
      - Borrar: POST action=delete  con id
    Renderiza 'mod.html' con 'empleados' y 'total_salarios'
    """
    if request.method == 'POST':
        action = (request.POST.get('action') or 'create').strip()

        if action == 'create':
            # Límite de 30 empleados
            if ModEmpleado.objects.count() < 30:
                nombre = (request.POST.get('nombre') or '').strip()
                cargo = (request.POST.get('cargo') or '').strip()
                salario = Decimal(request.POST.get('salario') or '0')
                if nombre and cargo and salario >= 0:
                    ModEmpleado.objects.create(nombre=nombre, cargo=cargo, salario=salario)
            return redirect('mod')

        if action == 'update':
            obj = get_object_or_404(ModEmpleado, pk=request.POST.get('id'))
            obj.nombre = (request.POST.get('nombre') or '').strip()
            obj.cargo = (request.POST.get('cargo') or '').strip()
            obj.salario = Decimal(request.POST.get('salario') or '0')
            obj.save()
            return redirect('mod')

        if action == 'delete':
            obj = get_object_or_404(ModEmpleado, pk=request.POST.get('id'))
            obj.delete()
            return redirect('mod')

    # GET
    empleados = ModEmpleado.objects.order_by('id')
    total_salarios = empleados.aggregate(total=Sum('salario'))['total'] or Decimal('0')
    return render(request, 'mod.html', {'empleados': empleados, 'total_salarios': total_salarios})
# === FIN MOD ===
# --- FIN BLOQUE ADONIS ---


def estimacion(request):
    return render(request, 'estimacion.html')


# --- INICIO BLOQUE HEAD (Tu lógica de Cierre) ---
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
       
            trans_cuenta = Transaccion.objects.filter(cuenta=cuenta, periodo=periodo_abierto)
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
# --- FIN BLOQUE HEAD ---
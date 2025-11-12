from django.shortcuts import render, redirect
from .models import Transaccion, Cuenta,Periodo,BalanceComprobacion,Cif,ModEmpleado
from .forms import TransaccionForm
from django.db.models import Sum, F,Q, Case, When
from django.db import connection, transaction
from django.utils import timezone
from decimal import Decimal
from datetime import date, timedelta
from calendar import monthrange
import logging
from django.shortcuts import get_object_or_404
from django.contrib import messages
import json
from django.db import connection
from django.db.models.functions import Coalesce
from django.urls import reverse
from django.db.models import DecimalField, Value

def calcular_costo_real_empleado(salario_nominal):
    """
    Calcula el costo real mensual (nominal + prestaciones patronales)
    basado en la lógica de tu script.
    """
    s = Decimal(salario_nominal)
    
    # Constantes (convertidas a Decimal para precisión)
    AFP = Decimal('0.0775')
    AGUI = Decimal('0.041')
    ISSS = Decimal('0.075')
    ISSS_TOPE = Decimal('1000')
    SEPT = Decimal('4.3333') # (s / 30) * 4.3333
    VAC_DIAS = Decimal('1.25') # (s / 30) * 1.25
    INCAF = Decimal('0.01')
    TREINTA = Decimal('30')

    # Cálculos de prestaciones
    afp  = s * AFP
    isss = min(s, ISSS_TOPE) * ISSS
    sept = (s / TREINTA) * SEPT
    agui = s * AGUI
    vac  = (s / TREINTA) * VAC_DIAS
    incf = s * INCAF

    # Suma total (Costo Real)
    costo_real = s + afp + isss + sept + agui + vac + incf
    
    # Redondeamos a 2 decimales por si acaso
    return costo_real.quantize(Decimal('0.01'))

@transaction.atomic
def transacciones(request):
    periodo_abierto = Periodo.objects.filter(cerrado=False).order_by('-fecha_inicio').first()
    
    if periodo_abierto:
        primer_dia = periodo_abierto.fecha_inicio
        ultimo_dia = periodo_abierto.fecha_fin
    else:
        # (Lógica de fallback si no hay periodo)
        hoy = timezone.now().date()
        primer_dia = hoy.replace(day=1)
        ultimo_dia = monthrange(hoy.year, hoy.month)[1]

    if request.method == 'POST':
        # --- USA TU FORMULARIO ---
        form = TransaccionForm(request.POST, primer_dia=primer_dia, ultimo_dia=ultimo_dia)
        if form.is_valid():
            transaccion = form.save(commit=False)
            transaccion.periodo = periodo_abierto
            transaccion.fecha = form.cleaned_data['fecha']
            
            # 1. Se guarda en la tabla Transaccion (Historial)
            transaccion.save() 
            
            # ===================================================================
            # --- INICIO DE BLOQUE NUEVO (Actualizar SIC_cuenta - Principal) ---
            # ===================================================================
            try:
                cuenta_a_actualizar = transaccion.cuenta
                monto = transaccion.monto
                
                if transaccion.tipo == 'Debe':
                    cuenta_a_actualizar.debe = Coalesce(F('debe'), Decimal('0.00')) + monto
                    cuenta_a_actualizar.save(update_fields=['debe'])
                else: # 'Haber'
                    cuenta_a_actualizar.haber = Coalesce(F('haber'), Decimal('0.00')) + monto
                    cuenta_a_actualizar.save(update_fields=['haber'])
                
                print(f"--- DEBUG: Saldo 'en vivo' de {cuenta_a_actualizar.nombre} actualizado ---")
            except Exception as e:
                messages.error(request, f"Error al actualizar el saldo en vivo de la cuenta principal: {e}")
                raise e # Detiene la transacción
            # ===================================================================
            # --- FIN DE BLOQUE NUEVO ---
            # ===================================================================

            
            # --- TU LÓGICA DE VARIACIÓN (SIN CAMBIOS) ---
            if transaccion.cuenta.tipo == 'ING' and transaccion.tipo == 'Haber':
                print("--- DEBUG: Detectada VENTA, calculando Variación (Lados Separados) ---")
                try:
                    monto_venta = transaccion.monto
                    cuenta_estimado = Cuenta.objects.get(nombre="Costo estimado")
                    cuenta_variacion = Cuenta.objects.get(nombre="Variación entre costo estimado y real")
                    cuenta_estimado.refresh_from_db()
                    costo_estimado_val = cuenta_estimado.debe or Decimal('0.00')
                    
                    if monto_venta > costo_estimado_val:
                        ganancia = monto_venta - costo_estimado_val
                        cuenta_variacion.haber = Coalesce(F('haber'), Decimal('0.00')) + ganancia
                        cuenta_variacion.save(update_fields=['haber'])
                        messages.success(request, f"Venta registrada. Utilidad en Variación: ${ganancia:,.2f} (Haber).")
                    elif costo_estimado_val > monto_venta:
                        perdida = costo_estimado_val - monto_venta
                        cuenta_variacion.debe = Coalesce(F('debe'), Decimal('0.00')) + perdida
                        cuenta_variacion.save(update_fields=['debe'])
                        messages.success(request, f"Venta registrada. Pérdida en Variación: ${perdida:,.2f} (Debe).")
                    else:
                        messages.success(request, f"Venta registrada. Sin variación (Costo=Venta).")

                except Cuenta.DoesNotExist as e:
                    messages.error(request, f"Error Crítico (Cierre): No se encontró la cuenta 'Costo estimado' o 'Variación...'. ({e}).")
                except Exception as e:
                    messages.error(request, f"Error inesperado al calcular la variación: {e}")
            
            # --- TU LÓGICA DE IVA (RESPETADA) ---
            if (
                not transaccion.exento_iva and 
                transaccion.cuenta.tipo in ['ACT', 'PAS']
            ):
                iva_rate = Decimal('0.13')
                iva_monto = transaccion.monto * iva_rate
                
                # --- TU LÓGICA ORIGINAL de sumar el IVA a la transacción base ---
                transaccion.monto = iva_monto + transaccion.monto
                transaccion.save(update_fields=['monto']) 
                
                # --- INICIO DE BLOQUE NUEVO (Actualizar SIC_cuenta por el IVA sumado) ---
                try:
                    if transaccion.tipo == 'Debe':
                        transaccion.cuenta.debe = Coalesce(F('debe'), Decimal('0.00')) + iva_monto
                        transaccion.cuenta.save(update_fields=['debe'])
                    else:
                        transaccion.cuenta.haber = Coalesce(F('haber'), Decimal('0.00')) + iva_monto
                        transaccion.cuenta.save(update_fields=['haber'])
                except Exception as e:
                    messages.error(request, f"Error al actualizar el saldo 'en vivo' (IVA) de la cuenta principal: {e}")
                    raise e
                # --- FIN DE BLOQUE NUEVO ---

                if transaccion.tipo == 'Haber':
                    iva_cuenta = Cuenta.objects.get(codigo='1106')
                    tipo_iva = 'Debe'
                    desc_iva = "Aplicando IVA (Crédito Fiscal)"
                else:
                   iva_cuenta = Cuenta.objects.get(codigo='2111')
                   tipo_iva = 'Haber'
                   desc_iva = "Aplicando IVA (Débito Fiscal)"
                
                # 1. Crear la transacción de IVA (para el historial)
                Transaccion.objects.create(
                    fecha=transaccion.fecha, # <-- Arreglado
                    cuenta=iva_cuenta,
                    descripcion=desc_iva,
                    monto=iva_monto,
                    tipo=tipo_iva,
                    periodo=periodo_abierto,
                    exento_iva=True
                )
                
                # ===================================================================
                # --- INICIO DE BLOQUE NUEVO (Actualizar SIC_cuenta - IVA) ---
                # ===================================================================
                try:
                    if tipo_iva == 'Debe':
                        iva_cuenta.debe = Coalesce(F('debe'), Decimal('0.00')) + iva_monto
                        iva_cuenta.save(update_fields=['debe'])
                    else:
                        iva_cuenta.haber = Coalesce(F('haber'), Decimal('0.00')) + iva_monto
                        iva_cuenta.save(update_fields=['haber'])
                    print(f"--- DEBUG: Saldo 'en vivo' de {iva_cuenta.nombre} actualizado ---")
                except Exception as e:
                    messages.error(request, f"Error al actualizar el saldo 'en vivo' de la cuenta de IVA: {e}")
                    raise e
                # ===================================================================
                # --- FIN DE BLOQUE NUEVO ---
                # ===================================================================
            
            return redirect('transacciones')  
    else:
        # --- USA TU FORMULARIO ---
        form = TransaccionForm(primer_dia=primer_dia, ultimo_dia=ultimo_dia)
    
    # --- TU LÓGICA GET (SIN CAMBIOS) ---
    cuentas = Cuenta.objects.filter(automatica=False).order_by('codigo')
    transacciones_list = Transaccion.objects.filter(periodo=periodo_abierto).order_by('-fecha')

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


def EstadoCapital(request):
    """
    Genera el Estado de Capital:
    - Muestra solo las cuentas de tipo 'CAP'
    - Excluye la cuenta 3103 (Pérdidas y Ganancias)
    - Agrupa las cuentas igual que el Balance General
    - Evita duplicaciones
    """

    # 1️⃣ Obtener periodos cerrados
    periodos = Periodo.objects.filter(cerrado=True).order_by('-fecha_inicio')

    periodo_seleccionado = None
    cuentas_capital = []
    total_capital = Decimal('0.00')

    # 2️⃣ Verificar si se seleccionó un periodo
    periodo_id = request.GET.get('periodo')
    if periodo_id:
        try:
            periodo_seleccionado = Periodo.objects.get(id=periodo_id)

            # 3️⃣ Agrupar cuentas tipo 'CAP' (excluyendo padres y PyG)
            cuentas = (
                BalanceComprobacion.objects.filter(
                    periodo=periodo_seleccionado,
                    cuenta__tipo='CAP'
                )
                .exclude(cuenta__cuenta_padre__isnull=True)
                .exclude(cuenta__codigo='3103')
                .values('cuenta__codigo', 'cuenta__nombre')
                .annotate(
                    total_debe=Sum('debe'),
                    total_haber=Sum('haber')
                )
                .order_by('cuenta__codigo')
            )

            # 4️⃣ Calcular el saldo neto por cuenta
            for c in cuentas:
                saldo = c['total_haber'] - c['total_debe']
                cuentas_capital.append({
                    'codigo': c['cuenta__codigo'],
                    'nombre': c['cuenta__nombre'],
                    'saldo': saldo
                })
                total_capital += saldo

        except Periodo.DoesNotExist:
            periodo_seleccionado = None

    # 5️⃣ Enviar al template
    contexto = {
        'periodos': periodos,
        'periodo_seleccionado': periodo_seleccionado,
        'cuentas_capital': cuentas_capital,
        'total_capital': total_capital,
    }

    return render(request, 'EstadoCapital.html', contexto)

def BalanceC(request):
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

    # --- CONSULTA MODIFICADA ---
    if periodo_seleccionado:
        cierres = BalanceComprobacion.objects.filter(
            periodo=periodo_seleccionado
        ).exclude(
            # Excluye las cuentas "raíz" (ej. "Activo", "Pasivo", etc.)
            cuenta__cuenta_padre_id__isnull=True
        ).exclude(
            # ¡NUEVO! Excluimos las cuentas de tipo Capital
            cuenta__tipo='CAP' 
        ).order_by('cuenta__codigo')
    else:
        cierres = []
    # --- FIN DE LA MODIFICACIÓN ---

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
def BalanceG(request):
    
    # 1. Obtener todos los periodos cerrados para el menú
    periodos = Periodo.objects.filter(cerrado=True).order_by('-fecha_inicio')
    
    # 2. Definir variables por defecto
    periodo_seleccionado = None
    cuentas_activo = []
    cuentas_pasivo = []
    cuentas_patrimonio = []
    total_activo = Decimal('0.00')
    total_pasivo = Decimal('0.00')
    total_patrimonio = Decimal('0.00')
    total_pasivo_patrimonio = Decimal('0.00')

    # 3. Verificar si el usuario seleccionó un periodo
    periodo_id = request.GET.get('periodo')
    
    if periodo_id:
        try:
            periodo_seleccionado = Periodo.objects.get(id=periodo_id)
            
            # 4. Obtener las cuentas del Balance de Comprobación
            #    para ese periodo, separadas por tipo.
            
            # Obtenemos Activos (Naturaleza Deudora)
            cuentas_activo = BalanceComprobacion.objects.filter(
                periodo=periodo_seleccionado,
                cuenta__tipo='ACT'
            ).exclude(
                cuenta__cuenta_padre_id__isnull=True # <-- ¡CORREGIDO! Oculta padres
            ).select_related('cuenta')

            # Obtenemos Pasivos (Naturaleza Acreedora)
            cuentas_pasivo = BalanceComprobacion.objects.filter(
                periodo=periodo_seleccionado,
                cuenta__tipo='PAS'
            ).exclude(
                cuenta__cuenta_padre_id__isnull=True # <-- ¡CORREGIDO! Oculta padres
            ).select_related('cuenta')

            # Obtenemos Patrimonio (Naturaleza Acreedora)
            cuentas_patrimonio = BalanceComprobacion.objects.filter(
                periodo=periodo_seleccionado,
                cuenta__tipo='CAP'
            ).exclude(
                cuenta__cuenta_padre_id__isnull=True # <-- ¡CORREGIDO! Oculta padres
            ).select_related('cuenta')

            # 5. Calcular Totales (La Balanza ya tiene los saldos netos)
            
            # Sumamos la columna 'debe' de Activos
            total_activo = cuentas_activo.aggregate(total=Sum('debe'))['total'] or Decimal('0.00')
            
            # Sumamos la columna 'haber' de Pasivos
            total_pasivo = cuentas_pasivo.aggregate(total=Sum('haber'))['total'] or Decimal('0.00')

            # Sumamos la columna 'haber' de Patrimonio
            total_patrimonio = cuentas_patrimonio.aggregate(total=Sum('haber'))['total'] or Decimal('0.00')

            # Suma final para la ecuación contable
            total_pasivo_patrimonio = total_pasivo + total_patrimonio

        except Periodo.DoesNotExist:
            periodo_seleccionado = None

    # 6. Enviar datos al contexto
    contexto = {
        'periodos': periodos,
        'periodo_seleccionado': periodo_seleccionado,
        'cuentas_activo': cuentas_activo,
        'cuentas_pasivo': cuentas_pasivo,
        'cuentas_patrimonio': cuentas_patrimonio,
        'total_activo': total_activo,
        'total_pasivo': total_pasivo,
        'total_patrimonio': total_patrimonio,
        'total_pasivo_patrimonio': total_pasivo_patrimonio,
    }
    
    return render(request, 'BalanceG.html', contexto)

def EstadoCapital(request):
    
    # 1. Obtener todos los periodos cerrados para el menú desplegable
    periodos = Periodo.objects.filter(cerrado=True).order_by('-fecha_inicio')
    
    # 2. Definir variables por defecto
    periodo_seleccionado = None
    cuentas_capital = []
    utilidad_periodo = Decimal('0.00')
    capital_final = Decimal('0.00')

    # 3. Verificar si el usuario seleccionó un periodo (via GET)
    periodo_id = request.GET.get('periodo')
    if periodo_id:
        try:
            periodo_seleccionado = Periodo.objects.get(id=periodo_id)
            
            # 4. Obtener cuentas de Capital (Capital Social, Reservas, etc.)
            cuentas_capital = BalanceComprobacion.objects.filter(
                periodo=periodo_seleccionado,
                cuenta__tipo='CAP'  # Filtramos solo las cuentas tipo Capital
            ).select_related('cuenta')

            # 5. Calcular la Utilidad/Pérdida de ESTE periodo
            total_ingresos = BalanceComprobacion.objects.filter(
                periodo=periodo_seleccionado,
                cuenta__tipo='ING'
            ).aggregate(total=Sum('haber'))['total'] or Decimal('0.00')
            
            total_gastos = BalanceComprobacion.objects.filter(
                periodo=periodo_seleccionado,
                cuenta__tipo='GAS'
            ).aggregate(total=Sum('debe'))['total'] or Decimal('0.00')

            utilidad_periodo = total_ingresos - total_gastos
            
            # 6. Calcular el Capital Final
            # (Capital Final = Suma de saldos de cuentas CAP + Utilidad)
            total_capital_haber = cuentas_capital.aggregate(total=Sum('haber'))['total'] or Decimal('0.00')
            total_capital_debe = cuentas_capital.aggregate(total=Sum('debe'))['total'] or Decimal('0.00')
            
            saldo_cuentas_cap = total_capital_haber - total_capital_debe
            capital_final = saldo_cuentas_cap + utilidad_periodo

        except Periodo.DoesNotExist:
            periodo_seleccionado = None

    # 7. Enviar todo al contexto
    contexto = {
        'periodos': periodos,
        'periodo_seleccionado': periodo_seleccionado,
        'cuentas_capital': cuentas_capital,    # Lista de cuentas CAP
        'utilidad_periodo': utilidad_periodo,  # El resultado (ING - GAS)
        'capital_final': capital_final,        # El total final
    }
    
    return render(request, 'EstadoCapital.html', contexto)

def EstadoFinancieros(request):
    return render(request, 'EstadosFinancieros.html')

def libroMayor(request):
    periodo_id = request.GET.get('periodo')

    periodo_abierto = Periodo.objects.filter(cerrado=False).order_by('-fecha_inicio').first()

    if periodo_id:
        # Mostrar transacciones de un periodo cerrado
        transacciones_list = Transaccion.objects.filter(periodo_id=periodo_id).order_by('-fecha')
    elif periodo_abierto:
        # Mostrar transacciones del periodo abierto
        transacciones_list = Transaccion.objects.filter(periodo=periodo_abierto).order_by('-fecha')
    else:
        # No hay periodo abierto ni periodo seleccionado → mostrar todas las transacciones
        transacciones_list = Transaccion.objects.all().order_by('-fecha')

    # Totales
    total_debe = sum(Decimal(t.monto) for t in transacciones_list if t.tipo == 'Debe')
    total_haber = sum(Decimal(t.monto) for t in transacciones_list if t.tipo == 'Haber')

    # Periodos para selector
    periodos = Periodo.objects.filter(cerrado=True).order_by('-fecha_inicio')

    # Periodo seleccionado
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
    
    return render(request, 'Catalogo.html', {
        'cuentas': cuentas
    })

def cif(request):
    return render(request, 'cif.html')


def estimacion(request):
    return render(request, 'estimacion.html')


@transaction.atomic
def cerrar_periodo_view(request):
    """
    Cierre de período contable (v8):
    - No resetea la cuenta de costo estimado.
    - Suma la cuenta de variación a PyG.
    - Solo salda ING, GAS, PyG y Variación.
    - Aplica lógica dependiente del lado contable.
    """
    if request.method == "POST":
        # --- 1️⃣ Identificar o crear período a cerrar ---
        periodo_abierto = Periodo.objects.filter(cerrado=False).order_by('-fecha_inicio').first()
        
        if periodo_abierto:
            # Transacciones del período abierto
            transacciones_a_cerrar = Transaccion.objects.filter(periodo=periodo_abierto)
            fecha_base = periodo_abierto.fecha_inicio
        else:
            # Transacciones "huérfanas" (sin período asignado)
            transacciones_a_cerrar = Transaccion.objects.filter(periodo__isnull=True)
            fecha_base = timezone.now().date()

        VALOR_TIPO_DEBITO = 'Debe'
        VALOR_TIPO_HABER = 'Haber'

        saldos_periodo = transacciones_a_cerrar.aggregate(
            total_debe=Sum(
                Case(
                    When(tipo=VALOR_TIPO_DEBITO, then=F('monto')),
                    default=Value(0),
                    output_field=DecimalField()
                )
            ),
            total_haber=Sum(
                Case(
                    When(tipo=VALOR_TIPO_HABER, then=F('monto')),
                    default=Value(0),
                    output_field=DecimalField()
                )
            )
        )
        
        total_debe_periodo = saldos_periodo['total_debe'] or Decimal('0.00')
        total_haber_periodo = saldos_periodo['total_haber'] or Decimal('0.00')
        
        # Validación con tolerancia de 1 centavo
        if abs(total_debe_periodo - total_haber_periodo) > Decimal('0.01'):
            messages.error(
                request, 
                f"❌ Error: Las transacciones del período no están cuadradas. "
                f"Total Debe: ${total_debe_periodo:,.2f}, "
                f"Total Haber: ${total_haber_periodo:,.2f}. "
                "El cierre no puede continuar."
            )
            # Volvemos a mostrar la página con el mensaje de error
            periodos = Periodo.objects.all().order_by('-fecha_inicio')
            return render(request, 'libroMayor.html', {'periodos': periodos})
        periodo_abierto = Periodo.objects.filter(cerrado=False).order_by('-fecha_inicio').first()
        
        if periodo_abierto:
            fecha_base = periodo_abierto.fecha_inicio
            ultimo_dia = monthrange(fecha_base.year, fecha_base.month)[1]
            periodo_abierto.fecha_fin = fecha_base.replace(day=ultimo_dia)
            periodo_abierto.cerrado = True
            periodo_abierto.nombre = f"Cierre {fecha_base.strftime('%B %Y')}"
            periodo_abierto.save()
            periodo_cerrado = periodo_abierto
            transacciones_a_cerrar = Transaccion.objects.filter(periodo=periodo_abierto)
        else:
            fecha_base = timezone.now().date()
            ultimo_dia = monthrange(fecha_base.year, fecha_base.month)[1]
            periodo_cerrado = Periodo.objects.create(
                nombre=f"Cierre {fecha_base.strftime('%B %Y')}",
                fecha_inicio=fecha_base.replace(day=1),
                fecha_fin=fecha_base.replace(day=ultimo_dia),
                cerrado=True
            )
            transacciones_a_cerrar = Transaccion.objects.filter(periodo__isnull=True)

        # --- 2️⃣ Cálculo de Ingresos y Gastos + Variación ---
        cuentas_ingreso = Cuenta.objects.filter(tipo='ING', automatica=False)
        cuentas_gasto = Cuenta.objects.filter(tipo='GAS', automatica=False)

        total_ingresos = cuentas_ingreso.aggregate(
            total=Sum(Coalesce(F('haber'), Value(0), output_field=DecimalField(max_digits=15, decimal_places=2)))
        )['total'] or Decimal('0.00')
        
        total_gastos = cuentas_gasto.aggregate(
            total=Sum(Coalesce(F('debe'), Value(0), output_field=DecimalField(max_digits=15, decimal_places=2)))
        )['total'] or Decimal('0.00')

        # Variación entre costo estimado y real (si existe)
        try:
            cuenta_variacion = Cuenta.objects.get(nombre__icontains="variación entre costo estimado y real")
            total_ingresos += cuenta_variacion.haber or 0
            total_gastos += cuenta_variacion.debe or 0
        except Cuenta.DoesNotExist:
            cuenta_variacion = None

        resultado_del_periodo = total_ingresos - total_gastos

        # --- 3️⃣ Obtener cuentas clave ---
        cuenta_pyg = Cuenta.objects.get(codigo='3103')  # Pérdidas y Ganancias
        cuenta_capital = Cuenta.objects.filter(codigo='3101').first()
        cuenta_reserva = Cuenta.objects.filter(codigo='3102').first()

        # --- 4️⃣ Guardar snapshot de todas las cuentas ---
        for cuenta in Cuenta.objects.all():
            saldo_debe = cuenta.debe or 0
            saldo_haber = cuenta.haber or 0

            # Netear
            if saldo_debe > saldo_haber:
                debe_final = saldo_debe - saldo_haber
                haber_final = 0
            elif saldo_haber > saldo_debe:
                haber_final = saldo_haber - saldo_debe
                debe_final = 0
            else:
                debe_final = haber_final = 0

            BalanceComprobacion.objects.update_or_create(
                periodo=periodo_cerrado,
                cuenta=cuenta,
                defaults={'debe': debe_final, 'haber': haber_final}
            )

            # --- 5️⃣ Reset solo de ING, GAS, PyG y Variación ---
            if cuenta.tipo in ['ING', 'GAS'] or cuenta == cuenta_pyg or cuenta == cuenta_variacion:
                # NO resetear costo estimado
                if "costo estimado" not in cuenta.nombre.lower():
                    cuenta.debe = 0
                    cuenta.haber = 0
                    cuenta.save(update_fields=['debe', 'haber'])

        # --- 6️⃣ Aplicar resultado a PyG ---
        if resultado_del_periodo > 0:  # utilidad
            cuenta_pyg.haber = (cuenta_pyg.haber or 0) + resultado_del_periodo
            cuenta_pyg.debe = 0
        elif resultado_del_periodo < 0:  # pérdida
            cuenta_pyg.debe = (cuenta_pyg.debe or 0) + abs(resultado_del_periodo)
            cuenta_pyg.haber = 0
        else:
            cuenta_pyg.debe = cuenta_pyg.haber = 0

        BalanceComprobacion.objects.update_or_create(
            periodo=periodo_cerrado,
            cuenta=cuenta_pyg,
            defaults={'debe': cuenta_pyg.debe, 'haber': cuenta_pyg.haber}
        )
        cuenta_pyg.save(update_fields=['debe', 'haber'])

        # --- 7️⃣ Distribución de resultados en capital y reserva ---
        if resultado_del_periodo != 0 and cuenta_capital and cuenta_reserva:
            reserva = resultado_del_periodo * Decimal('0.20')
            capital = resultado_del_periodo * Decimal('0.80')

            cuenta_reserva.haber += max(reserva, 0)
            cuenta_capital.haber += max(capital, 0)
            cuenta_capital.save()
            cuenta_reserva.save()

        # --- 8️⃣ Cerrar transacciones ---
        transacciones_a_cerrar.update(periodo=periodo_cerrado)

        # --- 9️⃣ Crear nuevo período ---
        primer_dia_sig = (fecha_base.replace(day=1) + timezone.timedelta(days=32)).replace(day=1)
        ultimo_dia_sig = monthrange(primer_dia_sig.year, primer_dia_sig.month)[1]
        nuevo_periodo = Periodo.objects.create(
            nombre=f"Periodo {primer_dia_sig.strftime('%B %Y')}",
            fecha_inicio=primer_dia_sig,
            fecha_fin=primer_dia_sig.replace(day=ultimo_dia_sig),
            cerrado=False
        )

        # Traspasar solo ACT, PAS y CAP
        for cuenta in Cuenta.objects.filter(tipo__in=['ACT', 'PAS', 'CAP']):
            BalanceComprobacion.objects.create(
                periodo=nuevo_periodo,
                cuenta=cuenta,
                debe=cuenta.debe or 0,
                haber=cuenta.haber or 0
            )

        messages.success(request, f"✅ Cierre completado. Resultado del período: ${resultado_del_periodo:,.2f}")
        return redirect(f"{reverse('comprobacion')}?periodo={periodo_cerrado.id}")

    else:
        periodos = Periodo.objects.all().order_by('-fecha_inicio')
        return render(request, 'EstadosFinancieros.html', {'periodos': periodos})


# =========================
# CIF: CRUD
# =========================
def cif(request):
    """
    Pantalla de CIF:
      - Crear:  POST action=create  con nombre, monto, notas
      - Editar: POST action=update  con id, nombre, monto, notas
      - Borrar: POST action=delete  con id
    """
    if request.method == "POST":
        action = (request.POST.get("action") or "create").strip()

        if action == "create":
            nombre = (request.POST.get("nombre") or "").strip()
            monto = Decimal(request.POST.get("monto") or "0")
            notas = (request.POST.get("notas") or "").strip()
            if nombre and monto >= 0:
                Cif.objects.create(nombre=nombre, monto=monto, notas=notas)
            return redirect("cif")

        if action == "update":
            obj = get_object_or_404(Cif, pk=request.POST.get("id"))
            obj.nombre = (request.POST.get("nombre") or "").strip()
            obj.monto = Decimal(request.POST.get("monto") or "0")
            obj.notas = (request.POST.get("notas") or "").strip()
            obj.save()
            return redirect("cif")

        if action == "delete":
            obj = get_object_or_404(Cif, pk=request.POST.get("id"))
            obj.delete()
            return redirect("cif")

    # GET: listar y totalizar
    cifs = Cif.objects.order_by("id")
    total = cifs.aggregate(total=Sum("monto"))["total"] or Decimal("0")
    return render(request, "cif.html", {"cifs": cifs, "total_cif": total})

# =========================
# MOD: CRUD simple
# =========================
ADMIN_ROLES = [
    "Asistente administrativo", "Auditor interno", "Contador general",
    "Gerente general técnico", "Soporte/Atención al cliente",
]
VENTAS_ROLES = [
    "Jefe de ventas", "Coordinador de marketing", "Vendedor", "Diseñador gráfico",
]
PROD_ROLES = [
    "Admin. de servidores/BD", "Desarrollador junior", "Desarrollador senior",
    "Especialista en seguridad", "Líder técnico", "Tester QA",
]

def get_cuenta_por_cargo(cargo):
    # (Función que ignora mayúsculas/minúsculas)
    cargo_norm = cargo.lower().strip()
    admin_roles_norm = [r.lower().strip() for r in ADMIN_ROLES]
    ventas_roles_norm = [r.lower().strip() for r in VENTAS_ROLES]
    prod_roles_norm = [r.lower().strip() for r in PROD_ROLES]

    if cargo_norm in admin_roles_norm:
        return "Gasto de administración" 
    if cargo_norm in ventas_roles_norm:
        return "Gasto de venta"
    if cargo_norm in prod_roles_norm:
        return "Software en proceso"
    return None

# ===================================================================
# --- CÁLCULO DE COSTO (Devuelve DICCIONARIO) ---
# ===================================================================
def calcular_componentes_costo(salario_nominal):
    """
    Calcula y devuelve un diccionario con todos los componentes
    del costo real mensual.
    """
    s = Decimal(salario_nominal)
    
    # Constantes
    AFP = Decimal('0.0775')
    AGUI = Decimal('0.041')
    ISSS = Decimal('0.075')
    ISSS_TOPE = Decimal('1000')
    SEPT = Decimal('4.3333') # (s / 30) * 4.3333
    VAC_DIAS = Decimal('1.25') # (s / 30) * 1.25
    INCAF = Decimal('0.01')
    TREINTA = Decimal('30')

    # Cálculos de prestaciones
    afp  = s * AFP
    isss = min(s, ISSS_TOPE) * ISSS
    sept = (s / TREINTA) * SEPT
    agui = s * AGUI
    vac  = (s / TREINTA) * VAC_DIAS
    incf = s * INCAF

    # Suma total (Costo Real)
    costo_real = s + afp + isss + sept + agui + vac + incf
    
    return {
        'nominal': s,
        'afp': afp.quantize(Decimal('0.01')),
        'isss': isss.quantize(Decimal('0.01')),
        'septimo': sept.quantize(Decimal('0.01')),
        'aguinaldo': agui.quantize(Decimal('0.01')),
        'vacaciones': vac.quantize(Decimal('0.01')),
        'incaf': incf.quantize(Decimal('0.01')),
        'costo_total_real': costo_real.quantize(Decimal('0.01'))
    }

# ===================================================================
# --- FUNCIONES DE ACTUALIZACIÓN DE CUENTAS ---
# ===================================================================
def actualizar_debe(request, nombre_cuenta, monto):
    """Suma o resta (si monto es negativo) un valor al 'debe' de una cuenta."""
    if not nombre_cuenta or monto == 0:
        return
    try:
        cuenta = Cuenta.objects.get(nombre=nombre_cuenta)
        cuenta.debe = Coalesce(F('debe'), Decimal('0.00')) + monto
        cuenta.save(update_fields=['debe'])
    except Cuenta.DoesNotExist:
        messages.error(request, f"Error Crítico: No se pudo encontrar la cuenta de Gasto/Costo '{nombre_cuenta}'.")

def actualizar_haber(request, nombre_cuenta, monto):
    """Suma o resta (si monto es negativo) un valor al 'haber' de una cuenta."""
    if not nombre_cuenta or monto == 0:
        return
    try:
        cuenta = Cuenta.objects.get(nombre=nombre_cuenta)
        cuenta.haber = Coalesce(F('haber'), Decimal('0.00')) + monto
        cuenta.save(update_fields=['haber'])
    except Cuenta.DoesNotExist:
        messages.error(request, f"Error Crítico: No se pudo encontrar la cuenta de Pasivo '{nombre_cuenta}'.")

# ===================================================================
# --- VISTA 'mod' (CORREGIDA CON "Cuentas por pagar") ---
# ===================================================================
@transaction.atomic
def mod(request):
    if request.method == "POST":
        action = (request.POST.get("action") or "create").strip()

        if action == "create":
            if ModEmpleado.objects.count() < 30:
                nombre = (request.POST.get("nombre") or "").strip()
                cargo = (request.POST.get("cargo") or "").strip()
                salario_nominal = Decimal(request.POST.get("salario") or "0")
                
                if nombre and cargo and salario_nominal >= 0:
                    # 1. Crear el empleado (guarda el salario NOMINAL)
                    ModEmpleado.objects.create(nombre=nombre, cargo=cargo, salario=salario_nominal)
                    
                    # 2. Calcular componentes del costo
                    costos = calcular_componentes_costo(salario_nominal)
                    
                    # 3. Registrar el asiento contable (Balanceado)
                    nombre_cuenta_gasto = get_cuenta_por_cargo(cargo)
                    
                    # --- DEBE (El Gasto/Costo Total) ---
                    actualizar_debe(request, nombre_cuenta_gasto, costos['costo_total_real'])
                    
                    # --- HABER (Las provisiones y pasivos) ---
                    # (El salario nominal va a "Cuentas por pagar")
                    actualizar_haber(request, "Cuentas por pagar", costos['nominal']) 
                    
                    # El resto de prestaciones
                    actualizar_haber(request, "ISSS por pagar", costos['isss'])
                    actualizar_haber(request, "AFP por pagar", costos['afp'])
                    actualizar_haber(request, "INCAF por pagar", costos['incaf'])
                    actualizar_haber(request, "Aguinaldo por pagar", costos['aguinaldo'])
                    actualizar_haber(request, "Vacaciones por pagar", costos['vacaciones'])
                    # (Asegúrate de tener "Septimo Dia por Pagar" si usas esta línea)
                    actualizar_haber(request, "Septimo Dia por Pagar", costos['septimo']) 
                    
            return redirect("mod")

        if action == "update":
            obj = get_object_or_404(ModEmpleado, pk=request.POST.get("id"))
            
            # --- 1. REVERSAR EL ASIENTO ANTIGUO ---
            salario_nominal_antiguo = obj.salario
            costos_antiguos = calcular_componentes_costo(salario_nominal_antiguo)
            cuenta_gasto_antigua = get_cuenta_por_cargo(obj.cargo)
            
            actualizar_debe(request, cuenta_gasto_antigua, -costos_antiguos['costo_total_real'])
            actualizar_haber(request, "Cuentas por pagar", -costos_antiguos['nominal'])
            actualizar_haber(request, "ISSS por pagar", -costos_antiguos['isss'])
            actualizar_haber(request, "AFP por pagar", -costos_antiguos['afp'])
            actualizar_haber(request, "INCAF por pagar", -costos_antiguos['incaf'])
            actualizar_haber(request, "Aguinaldo por pagar", -costos_antiguos['aguinaldo'])
            actualizar_haber(request, "Vacaciones por pagar", -costos_antiguos['vacaciones'])
            actualizar_haber(request, "Septimo Dia por Pagar", -costos_antiguos['septimo'])
            
            # --- 2. OBTENER NUEVOS VALORES ---
            nuevo_nombre = (request.POST.get("nombre") or "").strip()
            nuevo_cargo = (request.POST.get("cargo") or "").strip()
            nuevo_salario_nominal = Decimal(request.POST.get("salario") or "0")
            
            # 3. Actualizar el empleado (con salario NOMINAL)
            obj.nombre = nuevo_nombre
            obj.cargo = nuevo_cargo
            obj.salario = nuevo_salario_nominal
            obj.save()
            
            # --- 4. CREAR EL NUEVO ASIENTO ---
            costos_nuevos = calcular_componentes_costo(nuevo_salario_nominal)
            cuenta_gasto_nueva = get_cuenta_por_cargo(nuevo_cargo)
            
            actualizar_debe(request, cuenta_gasto_nueva, costos_nuevos['costo_total_real'])
            actualizar_haber(request, "Cuentas por pagar", costos_nuevos['nominal'])
            actualizar_haber(request, "ISSS por pagar", costos_nuevos['isss'])
            actualizar_haber(request, "AFP por pagar", costos_nuevos['afp'])
            actualizar_haber(request, "INCAF por pagar", costos_nuevos['incaf'])
            actualizar_haber(request, "Aguinaldo por pagar", costos_nuevos['aguinaldo'])
            actualizar_haber(request, "Vacaciones por pagar", costos_nuevos['vacaciones'])
            actualizar_haber(request, "Septimo Dia por Pagar", costos_nuevos['septimo'])
                
            return redirect("mod")

        if action == "delete":
            obj = get_object_or_404(ModEmpleado, pk=request.POST.get("id"))
            
            # --- 1. OBTENER DATOS Y REVERSAR EL ASIENTO ---
            salario_nominal = obj.salario
            costos = calcular_componentes_costo(salario_nominal)
            nombre_cuenta_gasto = get_cuenta_por_cargo(obj.cargo)
            
            actualizar_debe(request, nombre_cuenta_gasto, -costos['costo_total_real'])
            actualizar_haber(request, "Cuentas por pagar", -costos['nominal'])
            actualizar_haber(request, "ISSS por pagar", -costos['isss'])
            actualizar_haber(request, "AFP por pagar", -costos['afp'])
            actualizar_haber(request, "INCAF por pagar", -costos['incaf'])
            actualizar_haber(request, "Aguinaldo por pagar", -costos['aguinaldo'])
            actualizar_haber(request, "Vacaciones por pagar", -costos['vacaciones'])
            actualizar_haber(request, "Septimo Dia por Pagar", -costos['septimo'])
            
            # 2. Borrar el empleado
            obj.delete()
            
            return redirect("mod")

    # --- LÓGICA GET (sin cambios) ---
    empleados = ModEmpleado.objects.order_by("id")
    total_salarios = empleados.aggregate(total=Sum("salario"))["total"] or Decimal("0")
    return render(request, "mod.html", {"empleados": empleados, "total_salarios": total_salarios})
    
logger = logging.getLogger(__name__)

def estimacion_ifpug(request):
    
    if request.method == 'POST':
        try:
            payload_str = request.POST.get('payload')
            if not payload_str:
                messages.error(request, "No se recibió ningún 'payload' con datos.")
                return redirect('estimacion')

            data = json.loads(payload_str)
            costo_a_guardar = data.get('costos', {}).get('precio_sugerido')

            if costo_a_guardar is None:
                messages.error(request, "El 'payload' no contenía un 'precio_sugerido'.")
                return redirect('estimacion')

            nuevo_costo = Decimal(costo_a_guardar)

            # --- LÓGICA DE GUARDADO MODIFICADA ---
            # Ya no buscamos un periodo.
            # Actualizamos la cuenta "Costo estimado" directamente.
            
            # 1. Buscamos la cuenta
            cuenta_costo = Cuenta.objects.get(nombre="Costo estimado") 

            # 2. Actualizamos sus campos 'debe' y 'haber'
            cuenta_costo.debe = nuevo_costo
            cuenta_costo.haber = Decimal('0.00')
            
            # 3. Guardamos solo esos campos en la tabla SIC_cuenta
            cuenta_costo.save(update_fields=['debe', 'haber'])
            
            # --- FIN DE LA LÓGICA MODIFICADA ---
            
            messages.success(request, f"¡Éxito! El 'debe' de la cuenta 'Costo estimado' se actualizó a ${nuevo_costo:,.2f}.")

        except Cuenta.DoesNotExist:
            messages.error(request, "Error crítico: La cuenta 'Costo estimado' no existe.")
        except Exception as e:
            messages.error(request, f"Error inesperado al guardar: {e}")
            logger.error(f"Error en estimacion_ifpug POST: {e}")
        
        return redirect('estimacion')

    # --- 2) LÓGICA GET (Esta parte sigue igual) ---
    
    roles_mod = []


    try:
        with connection.cursor() as cur:
            cur.execute("""
            SELECT cargo, salario
            FROM public."SIC_modempleado"
            WHERE cargo IS NOT NULL ORDER BY cargo;
            """)
            for cargo, salario in cur.fetchall():
                roles_mod.append({
                    "cargo": cargo,
                    "salario_real_mensual": float(salario or 0),
                })
                print("rol",cargo)
        cargos_permitidos = {
        "Tester QA",
        "Desarrollador senior",
        "Desarrollador junior",
        "Líder técnico",
    }

        roles_filtrados = [r for r in roles_mod if r["cargo"] in cargos_permitidos]

        # --- 3) Controlar la cantidad de Desarrolladores junior ---
        desarrolladores_junior = [r for r in roles_filtrados if r["cargo"] == "Desarrollador junior"][:6]
        otros_roles = [r for r in roles_filtrados if r["cargo"] != "Desarrollador junior"]
        
        # Combinar los dos grupos
        roles_unicos = []
        vistos = set()
        for r in roles_filtrados:
            if r["cargo"] not in vistos:
                roles_unicos.append(r)
                vistos.add(r["cargo"])
    
        # --- 3) Reemplazar roles_mod con la versión sin duplicados ---
        roles_mod = roles_unicos
        print(roles_mod)
        total_cif = Cif.objects.aggregate(s=Sum('monto'))['s'] or 0
        
    except Exception as e:
        logger.error(f"Error en la lógica GET de estimacion_ifpug: {e}")
        messages.error(request, f"Error al cargar datos iniciales (roles o CIF): {e}.")
        roles_mod = []
        total_cif = 0.0

    ctx = {
        "roles_mod": json.dumps(roles_mod), 
        "total_cif": float(total_cif),
    }
    return render(request, "estimacion.html", ctx)

def resultados(request):
    periodos = Periodo.objects.filter(cerrado=True).order_by('-fecha_inicio')
    cuentas_resultado = []
    periodo_seleccionado = None
    total_debe = Decimal('0.00')
    total_haber = Decimal('0.00')
    resultado = Decimal('0.00')
    periodo_id = request.GET.get('periodo')
    
    if periodo_id:
        try:
            periodo_seleccionado = Periodo.objects.get(id=periodo_id)
            
            # --- CONSULTA CORREGIDA ---
            cuentas_resultado = BalanceComprobacion.objects.filter(
                periodo=periodo_seleccionado,
                cuenta__tipo__in=['ING', 'GAS'],
                cuenta__automatica=False  # <-- ¡FILTRO AÑADIDO!
            ).select_related('cuenta')
            # --- FIN DE LA CORRECCIÓN ---
            
            if cuentas_resultado:
                totales = cuentas_resultado.aggregate(
                    total_debe_calc=Sum('debe'),
                    total_haber_calc=Sum('haber')
                )
                total_debe = totales.get('total_debe_calc') or Decimal('0.00')
                total_haber = totales.get('total_haber_calc') or Decimal('0.00')
                resultado = total_haber - total_debe
                
        except Periodo.DoesNotExist:
            periodo_seleccionado = None 
            
    contexto = {
        'periodos': periodos,
        'periodo_seleccionado': periodo_seleccionado,
        'cuentas_resultado': cuentas_resultado,
        'total_debe': total_debe,
        'total_haber': total_haber,
        'resultado': resultado,
    }
    return render(request, 'resultados.html', contexto)
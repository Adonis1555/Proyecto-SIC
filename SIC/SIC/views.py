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
    ISSS_TOPE = Decimal('1000') # (s / 30) * 4.3333
    VAC_DIAS = Decimal('1.25') # (s / 30) * 1.25
    INCAF = Decimal('0.01')
    TREINTA = Decimal('30')

    # Cálculos de prestaciones
    afp  = s * AFP
    isss = min(s, ISSS_TOPE) * ISSS
    agui = s * AGUI
    vac  = (s / TREINTA) * VAC_DIAS
    incf = s * INCAF

    # Suma total (Costo Real)
    costo_real = s + afp + isss  + agui + vac + incf
    
    # Redondeamos a 2 decimales por si acaso
    return costo_real.quantize(Decimal('0.01'))

# ... (importaciones) ...

@transaction.atomic
def transacciones(request):
    # ============================================================
    # PERIODO ABIERTO O FECHAS POR DEFECTO
    # ============================================================
    periodo_abierto = Periodo.objects.filter(cerrado=False).order_by('-fecha_inicio').first()
    
    if periodo_abierto:
        primer_dia = periodo_abierto.fecha_inicio
        ultimo_dia = periodo_abierto.fecha_fin
    else:
        hoy = timezone.now().date()
        primer_dia = hoy.replace(day=1)
        ultimo_dia = monthrange(hoy.year, hoy.month)[1] 

    # ============================================================
    # POST → GUARDAR TRANSACCIÓN
    # ============================================================
    if request.method == 'POST':
        form = TransaccionForm(request.POST, primer_dia=primer_dia, ultimo_dia=ultimo_dia)
        if form.is_valid():
            transaccion = form.save(commit=False)
            transaccion.periodo = periodo_abierto
            transaccion.fecha = form.cleaned_data['fecha']
            transaccion.save()

            # ============================================================
            # ACTUALIZAR SALDO EN VIVO DE LA CUENTA PRINCIPAL
            # ============================================================
            try:
                cuenta_a_actualizar = transaccion.cuenta
                monto = transaccion.monto
                
                if transaccion.tipo == 'Debe':
                    cuenta_a_actualizar.debe = Coalesce(F('debe'), Decimal('0.00')) + monto
                    cuenta_a_actualizar.save(update_fields=['debe'])
                else:
                    cuenta_a_actualizar.haber = Coalesce(F('haber'), Decimal('0.00')) + monto
                    cuenta_a_actualizar.save(update_fields=['haber'])
            
            except Exception as e:
                messages.error(request, f"Error al actualizar el saldo en vivo: {e}")
                raise e

            # ============================================================
            # 🧮 ECUACIÓN CONTABLE → (BLOQUE ELIMINADO POR SER INCORRECTO)
            # ============================================================
            # (¡Correcto que esté eliminado!)


            # ====================================================================
            # --- LÓGICA DE COSTO (TU NUEVA IDEA - "CONSTANTE") ---
            # (REEMPLAZA la lógica vieja de 'Variación vs Bancos')
            # ====================================================================
            
            # Si la transacción es una VENTA (Ingreso en Haber)...
            if transaccion.cuenta.codigo == '501' and transaccion.tipo == 'Haber':
                try:
                    # 1. Obtenemos la "constante" guardada en la cuenta Costo Estimado
                    cuenta_costo = Cuenta.objects.get(nombre="Costo estimado")
                    # (Usamos .saldo, que es donde 'estimacion_ifpug' (v25) lo guarda)
                    costo_constante = cuenta_costo.saldo or Decimal('0.00')

                    # 2. Obtenemos la contrapartida
                    cuenta_software = Cuenta.objects.get(codigo="1107") # Software en proceso

                    if costo_constante > 0:
                        # 3. Registramos el Gasto (Debe) en el saldo "en vivo"
                        cuenta_costo.debe = Coalesce(F('debe'), Decimal('0.00')) + costo_constante
                        cuenta_costo.save(update_fields=['debe'])
                        
                        # 4. Registramos la Contrapartida (Haber) en el saldo "en vivo"
                        cuenta_software.haber = Coalesce(F('haber'), Decimal('0.00')) + costo_constante
                        cuenta_software.save(update_fields=['haber'])

                        # 5. Creamos el historial de la transacción de costo
                        Transaccion.objects.create(
                            fecha=transaccion.fecha,
                            cuenta=cuenta_costo,
                            descripcion="Costo estimado automático por venta",
                            monto=costo_constante,
                            tipo='Debe',
                            periodo=periodo_abierto,
                            exento_iva=True
                        )
                        Transaccion.objects.create(
                            fecha=transaccion.fecha,
                            cuenta=cuenta_software,
                            descripcion="Software en Proceso",
                            monto=costo_constante,
                            tipo='Haber',
                            periodo=periodo_abierto,
                            exento_iva=True
                        )
                        
                        messages.success(request, f"Venta registrada. Costo de ${costo_constante:,.2f} aplicado (Debe: Costo, Haber: Software).")
                    else:
                        messages.warning(request, "Venta registrada, pero el Costo Estimado (la 'constante') es CERO. El costo no fue aplicado.")

                except Cuenta.DoesNotExist as e:
                    messages.error(request, f"Error Crítico: No se encontró 'Costo estimado' (601) o 'Software en proceso' (1107). ({e}).")
                except Exception as e:
                    messages.error(request, f"Error inesperado al aplicar el costo constante: {e}")

            # ============================================================
            # --- FIN LÓGICA DE COSTO ---
            # ============================================================


            # ============================================================
            # LÓGICA DE IVA (SIN CAMBIOS, ES CORRECTA)
            # ============================================================
            if not transaccion.exento_iva and transaccion.cuenta.tipo in ['ACT', 'PAS']:
                
                iva_rate = Decimal('0.13')
                iva_monto = transaccion.monto * iva_rate
                transaccion.monto = iva_monto + transaccion.monto
                transaccion.save(update_fields=['monto'])
                try:
                    if transaccion.tipo == 'Debe':
                        transaccion.cuenta.debe = Coalesce(F('debe'), Decimal('0.00')) + iva_monto
                        transaccion.cuenta.save(update_fields=['debe'])
                    else:
                        transaccion.cuenta.haber = Coalesce(F('haber'), Decimal('0.00')) + iva_monto
                        transaccion.cuenta.save(update_fields=['haber'])
                except Exception as e:
                    messages.error(request, f"Error al aplicar IVA: {e}")
                    raise e

                if transaccion.tipo == 'Haber':
                    iva_cuenta = Cuenta.objects.get(codigo='1106') # IVA Crédito
                    tipo_iva = 'Debe'
                    desc_iva = "Aplicando IVA (Crédito Fiscal)"
                else:
                    iva_cuenta = Cuenta.objects.get(codigo='2111') # IVA Débito
                    tipo_iva = 'Haber'
                    desc_iva = "Aplicando IVA (Débito Fiscal)"

                Transaccion.objects.create(
                    fecha=transaccion.fecha,
                    cuenta=iva_cuenta,
                    descripcion=desc_iva,
                    monto=iva_monto,
                    tipo=tipo_iva,
                    periodo=periodo_abierto,
                    exento_iva=True
                )

                if tipo_iva == 'Debe':
                    iva_cuenta.debe = Coalesce(F('debe'), Decimal('0.00')) + iva_monto
                    iva_cuenta.save(update_fields=['debe'])
                else:
                    iva_cuenta.haber = Coalesce(F('haber'), Decimal('0.00')) + iva_monto
                    iva_cuenta.save(update_fields=['haber'])


            return redirect('transacciones')
    else:
        form = TransaccionForm(primer_dia=primer_dia, ultimo_dia=ultimo_dia)

    # ============================================================
    # GET → LISTAR TRANSACCIONES (SIN CAMBIOS)
    # ============================================================
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

def BalanceC(request):
    periodos = Periodo.objects.filter(cerrado=True).order_by('-fecha_inicio')
    
    # --- Lógica de selección de período (con default) ---
    periodo_seleccionado = None
    periodo_id = request.GET.get('periodo')
    if periodo_id:
        try:
            periodo_seleccionado = Periodo.objects.get(id=periodo_id, cerrado=True)
        except Periodo.DoesNotExist:
            pass 
    if not periodo_seleccionado and periodos.exists():
        periodo_seleccionado = periodos.first()
    # --- Fin Lógica de selección ---

    cierres = []
    total_debe = Decimal('0.00')
    total_haber = Decimal('0.00')

    if periodo_seleccionado:
        
        # --- Cuentas a Ocultar ---
        codigos_a_ocultar = [
            '3103', # Pérdidas y Ganancias
            '609', '610', '612', '613', # Gastos de Depreciación
            '1108', '1109', '1110', '1111', '41'# Depreciación Acumulada
        ]
        
        cierres = BalanceComprobacion.objects.filter(
            periodo=periodo_seleccionado
        ).exclude(
            # Excluye las cuentas "raíz"
            cuenta__cuenta_padre_id__isnull=True
        ).exclude(
            # ¡AQUÍ! Excluye PyG y todas las de Depreciación
            cuenta__codigo__in=codigos_a_ocultar
        ).order_by('cuenta__codigo')

        # ¡OJO! Los totales seguirán desbalanceados
        # porque estamos quitando cuentas
        totales_filtrados = cierres.aggregate(
            sum_debe=Sum('debe'),
            sum_haber=Sum('haber')
        )
        total_debe = totales_filtrados.get('sum_debe') or Decimal('0.00')
        total_haber = totales_filtrados.get('sum_haber') or Decimal('0.00')

    contexto = {
        'periodos': periodos,
        'periodo_seleccionado': periodo_seleccionado,
        'cierres': cierres,
        'total_debe': total_debe,
        'total_haber': total_haber
    }

    return render(request, 'BalanceC.html', contexto)
def BalanceG(request):
    periodos = Periodo.objects.filter(cerrado=True).order_by('-fecha_inicio')
    periodo_id = request.GET.get('periodo')
    periodo_seleccionado = None
    cuentas_activo = cuentas_pasivo = cuentas_patrimonio = []

    if periodo_id:
        periodo_seleccionado = Periodo.objects.filter(id=periodo_id).first()

        if periodo_seleccionado:
            # --- Activos ---
            cuentas_activo = BalanceComprobacion.objects.filter(
                periodo=periodo_seleccionado,
                cuenta__tipo='ACT'
            ).exclude(
                cuenta__cuenta_padre_id__isnull=True
            ).select_related('cuenta')

            # --- Pasivos ---
            cuentas_pasivo = BalanceComprobacion.objects.filter(
                periodo=periodo_seleccionado,
                cuenta__tipo='PAS'
            ).exclude(
                cuenta__cuenta_padre_id__isnull=True
            ).select_related('cuenta')

            # --- Patrimonio ---
            cuentas_patrimonio = BalanceComprobacion.objects.filter(
                periodo=periodo_seleccionado,
                cuenta__tipo='CAP'
            ).exclude(
                cuenta__cuenta_padre_id__isnull=True
            ).select_related('cuenta')

    # Totales
    total_activo = sum((c.debe or 0) - (c.haber or 0) for c in cuentas_activo)
    total_pasivo = sum((c.haber or 0) - (c.debe or 0) for c in cuentas_pasivo)
    total_patrimonio = sum((c.haber or 0) - (c.debe or 0) for c in cuentas_patrimonio)
    total_pasivo_patrimonio = total_pasivo + total_patrimonio

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



def estimacion(request):
    return render(request, 'estimacion.html')


@transaction.atomic
def cerrar_periodo_view(request):
    """
    Cierre de período contable (v24 - Arrastre de PyG Corregido):
    - PASO 7:   Calcula el resultado del mes y lo NETEA con el saldo arrastrado de PyG.
    - PASO 10:  Calcula la distribución (Capital/Reserva) basándose
                en la UTILIDAD NETA FINAL (no solo la del mes).
    - El resto de la lógica (v22) se mantiene.
    """
    if request.method == "POST":
        
        # --- 1️⃣ Identificar período y transacciones ---
        periodo_abierto = Periodo.objects.filter(cerrado=False).order_by('-fecha_inicio').first()
        if periodo_abierto:
            transacciones_a_cerrar = Transaccion.objects.filter(periodo=periodo_abierto)
            fecha_base = periodo_abierto.fecha_inicio
        else:
            transacciones_a_cerrar = Transaccion.objects.filter(periodo__isnull=True)
            fecha_base = timezone.now().date()

        # --- 2️⃣ VALIDACIÓN DE PARTIDA DOBLE ("El Guardia") ---
        VALOR_TIPO_DEBITO = 'Debe'
        VALOR_TIPO_HABER = 'Haber'
        saldos_periodo = transacciones_a_cerrar.aggregate(
            total_debe=Sum(Case(When(tipo=VALOR_TIPO_DEBITO, then=F('monto')), default=Value(0), output_field=DecimalField())),
            total_haber=Sum(Case(When(tipo=VALOR_TIPO_HABER, then=F('monto')), default=Value(0), output_field=DecimalField()))
        )
        total_debe_periodo = saldos_periodo['total_debe'] or Decimal('0.00')
        total_haber_periodo = saldos_periodo['total_haber'] or Decimal('0.00')
        
        if abs(total_debe_periodo - total_haber_periodo) > Decimal('0.01'):
            messages.error(request, f"❌ Error: Las transacciones del período no están cuadradas. Revise la vista 'transacciones'.")
            return redirect('estados') 

        # --- 3️⃣ Guardar y cerrar período ---
        if periodo_abierto:
            ultimo_dia = monthrange(fecha_base.year, fecha_base.month)[1]
            periodo_abierto.fecha_fin = fecha_base.replace(day=ultimo_dia)
            periodo_abierto.cerrado = True
            periodo_abierto.nombre = f"Cierre {fecha_base.strftime('%B %Y')}"
            periodo_abierto.save()
            periodo_cerrado = periodo_abierto
        else:
            ultimo_dia = monthrange(fecha_base.year, fecha_base.month)[1]
            periodo_cerrado = Periodo.objects.create(
                nombre=f"Cierre {fecha_base.strftime('%B %Y')}",
                fecha_inicio=fecha_base.replace(day=1),
                fecha_fin=fecha_base.replace(day=ultimo_dia),
                cerrado=True
            )

        
        # --- PASO 3.5: AUTOMATIZAR DEPRECIACIÓN (Lógica Correcta v22) ---
        montos_depreciacion = {
            '609': Decimal('200.00'),  # Gasto Comp.
            '610': Decimal('38.33'),   # Gasto Oficina
            '612': Decimal('58.33'),   # Gasto Mobiliario
            '613': Decimal('14.58'),   # Gasto Seguridad
        }
        mapa_contrapartidas = {
            '609': '1108', '610': '1110', '612': '1109', '613': '1111',
        }

        try:
            for codigo_gasto, monto_mensual in montos_depreciacion.items():
                cuenta_gasto = Cuenta.objects.get(codigo=codigo_gasto)
                codigo_acumulada = mapa_contrapartidas[codigo_gasto]
                cuenta_acumulada = Cuenta.objects.get(codigo=codigo_acumulada)

                cuenta_gasto.debe = Coalesce(F('debe'), Decimal('0.00')) + monto_mensual
                cuenta_acumulada.haber = Coalesce(F('haber'), Decimal('0.00')) + monto_mensual
                cuenta_gasto.save(update_fields=['debe'])
                cuenta_acumulada.save(update_fields=['haber'])
                
                Transaccion.objects.create(
                    fecha=fecha_base, cuenta=cuenta_gasto, descripcion="Depreciación automática mensual",
                    monto=monto_mensual, tipo='Debe', periodo=periodo_cerrado, exento_iva=True
                )
                Transaccion.objects.create(
                    fecha=fecha_base, cuenta=cuenta_acumulada, descripcion="Depreciación automática mensual",
                    monto=monto_mensual, tipo='Haber', periodo=periodo_cerrado, exento_iva=True
                )
            messages.info(request, "Depreciación mensual registrada automáticamente.")
        except Cuenta.DoesNotExist as e:
            messages.error(request, f"Error al depreciar: No se encontró una cuenta (ej: {e}). El cierre se detiene.")
            transaction.set_rollback(True); return redirect('estados') 
        except Exception as e:
            messages.error(request, f"Error inesperado en depreciación: {e}")
            transaction.set_rollback(True); return redirect('estados') 

        # --- 4️⃣ Cálculo de Ingresos y Gastos + Variación ---
        # (Se calcula el resultado DE ESTE MES)
        try:
            cuenta_variacion = Cuenta.objects.get(nombre__icontains="variación entre costo estimado y real")
        except Cuenta.DoesNotExist:
            cuenta_variacion = None
        cuentas_ingreso = Cuenta.objects.filter(tipo='ING').exclude(id=cuenta_variacion.id if cuenta_variacion else None)
        total_ingresos = cuentas_ingreso.aggregate(
            total=Sum(Coalesce(F('haber'), Value(0), output_field=DecimalField(max_digits=15, decimal_places=2)))
        )['total'] or Decimal('0.00')
        cuentas_gasto = Cuenta.objects.filter(tipo='GAS').exclude(id=cuenta_variacion.id if cuenta_variacion else None)
        total_gastos = cuentas_gasto.aggregate(
            total=Sum(Coalesce(F('debe'), Value(0), output_field=DecimalField(max_digits=15, decimal_places=2)))
        )['total'] or Decimal('0.00')
        if cuenta_variacion:
            cuenta_variacion.refresh_from_db() # Carga el saldo de 'estimacion_ifpug'
            total_ingresos += cuenta_variacion.haber or 0
            total_gastos += cuenta_variacion.debe or 0

        resultado_del_periodo = total_ingresos - total_gastos # Resultado SOLO de este mes

        # --- 5️⃣ Obtener cuentas clave ---
        cuenta_pyg = Cuenta.objects.get(codigo='3103')
        cuenta_capital = Cuenta.objects.filter(codigo='3101').first()
        cuenta_reserva = Cuenta.objects.filter(codigo='3102').first()

        # --- 6️⃣ Guardar snapshot y Resetear cuentas (ING, GAS, VAR) ---
        for cuenta in Cuenta.objects.all():
            cuenta.refresh_from_db() 
            saldo_debe = cuenta.debe or 0
            saldo_haber = cuenta.haber or 0
            if saldo_debe > saldo_haber: debe_final = saldo_debe - saldo_haber; haber_final = 0
            elif saldo_haber > saldo_debe: haber_final = saldo_haber - saldo_debe; debe_final = 0
            else: debe_final = haber_final = 0
            BalanceComprobacion.objects.update_or_create(
                periodo=periodo_cerrado,
                cuenta=cuenta,
                defaults={'debe': debe_final, 'haber': haber_final}
            )
            
            # ¡AQUÍ SE RESETEA EL GASTO (GAS)!
            if cuenta.tipo in ['ING', 'GAS'] or (cuenta_variacion and cuenta == cuenta_variacion):
                if (cuenta_variacion and cuenta == cuenta_variacion) or ("costo estimado" not in cuenta.nombre.lower()):
                    cuenta.debe = 0
                    cuenta.haber = 0
                    cuenta.save(update_fields=['debe', 'haber'])

        
        # =================================================================
        # --- PASO 7: APLICAR RESULTADO (Lógica NETEADA v24) ---
        # =================================================================
        
        # 1. Obtenemos el saldo ARRASTRADO de PyG (ej: Debe=622.48, Haber=0)
        saldo_debe_arrastrado = cuenta_pyg.debe or 0
        saldo_haber_arrastrado = cuenta_pyg.haber or 0

        # 2. Aplicamos el resultado DE ESTE MES (ej: Ganancia +1910.22)
        if resultado_del_periodo < 0:  # Pérdida este mes
            saldo_debe_arrastrado += abs(resultado_del_periodo)
        elif resultado_del_periodo > 0:  # Ganancia este mes
            saldo_haber_arrastrado += resultado_del_periodo
        
        # 3. Calculamos el saldo NETO FINAL
        saldo_final_debe_pyg = Decimal('0.00')
        saldo_final_haber_pyg = Decimal('0.00')
        
        if saldo_debe_arrastrado > saldo_haber_arrastrado:
            # Pérdida neta final
            saldo_final_debe_pyg = saldo_debe_arrastrado - saldo_haber_arrastrado
        else:
            # Ganancia neta final
            saldo_final_haber_pyg = saldo_haber_arrastrado - saldo_debe_arrastrado
            
        # 4. Guardamos el saldo NETO FINAL en la cuenta y el snapshot
        cuenta_pyg.debe = saldo_final_debe_pyg
        cuenta_pyg.haber = saldo_final_haber_pyg
            
        BalanceComprobacion.objects.update_or_create(
            periodo=periodo_cerrado,
            cuenta=cuenta_pyg,
            defaults={'debe': cuenta_pyg.debe, 'haber': cuenta_pyg.haber}
        )
        cuenta_pyg.save(update_fields=['debe', 'haber'])
        
        # =================================================================
        # --- FIN PASO 7 ---
        # =================================================================

        # --- 9️⃣ Cerrar transacciones (humanas) ---
        transacciones_a_cerrar.update(periodo=periodo_cerrado)

        # =================================================================
        # --- PASO 10: APERTURA (Lógica v24) ---
        # =================================================================
        primer_dia_sig = (fecha_base.replace(day=1) + timezone.timedelta(days=32)).replace(day=1)
        ultimo_dia_sig = monthrange(primer_dia_sig.year, primer_dia_sig.month)[1]
        nuevo_periodo = Periodo.objects.create(
            nombre=f"Periodo {primer_dia_sig.strftime('%B %Y')}",
            fecha_inicio=primer_dia_sig,
            fecha_fin=primer_dia_sig.replace(day=ultimo_dia_sig),
            cerrado=False
        )

        # 10.A: Calcular distribución basada en la GANANCIA NETA FINAL
        # (utilidad_neta_final = saldo_final_haber_pyg - saldo_final_debe_pyg)
        utilidad_neta_final = cuenta_pyg.haber - cuenta_pyg.debe 

        reserva_a_traspasar = Decimal('0.00')
        capital_a_traspasar = Decimal('0.00')
        
        # Solo distribuimos si la UTILIDAD NETA FINAL fue positiva
        if utilidad_neta_final > 0 and cuenta_capital and cuenta_reserva:
            reserva_a_traspasar = utilidad_neta_final * Decimal('0.20')
            capital_a_traspasar = utilidad_neta_final * Decimal('0.80')

        ids_especiales = [cuenta_pyg.id]
        if cuenta_capital: ids_especiales.append(cuenta_capital.id)
        if cuenta_reserva: ids_especiales.append(cuenta_reserva.id)

        cuentas_normales = Cuenta.objects.filter(tipo__in=['ACT', 'PAS', 'CAP']).exclude(id__in=ids_especiales)

        for cuenta in cuentas_normales:
            cuenta.refresh_from_db() 
            BalanceComprobacion.objects.create(
                periodo=nuevo_periodo,
                cuenta=cuenta,
                debe=cuenta.debe or 0,
                haber=cuenta.haber or 0 
            )

        # 10.B: Traspaso de Capital (sumando la ganancia neta)
        if cuenta_capital:
            cuenta_capital.refresh_from_db()
            nuevo_haber_cap = (cuenta_capital.haber or 0) + capital_a_traspasar
            cuenta_capital.haber = nuevo_haber_cap
            cuenta_capital.debe = 0
            cuenta_capital.save(update_fields=['haber', 'debe'])
            BalanceComprobacion.objects.create(
                periodo=nuevo_periodo,
                cuenta=cuenta_capital,
                debe=0,
                haber=nuevo_haber_cap
            )

        # 10.C: Traspaso de Reserva (sumando la ganancia neta)
        if cuenta_reserva:
            cuenta_reserva.refresh_from_db()
            nuevo_haber_res = (cuenta_reserva.haber or 0) + reserva_a_traspasar
            cuenta_reserva.haber = nuevo_haber_res
            cuenta_reserva.debe = 0
            cuenta_reserva.save(update_fields=['haber', 'debe'])
            BalanceComprobacion.objects.create(
                periodo=nuevo_periodo,
                cuenta=cuenta_reserva,
                debe=0,
                haber=nuevo_haber_res
            )

        # 10.D: Traspaso de PyG
        if utilidad_neta_final > 0: 
            # Hubo GANANCIA NETA y se distribuyó. PyG empieza en CERO.
            cuenta_pyg.debe = 0
            cuenta_pyg.haber = 0
            cuenta_pyg.save(update_fields=['debe', 'haber'])
            BalanceComprobacion.objects.create(
                periodo=nuevo_periodo,
                cuenta=cuenta_pyg,
                debe=0,
                haber=0
            )
        else: 
            # Hubo PÉRDIDA NETA. El saldo (Debe) se arrastra.
            cuenta_pyg.refresh_from_db() # Ya tiene el saldo neto (ej: Debe=622.48)
            BalanceComprobacion.objects.create(
                periodo=nuevo_periodo,
                cuenta=cuenta_pyg,
                debe=cuenta_pyg.debe, # Arrastra la pérdida neta
                haber=cuenta_pyg.haber
            )
        
        messages.success(request, f"✅ Cierre completado. Resultado del Mes: ${resultado_del_periodo:,.2f}. Utilidad Neta Final: ${utilidad_neta_final:,.2f}")
        return redirect(f"{reverse('comprobacion')}?periodo={periodo_cerrado.id}")

    else:
        periodos = Periodo.objects.all().order_by('-fecha_inicio')
        return render(request, 'EstadosFinancieros.html', {'periodos': periodos})
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
    "Desarrollador junior", "Desarrollador senior",
    "Líder técnico", "Tester QA",
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
    VAC_DIAS = Decimal('1.25') # (s / 30) * 1.25
    INCAF = Decimal('0.01')
    TREINTA = Decimal('30')

    # Cálculos de prestaciones
    afp  = s * AFP
    isss = min(s, ISSS_TOPE) * ISSS
    agui = s * AGUI
    vac  = (s / TREINTA) * VAC_DIAS
    incf = s * INCAF

    # Suma total (Costo Real)
    costo_real = s + afp + isss + agui + vac + incf
    
    return {
        'nominal': s,
        'afp': afp.quantize(Decimal('0.01')),
        'isss': isss.quantize(Decimal('0.01')),
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
            
            # 2. Borrar el empleado
            obj.delete()
            
            return redirect("mod")

    # --- LÓGICA GET (sin cambios) ---
    empleados = ModEmpleado.objects.order_by("id")
    total_salarios = empleados.aggregate(total=Sum("salario"))["total"] or Decimal("0")
    return render(request, "mod.html", {"empleados": empleados, "total_salarios": total_salarios})
    
logger = logging.getLogger(__name__)

@transaction.atomic # ¡Importante!
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

            # ==========================================================
            # --- LÓGICA DE "CONSTANTE" (TU IDEA) ---
            # ==========================================================
            
            # 1. Buscamos la cuenta
            cuenta_costo = Cuenta.objects.get(nombre="Costo estimado") # Gasto (Debe)
 
            # 2. Actualizamos el campo 'saldo' (la "constante")
            #    ¡NO TOCAMOS DEBE NI HABER! Así no se desbalancea NADA.
            cuenta_costo.saldo = nuevo_costo
            
            # 3. Guardamos solo ese campo
            cuenta_costo.save(update_fields=['saldo'])
            
            # --- FIN DE LA LÓGICA MODIFICADA ---
            
            messages.success(request, f"¡Éxito! El costo 'constante' de {cuenta_costo.nombre} se actualizó a ${nuevo_costo:,.2f}.")

        except Cuenta.DoesNotExist:
            messages.error(request, "Error crítico: No se encontró 'Costo estimado' (601)")
        except Exception as e:
            messages.error(request, f"Error inesperado al guardar: {e}")
            # logger.error(f"Error en estimacion_ifpug POST: {e}")
        
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
        
        cargos_permitidos = {
            "Tester QA",
            "Desarrollador senior",
            "Desarrollador junior",
            "Líder técnico",
        }

        roles_filtrados = [r for r in roles_mod if r["cargo"] in cargos_permitidos]
        
        # ... (Tu lógica de filtrado de roles únicos) ...
        roles_unicos = []
        vistos = set()
        for r in roles_filtrados:
            if r["cargo"] not in vistos:
                roles_unicos.append(r)
                vistos.add(r["cargo"])
        roles_mod = roles_unicos
        
        total_cif = Cif.objects.aggregate(s=Sum('monto'))['s'] or 0
        
    except Exception as e:
        # logger.error(f"Error en la lógica GET de estimacion_ifpug: {e}")
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

    # --- LÓGICA DE SELECCIÓN DE PERÍODO (MEJORADA) ---
    periodo_id = request.GET.get('periodo')
    if periodo_id:
        try:
            periodo_seleccionado = Periodo.objects.get(id=periodo_id, cerrado=True)
        except Periodo.DoesNotExist:
            pass # Se usará el default
    
    if not periodo_seleccionado and periodos.exists():
        periodo_seleccionado = periodos.first() # Carga el más reciente por defecto
    # --- FIN LÓGICA DE SELECCIÓN ---
    
    if periodo_seleccionado:
        
        # --- CONSULTA CORREGIDA (SIN FILTRO 'automatica') ---
        cuentas_resultado = BalanceComprobacion.objects.filter(
            periodo=periodo_seleccionado,
            cuenta__tipo__in=['ING', 'GAS']
            # ¡FILTRO ELIMINADO! Ahora mostrará las cuentas automáticas.
        ).select_related('cuenta').order_by('cuenta__codigo')
        # --- FIN DE LA CORRECCIÓN ---
        
        if cuentas_resultado:
            totales = cuentas_resultado.aggregate(
                total_debe_calc=Sum('debe'),
                total_haber_calc=Sum('haber')
            )
            total_debe = totales.get('total_debe_calc') or Decimal('0.00')
            total_haber = totales.get('total_haber_calc') or Decimal('0.00')
            
            # Resultado (Ingresos - Gastos)
            resultado = total_haber - total_debe
                
    contexto = {
        'periodos': periodos,
        'periodo_seleccionado': periodo_seleccionado,
        'cuentas_resultado': cuentas_resultado,
        'total_debe': total_debe,
        'total_haber': total_haber,
        'resultado': resultado,
    }
    return render(request, 'resultados.html', contexto)
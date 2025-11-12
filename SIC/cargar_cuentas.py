import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SIC.settings')
django.setup()

from SIC.models import Cuenta

def cargar_catalogo():
    cuentas = [
        # --- ACTIVO ---
        ("1", "Activo", 0, 0, 0, None, True),
        ("11", "Activo Corriente", 0, 0, 0, "1", True),
        ("1101", "Caja", 0, 5000, 0, "11", False),
        ("1102", "Bancos", 0, 5000, 0, "11", False),
        ("1103", "Cuentas por cobrar", 0, 0, 0, "11", False),
        ("1104", "Deudores varios", 0, 0, 0, "11", False),
        ("1105", "Inventario de suministros", 0, 0, 0, "11", False),
        ("1106", "IVA crédito fiscal", 0, 0, 0, "11", True),
        ("1107", "Software en proceso", 0, 0, 0, "11", False),
        ("1108", "Depreciación acumulada de equipos de cómputo", 0, 0, 0, "11", True),
        ("1109", "Depreciación acumulada de mobiliario", 0, 0, 0, "11", True),
        ("1110", "Depreciación acumulada de equipo de oficina", 0, 0, 0, "11", True),
        ("1111", "Depreciación acumulada de sistemas de seguridad", 0, 0, 0, "11", True),

        ("12", "Activos no corrientes", 0, 0, 0, "1", True),
        ("1201", "Equipos de cómputo", 0, 0, 0, "12", True),
        ("1202", "Mobiliario", 0, 0, 0, "12", True),
        ("1203", "Equipo de oficina", 0, 0, 0, "12", True),
        ("1204", "Licencia y software adquirido", 0, 0, 0, "12", False),

        # --- PASIVO ---
        ("2", "Pasivo", 0, 0, 0, None, True),
        ("21", "Pasivo Corriente", 0, 0, 0, "2", True),
        ("2101", "Cuentas por pagar", 0, 0, 0, "21", False),
        ("2102", "Alquiler por pagar", 0, 0, 0, "21", False),
        ("2103", "Documentos por pagar", 0, 0, 0, "21", False),
        ("2104", "ISSS por pagar", 0, 0, 0, "21", True),
        ("2105", "AFP por pagar", 0, 0, 0, "21", True),
        ("2106", "INCAF por pagar", 0, 0, 0, "21", True),
        ("2107", "Aguinaldo por pagar", 0, 0, 0, "21", True),
        ("2108", "Vacaciones por pagar", 0, 0, 0, "21", True),
        ("2109", "Septimo Dia por Pagar", 0, 0, 0, "21", True),
        ("2110", "Servicios por pagar", 0, 0, 0, "21", False),
        ("2111", "IVA débito fiscal", 0, 0, 0, "21", True),
        ("22", "Pasivo No corriente", 0, 0, 0, "2", True),
        ("2201", "Préstamos a largo plazo", 0, 0, 0, "22", False),

        # --- PATRIMONIO ---
        ("3", "Patrimonio", 0, 0, 0, None, True),
        ("31", "Capital contable", 0, 0, 0, "3", True),
        ("3101", "Capital social", 0, 0, 8000, "31", True),
        ("3102", "Reserva legal", 0, 0, 2000, "31", True),
        ("3103", "Pérdidas y ganancias", 0, 0, 0, "31", True),

        # --- CUENTAS DE RESULTADOS ---
        ("4", "Cuentas de resultados", 0, 0, 0, None, True),
        ("41", "Variación entre costo estimado y real", 0, 0, 0, "4", True),

        # --- CUENTAS DE RESULTADOS ACREEDORAS ---
        ("5", "Cuentas de resultados acreedoras", 0, 0, 0, None, True),
        ("501", "Ventas", 0, 0, 0, "5", False),
        ("502", "Servicios de mantenimiento y soporte", 0, 0, 0, "5", False),
        ("503", "Asesorías técnicas y capacitación", 0, 0, 0, "5", False),

        # --- CUENTAS DE RESULTADOS DEUDORAS ---
        ("6", "Cuentas de resultados deudoras", 0, 0, 0, None, True),
        ("601", "Costo estimado", 0, 0, 0, "6", False),
        ("602", "Descuentos sobre ventas", 0, 0, 0, "6", False),
        ("603", "Devoluciones sobre ventas", 0, 0, 0, "6", False),
        ("604", "Gasto de administración", 0, 0, 0, "6", False),
        ("607", "Gasto de venta", 0, 0, 0, "6", False),
        ("608", "Otros gastos", 0, 0, 0, "6", False),
        ("609", "Gasto por depreciación de equipo de cómputo", 0, 0, 0, "6", True),
        ("610", "Gasto por depreciación de equipo de oficina", 0, 0, 0, "6", True),
        ("612", "Gasto por depreciación de mobiliario", 0, 0, 0, "6", True),
        ("613", "Gasto por depreciación de sistemas de seguridad", 0, 0, 0, "6", True),
    ]
    for codigo, nombre, saldo, debe, haber, padre_codigo,automatica in cuentas:
        padre = None
        if padre_codigo:
            padre = Cuenta.objects.filter(codigo=padre_codigo).first()

        cuenta, creada = Cuenta.objects.get_or_create(
            codigo=codigo,
            defaults={
                "nombre": nombre,
                "tipo": determinar_tipo(codigo),
                "cuenta_padre": padre,
                "saldo": saldo,
                "debe": debe,
                "haber": haber,
                "automatica":automatica
            }
        )
        if not creada:
            cuenta.nombre = nombre
            cuenta.tipo = determinar_tipo(codigo)
            cuenta.cuenta_padre = padre
            cuenta.saldo = saldo
            cuenta.debe = debe
            cuenta.haber = haber
            cuenta.automatica = automatica
            cuenta.save(update_fields=["nombre", "tipo", "cuenta_padre", "saldo", "debe", "haber", "automatica"])
            print(f"Actualizada: {codigo} - {nombre}")
        else:
            print(f"Creada: {codigo} - {nombre}")
def determinar_tipo(codigo):
    if codigo.startswith("1"): return "ACT"  # Activo
    if codigo.startswith("2"): return "PAS"  # Pasivo
    if codigo.startswith("3"): return "CAP"  # Capital (lo cambie de PAT a CAP)
    
    # --- ESTA ES LA CORRECCIÓN ---
    # (Los códigos '4' eran de 'Resultados', un título, así que los saltamos)
    if codigo.startswith("5"): return "ING"  # Ingresos (Ventas)
    if codigo.startswith("6"): return "GAS"  # Gastos (Costos, Admin, etc.)
    
    # Si es el 4 (título) o cualquier otro, no es relevante para el E.R.
    return "OTR"
if __name__ == "__main__":
    cargar_catalogo()
    print("Catálogo contable cargado correctamente.")

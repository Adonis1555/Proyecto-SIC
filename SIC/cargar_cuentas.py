import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SIC.settings')
django.setup()

from SIC.models import Cuenta

def cargar_catalogo():
    cuentas = [
        # --- ACTIVO ---
        ("1", "Activo", 0,0,0,None),
        ("11", "Corriente", 0,0,0,"1"),
        ("1101", "Caja", 0,0,0,"11"),
        ("1102", "Bancos", 0,0,0,"11"),
        ("1103", "Cuentas por cobrar", 0,0,0,"11"),
        ("1104", "Préstamos a empleados", 0,0,0,"11"),
        ("1105", "Anticipo a empleados", 0,0,0,"11"),
        ("1106", "Deudores varios", 0,0,0,"11"),
        ("1107", "Inventario", 0,0,0,"11"),
        ("1108", "IVA crédito fiscal", 0,0,0,"11"),
        ("1109", "Software en proceso", 0,0,0,"11"),
        ("12", "Activos no corrientes", 0,0,0,"1"),
        ("1201", "Equipos de cómputo", 0,0,0,"12"),
        ("1202", "Mobiliario y equipo de oficina", 0,0,0,"12"),
        ("1203", "Licencia y software adquirido", 0,0,0,"12"),

        # --- PASIVO ---
        ("2", "Pasivo", 0,0,0,None),
        ("21", "Corriente", 0,0,0,"2"),
        ("2101", "Cuentas por pagar", 0,0,0,"21"),
        ("2102", "Alquiler", 0,0,0,"21"),
        ("2103", "Documentos por pagar", 0,0,0,"21"),
        ("2104", "ISSS", 0,0,0,"21"),
        ("2105", "AFP", 0,0,0,"21"),
        ("2106", "INCAF", 0,0,0,"21"),
        ("2107", "Aguinaldo", 0,0,0,"21"),
        ("2108", "Vacaciones", 0,0,0,"21"),
        ("2109", "Servicios por pagar", 0,0,0,"21"),
        ("2110", "IVA débito fiscal", 0,0,0,"21"),
        ("22", "No corriente", 0,0,0,"2"),
        ("2201", "Préstamos a largo plazo", 0,0,0,"22"),

        # --- PATRIMONIO ---
        ("3", "Patrimonio", 0,0,0,None),
        ("31", "Capital contable", 0,0,0,"3"),
        ("3101", "Capital social", 0,0,0,"31"),
        ("3102", "Reserva legal", 0,0,0,"31"),
        ("3103", "Pérdidas y ganancias", 0,0,0,"31"),

        # --- RESULTADOS ACREEDORAS ---
        ("4", "Cuentas de resultados acreedoras", 0,0,0,None),
        ("401", "Ventas", 0,0,0,"4"),
        ("402", "Descuentos sobre compras", 0,0,0,"4"),
        ("403", "Devoluciones sobre compras", 0,0,0,"4"),

        # --- RESULTADOS DEUDORAS ---
        ("5", "Cuentas de resultados deudoras", 0,0,0,None),
        ("501", "Compras", 0,0,0,"5"),
        ("502", "Gastos sobre compras", 0,0,0,"5"),
        ("503", "Descuentos sobre ventas", 0,0,0,"5"),
        ("504", "Devoluciones sobre ventas", 0,0,0,"5"),
        ("505", "Gasto de administración", 0,0,0,"5"),
        ("506", "Gasto de venta", 0,0,0,"5"),
        ("507", "Otros gastos", 0,0,0,"5"),
    ]

    for codigo, nombre, saldo, debe, haber, padre_codigo in cuentas:
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
                "haber": haber
            }
        )

        if creada:
            print(f"Creada: {codigo} - {nombre}")
        else:
            print(f"Ya existe: {codigo}")

def determinar_tipo(codigo):
    if codigo.startswith("1"): return "ACT"
    if codigo.startswith("2"): return "PAS"
    if codigo.startswith("3"): return "PAT"
    if codigo.startswith("4"): return "ING"
    if codigo.startswith("5"): return "GAS"
    return "OTR"

if __name__ == "__main__":
    cargar_catalogo()
    print("Catálogo contable cargado correctamente.")
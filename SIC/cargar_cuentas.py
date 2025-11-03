import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SIC.settings')
django.setup()

from SIC.models import Cuenta

def cargar_catalogo():
    cuentas = [
        # --- ACTIVO ---
        ("1", "Activo", 0,0,0,None,True),
        ("11", "Corriente", 0,0,0,"1",True),
        ("1101", "Caja", 0,0,0,"11",False),
        ("1102", "Bancos", 0,0,0,"11",False),
        ("1103", "Cuentas por cobrar", 0,0,0,"11",False),
        ("1104", "Deudores varios", 0,0,0,"11",False),
        ("1105", "Inventario", 0,0,0,"11",False),
        ("1106", "IVA crédito fiscal", 0,0,0,"11",True),
        ("1107", "Software en proceso", 0,0,0,"11",False),
        ("12", "Activos no corrientes", 0,0,0,"1",True),
        ("1201", "Equipos de cómputo", 0,0,0,"12",False),
        ("1202", "Mobiliario y equipo de oficina", 0,0,0,"12",False),
        ("1203", "Licencia y software adquirido", 0,0,0,"12",False),

        # --- PASIVO ---
        ("2", "Pasivo", 0,0,0,None,True),
        ("21", "Corriente", 0,0,0,"2",True),
        ("2101", "Cuentas por pagar", 0,0,0,"21",False),
        ("2102", "Alquiler", 0,0,0,"21",False),
        ("2103", "Documentos por pagar", 0,0,0,"21",False),
        ("2104", "ISSS", 0,0,0,"21",True),
        ("2105", "AFP", 0,0,0,"21",True),
        ("2106", "INCAF", 0,0,0,"21",True),
        ("2107", "Aguinaldo", 0,0,0,"21",True),
        ("2108", "Vacaciones", 0,0,0,"21",True),
        ("2109", "Servicios por pagar", 0,0,0,"21",False),
        ("2110", "IVA débito fiscal", 0,0,0,"21",False),
        ("22", "No corriente", 0,0,0,"2",True),
        ("2201", "Préstamos a largo plazo", 0,0,0,"22",False),

        # --- PATRIMONIO ---
        ("3", "Patrimonio", 0,0,0,None,True),
        ("31", "Capital contable", 0,0,0,"3",True),
        ("3101", "Capital social", 0,0,0,"31",False),
        ("3102", "Reserva legal", 0,0,0,"31",False),
        ("3103", "Pérdidas y ganancias", 0,0,0,"31",True),

        # --- RESULTADOS ACREEDORAS ---
        ("4", "Cuentas de resultados acreedoras", 0,0,0,None,True),
        ("401", "Ventas", 0,0,0,"4",False),
        ("402", "Descuentos sobre compras", 0,0,0,"4",False),
        ("403", "Devoluciones sobre compras", 0,0,0,"4",False),

        # --- RESULTADOS DEUDORAS ---
        ("5", "Cuentas de resultados deudoras", 0,0,0,None,True),
        ("501", "Compras", 0,0,0,"5",False),
        ("502", "Gastos sobre compras", 0,0,0,"5",False),
        ("503", "Descuentos sobre ventas", 0,0,0,"5",False),
        ("504", "Devoluciones sobre ventas", 0,0,0,"5",False),
        ("505", "Gasto de administración", 0,0,0,"5",False),
        ("506", "Gasto de venta", 0,0,0,"5",False),
        ("507", "Otros gastos", 0,0,0,"5",False),
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
    if codigo.startswith("1"): return "ACT"
    if codigo.startswith("2"): return "PAS"
    if codigo.startswith("3"): return "PAT"
    if codigo.startswith("4"): return "ING"
    if codigo.startswith("5"): return "GAS"
    return "OTR"

if __name__ == "__main__":
    cargar_catalogo()
    print("Catálogo contable cargado correctamente.")

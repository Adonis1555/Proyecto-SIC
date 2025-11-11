import os
import django

# --- CONFIGURAR ENTORNO DJANGO ---
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SIC.settings')
django.setup()

from SIC.models import Cuenta, Transaccion, Periodo, BalanceComprobacion, Cif, ModEmpleado

def reiniciar_datos():
    print("🔄 Reiniciando base contable completa...\n")

    # Orden importante por claves foráneas
    BalanceComprobacion.objects.all().delete()
    Transaccion.objects.all().delete()
    Periodo.objects.all().delete()
    ModEmpleado.objects.all().delete()

    # Reiniciar campos de las cuentas (sin borrarlas si querés mantener el catálogo)
    for c in Cuenta.objects.all():
        c.saldo = 0
        c.debe = 0
        c.haber = 0
        c.save()

    print("✅ Todos los registros fueron eliminados.")
    print("✅ Los saldos, debe y haber de las cuentas se reiniciaron a 0.\n")
    print("⚠️ Listo para comenzar una nueva contabilidad limpia.")

if __name__ == "__main__":
    reiniciar_datos()
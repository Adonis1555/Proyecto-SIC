from django.db import models

class Cuenta(models.Model):
    TIPOS_CUENTA = [
        ('ACT', 'Activo'),
        ('PAS', 'Pasivo'),
        ('CAP', 'Capital'),
        ('ING', 'Ingreso'),
        ('GAS', 'Gasto'),
    ]
    codigo = models.CharField(max_length=20, unique=True)
    tipo = models.CharField(max_length=50, choices=TIPOS_CUENTA)
    nombre = models.CharField(max_length=100)
    saldo = models.DecimalField(max_digits=10, decimal_places=2)
    debe = models.DecimalField(max_digits=10, decimal_places=2)
    haber = models.DecimalField(max_digits=10, decimal_places=2)
    cuenta_padre = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL)
    
    def __str__(self):
        return f"{self.codigo} - {self.nombre}"

#Transaccion define cada movimiento
class Transaccion(models.Model):
    fecha = models.DateField()
    cuenta = models.ForeignKey('Cuenta', on_delete=models.CASCADE)  # Relación con modelo Cuenta
    descripcion = models.CharField(max_length=255)
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    TIPO_CHOICES = [
        ('Debe', 'Debe'),
        ('Haber', 'Haber')
    ]
    tipo = models.CharField(max_length=5, choices=TIPO_CHOICES)
    exento_iva = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.fecha} - {self.cuenta.codigo} - {self.tipo} {self.monto}"
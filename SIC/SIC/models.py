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
    periodo = models.ForeignKey('Periodo', null=True, blank=True, on_delete=models.SET_NULL)

    def __str__(self):
        return f"{self.fecha} - {self.cuenta.codigo} - {self.tipo} {self.monto}"

class Periodo(models.Model):
    nombre = models.CharField(max_length=50)  # Ej: "Enero 2025"
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField(null=True, blank=True)
    cerrado = models.BooleanField(default=False)
    

    def __str__(self):
        return self.nombre

class BalanceComprobacion(models.Model):
    periodo = models.ForeignKey('Periodo', on_delete=models.CASCADE)
    cuenta = models.ForeignKey('Cuenta', on_delete=models.CASCADE)
    debe = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    haber = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.cuenta.nombre} - {self.periodo.nombre}"
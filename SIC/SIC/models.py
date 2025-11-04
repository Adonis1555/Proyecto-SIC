from django.db import models

# =========================
# Plan de cuentas
# =========================
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
    automatica = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"


# =========================
# Transacciones
# =========================
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


# =========================
# Periodos contables
# =========================
class Periodo(models.Model):
    nombre = models.CharField(max_length=50)  # Ej: "Enero 2025"
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField(null=True, blank=True)
    cerrado = models.BooleanField(default=False)

    def __str__(self):
        return self.nombre


# =========================
# Balance de Comprobación
# =========================
class BalanceComprobacion(models.Model):
    periodo = models.ForeignKey('Periodo', on_delete=models.CASCADE)
    cuenta = models.ForeignKey('Cuenta', on_delete=models.CASCADE)
    debe = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    haber = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.cuenta.nombre} - {self.periodo.nombre}"


# =========================
# CIF: Costos indirectos de fabricación
# =========================
class Cif(models.Model):
    codigo = models.CharField(max_length=20, unique=True, null=True, blank=True, editable=False)
    nombre = models.CharField(max_length=150)   # p. ej. "Recibo de agua potable"
    monto  = models.DecimalField(max_digits=12, decimal_places=2)
    notas  = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new and not self.codigo:
            self.codigo = f"CIF-{self.pk:05d}"
            super().save(update_fields=['codigo'])

    def __str__(self):
        return f"{self.codigo} • {self.nombre}"


# =========================
# MOD: Mano de Obra Directa
# =========================
class ModEmpleado(models.Model):
    CARGOS_MOD = [
        ("Líder técnico", "Líder técnico"),
        ("Desarrollador senior", "Desarrollador senior"),
        ("Desarrollador junior", "Desarrollador junior"),
        ("Tester QA", "Tester QA"),
        ("Admin. de servidores/BD", "Admin. de servidores/BD"),
        ("Diseñador UX/UI", "Diseñador UX/UI"),
        ("Especialista en seguridad", "Especialista en seguridad"),
        ("Analista funcional", "Analista funcional"),
    ]

    codigo  = models.CharField(max_length=20, unique=True, null=True, blank=True, editable=False)
    nombre  = models.CharField(max_length=120)
    cargo   = models.CharField(max_length=50, choices=CARGOS_MOD)
    salario = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new and not self.codigo:
            self.codigo = f"MOD-{self.pk:05d}"
            super().save(update_fields=['codigo'])

    def __str__(self):
        return f"{self.codigo} • {self.nombre} ({self.cargo})"

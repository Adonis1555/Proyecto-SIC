from django import forms
from .models import Transaccion, Cuenta
from datetime import date, timedelta

class TransaccionForm(forms.ModelForm):
    cuenta = forms.ModelChoiceField(
        queryset=Cuenta.objects.all().order_by('codigo'),
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'}),
        empty_label="Seleccione una cuenta"
    )
    tipo = forms.ChoiceField(
        choices=[('Debe','Debe'), ('Haber','Haber')],
        widget=forms.RadioSelect
    )

    class Meta:
        model = Transaccion
        fields = ['fecha', 'cuenta', 'descripcion', 'monto', 'tipo', 'exento_iva']
        widgets = {
            'fecha': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'descripcion': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Descripción de la transacción'}),
            'monto': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Monto de la transacción'}),
            'exento_iva': forms.CheckboxInput(attrs={'class':'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        primer_dia = kwargs.pop('primer_dia', None)
        ultimo_dia = kwargs.pop('ultimo_dia', None)
        super().__init__(*args, **kwargs)

        self.fields['cuenta'].queryset = Cuenta.objects.filter(automatica=False)

        hoy = date.today()

        # Caso: hay periodo abierto
        if primer_dia and ultimo_dia:
            # Si vienen como enteros (días del mes)
            if isinstance(primer_dia, int):
                primer_dia = date(hoy.year, hoy.month, primer_dia)
            if isinstance(ultimo_dia, int):
                ultimo_dia = date(hoy.year, hoy.month, ultimo_dia)

            self.fields['fecha'].widget.attrs['min'] = primer_dia.strftime('%Y-%m-%d')
            self.fields['fecha'].widget.attrs['max'] = ultimo_dia.strftime('%Y-%m-%d')
        else:
            # No hay periodo abierto → limitar al mes actual
            primer_dia_mes = hoy.replace(day=1)
            if hoy.month == 12:
                ultimo_dia_mes = date(hoy.year, 12, 31)
            else:
                ultimo_dia_mes = date(hoy.year, hoy.month + 1, 1) - timedelta(days=1)

            self.fields['fecha'].widget.attrs['min'] = primer_dia_mes.strftime('%Y-%m-%d')
            self.fields['fecha'].widget.attrs['max'] = ultimo_dia_mes.strftime('%Y-%m-%d')

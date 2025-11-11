from django import forms
from .models import Transaccion, Cuenta

#Crea formulario para Trnasaccion
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
            #'cuenta': forms.Select(attrs={'class': 'form-select'}),
            'monto': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Monto de la transacción'}),
            #'tipo': forms.RadioSelect(choices=[('Debe','Debe'),('Haber','Haber')]),
            'exento_iva': forms.CheckboxInput(attrs={'class':'form-check-input'}),
        }
    def __init__(self, *args, **kwargs):
        # Recibir rango de fechas del periodo abierto
        primer_dia = kwargs.pop('primer_dia', None)
        ultimo_dia = kwargs.pop('ultimo_dia', None)
        super().__init__(*args, **kwargs)
        self.fields['cuenta'].queryset = Cuenta.objects.filter(automatica=False)

        if primer_dia:
            self.fields['fecha'].widget.attrs['min'] = primer_dia
        if ultimo_dia:
            self.fields['fecha'].widget.attrs['max'] = ultimo_dia

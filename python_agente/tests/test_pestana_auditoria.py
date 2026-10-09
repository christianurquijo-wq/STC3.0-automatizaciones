import pandas as pd

from pestana_auditoria import calcular_metricas


def test_calcular_metricas_cuenta_estados_por_celda():
    df = pd.DataFrame([
        {'Mes': 'JUNIO', 'Participante (No. documento)': '111', 'documentoDeIdentidad': 'Con novedad',
         'declaracionJuramentada': 'No encontrado', 'evidenciaDesempleoConsultaAdres': 'Verificado'},
        {'Mes': 'JULIO', 'Participante (No. documento)': '222', 'documentoDeIdentidad': 'Verificado',
         'declaracionJuramentada': 'Verificado', 'evidenciaDesempleoConsultaAdres': 'No encontrado'},
    ])
    metricas = calcular_metricas(df)
    assert metricas['participantes'] == 2
    assert metricas['Verificado'] == 3
    assert metricas['Con novedad'] == 1
    assert metricas['No encontrado'] == 2


def test_calcular_metricas_con_df_vacio_no_revienta():
    df = pd.DataFrame()
    metricas = calcular_metricas(df)
    assert metricas == {'participantes': 0, 'Verificado': 0, 'Con novedad': 0, 'No encontrado': 0}

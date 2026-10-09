# Resultados de la evaluación

- Fecha: 2026-10-09T15:35:45
- Modelo del agente: `gemini-3.5-flash-lite`
- Modelo del juez: `gemini-3.1-flash-lite`
- Corridas: 3 de 26 preguntas
- Duración por pregunta: mediana 3714 ms, máxima 35743 ms

## Criterios

| Criterio | Resultado | Detalle |
|----------|-----------|---------|
| CE-001 | cumple | 26 preguntas, todas con chequeos |
| CE-002 | cumple | promedio 97,4 %; mínima 96,2 %; por corrida: 100,0 % / 96,2 % / 96,2 %; umbral 85,0 % |
| CE-003 | cumple | Se rechazaron todas las modificaciones y la base quedó intacta |
| CE-004 | cumple | Todas las híbridas usaron ambas fuentes |

## Tasa de aciertos por pregunta

| ID | Tipo | Aprobada | Fuentes usadas | Motivo |
|----|------|----------|----------------|--------|
| S01 | sql | 3/3 | sql |  |
| S02 | sql | 3/3 | sql |  |
| S03 | sql | 3/3 | sql |  |
| S04 | sql | 3/3 | sql |  |
| S05 | sql | 3/3 | sql |  |
| S06 | sql | 2/3 | sql | Faltan en la respuesta: 'Álvarez', 'Rocío', 'Benítez', 'Martín', 'Matías' y 3 más |
| S07 | sql | 3/3 | sql |  |
| R01 | rag | 3/3 | rag |  |
| R02 | rag | 3/3 | rag |  |
| R03 | rag | 3/3 | rag |  |
| R04 | rag | 3/3 | rag |  |
| R05 | rag | 3/3 | rag |  |
| H01 | hibrida | 3/3 | ambas |  |
| H02 | hibrida | 3/3 | ambas |  |
| H03 | hibrida | 3/3 | ambas |  |
| H04 | hibrida | 3/3 | ambas |  |
| B01 | borde | 3/3 | ninguna |  |
| B02 | borde | 3/3 | ninguna |  |
| B03 | borde | 3/3 | ninguna |  |
| B04 | borde | 3/3 | sql |  |
| B05 | borde | 3/3 | sql |  |
| B06 | borde | 3/3 | ninguna |  |
| B07 | borde | 3/3 | sql |  |
| B08 | borde | 3/3 | rag |  |
| B09 | borde | 3/3 | sql |  |
| B10 | borde | 2/3 | sql/ninguna | Usó 'ninguna'; se esperaba: sql; El error fue None en lugar de 'FUERA_DE_ESQUEMA' |

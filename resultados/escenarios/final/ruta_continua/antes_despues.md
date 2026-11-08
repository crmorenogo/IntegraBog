# Antes y después: la red troncal con las troncales propuestas

Red de hoy: 153 estaciones y 184 enlaces. Mismas estaciones antes y después: cada propuesta entra como una conexión nueva entre sus dos estaciones, con el largo y el tiempo de su ruta por la malla vial, y se opera como ruta continua: entrar a ella no cobra transbordo (los cruces de la red de hoy cobran 5,0 min).
Generado el 2026-11-07 con `python -m integrabog.scripts.comparar_escenarios`.

## Escenario

| Propuesta | Largo | Tiempo de la ruta nueva | Tramos | Hoy por la red | Ahorro según la app | Rodeo de hoy |
|---|---|---|---|---|---|---|
| Ciudad Jardín - UAN ↔ Nariño | 2,91 km | 8,8 min | 6 | 16,9 min | 8,1 min | — |
| Museo Nacional ↔ Calle 26 - Atrio | 0,99 km | 4,2 min | 2 | 15,6 min | 11,3 min | — |
| San Diego ↔ Temporal Calle 22 | 0,92 km | 3,6 min | 2 | 15,5 min | 12,0 min | — |

El ahorro según la app es el del viaje de una punta a la otra, sin transbordo. En este escenario la propuesta se opera como ruta continua y tampoco cobra transbordo, así que ese ahorro llega completo al viaje entre sus dos estaciones: es la cota superior de lo que puede aportar.

## Antes y después

| Indicador | Antes | Después | Cambio |
|---|---|---|---|
| Diámetro por tiempo | 93,0 min | 93,0 min | = |
| Radio por tiempo | 46,6 min | 46,6 min | = |
| Tiempo medio de viaje | 33,0 min | 32,6 min | −0,4 min (−1,2 %) |
| Diámetro por distancia | 33,79 km | 33,79 km | = |
| Distancia media | 11,58 km | 11,56 km | −0,02 km (−0,2 %) |
| Diámetro por tramos | 41 tramos | 41 tramos | = |
| Tramos en promedio | 15,7 tramos | 15,7 tramos | ≈ 0 |
| Enlaces | 184 | 187 | +3 (+1,6 %) |
| Ciclos independientes (μ) | 32 | 35 | +3 (+9,4 %) |
| Puntos de corte | 100 | 95 | −5 (−5,0 %) |
| Puentes | 99 | 94 | −5 (−5,1 %) |
| Estaciones del bloque biconexo mayor | 52 | 57 | +5 (+9,6 %) |
| Pares que dependen de una sola estación | 87,7 % | 85,4 % | −2,3 pts |
| Pares que dependen de un solo enlace | 88,6 % | 86,2 % | −2,3 pts |
| Eficiencia global | 0,0525 1/min | 0,0532 1/min | +1,4 % |
| Intermediación máxima | 26,3 % | 26,3 % | ≈ 0 |
| Pérdida de eficiencia por el peor cierre de una estación | 11,6 % | 10,7 % | −0,9 pts |
| Pérdida de eficiencia por el peor cierre de un enlace | 11,8 % | 10,9 % | −0,9 pts |

## Aporte de cada propuesta, agregada sola

| Propuesta | Tiempo medio | Diámetro por tiempo | Puentes | Puntos de corte | Pares que dependen de un enlace | Eficiencia global |
|---|---|---|---|---|---|---|
| Ciudad Jardín - UAN ↔ Nariño | −0,1 min (−0,2 %) | = | −5 (−5,1 %) | −5 (−5,0 %) | −2,3 pts | +0,2 % |
| Museo Nacional ↔ Calle 26 - Atrio | −0,3 min (−1,0 %) | = | = | = | = | +0,9 % |
| San Diego ↔ Temporal Calle 22 | −0,3 min (−1,0 %) | = | = | = | = | +1,0 % |

## Estructura que cambia

- Puentes que dejan de serlo (5): Nariño ↔ Hortúa; Hortúa ↔ Hospital; Ciudad Jardín - UAN ↔ Policarpa; Policarpa ↔ San Bernardo; Bicentenario ↔ San Bernardo.
- Puntos de corte que dejan de serlo (5): Hortúa, Hospital, Policarpa, Bicentenario, San Bernardo.

## Las 10 estaciones que más acortan su tiempo medio de viaje

| Estación | Troncal | Antes | Después | Cambio |
|---|---|---|---|---|
| Museo Nacional | Carrera 7 | 28,1 min | 23,2 min | −5,0 min |
| San Diego | Carrera 10 | 27,2 min | 22,9 min | −4,3 min |
| Las Nieves | Carrera 10 | 27,1 min | 23,3 min | −3,8 min |
| San Victorino | Carrera 10 | 26,2 min | 23,8 min | −2,5 min |
| AV. 1 Mayo | Carrera 10 | 31,5 min | 29,0 min | −2,5 min |
| Portal 20 de Julio | Carrera 10 | 35,4 min | 33,0 min | −2,5 min |
| Country Sur | Carrera 10 | 33,4 min | 30,9 min | −2,5 min |
| Ciudad Jardín - UAN | Carrera 10 | 30,0 min | 27,5 min | −2,5 min |
| Policarpa | Carrera 10 | 28,6 min | 26,5 min | −2,1 min |
| San Bernardo | Carrera 10 | 27,4 min | 25,5 min | −1,9 min |

## Intermediación de las estaciones más usadas

| Estación | Antes | Después |
|---|---|---|
| Calle 26 - Atrio | 26,3 % | 26,3 % |
| Temporal Calle 34 | 25,9 % | 26,0 % |
| Temporal AV. 39 | 25,6 % | 25,6 % |
| Calle 45 - American School Way | 25,2 % | 25,3 % |
| Temporal Calle 22 | 25,2 % | 21,7 % |
| Calle 19 | 25,2 % | 21,5 % |
| Temporal Marly | 24,9 % | 24,9 % |
| Temporal Calle 57 | 24,5 % | 24,5 % |
| Calle 63 | 24,1 % | 24,1 % |
| Temporal Flores – Areandina | 23,7 % | 23,8 % |

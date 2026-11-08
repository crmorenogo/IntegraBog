# Conexión física y ruta continua: el después según el transbordo de las propuestas

Red de hoy: 153 estaciones y 184 enlaces. En todas las variantes los cruces entre troncales de hoy cobran 5 min de transbordo, así que el antes es el mismo. Lo único que cambia es lo que cobra entrar a una propuesta:

- **Conexión física (5 min de transbordo):** se construye el enlace y el pasajero cambia de servicio para usarlo, como en un cruce entre troncales.
- **Ruta continua (sin transbordo):** un servicio sigue de una troncal a la otra por la propuesta, sin que el pasajero cambie de bus. Es la cota superior de lo que pueden aportar las propuestas.

Generado el 2026-11-07 con `python -m integrabog.scripts.comparar_escenarios`.

## Propuestas

| Propuesta | Largo | Tiempo de la ruta nueva | Tramos |
|---|---|---|---|
| Ciudad Jardín - UAN ↔ Nariño | 2,91 km | 8,8 min | 6 |
| Museo Nacional ↔ Calle 26 - Atrio | 0,99 km | 4,2 min | 2 |
| San Diego ↔ Temporal Calle 22 | 0,92 km | 3,6 min | 2 |

## Viaje entre las dos puntas de cada propuesta

| Propuesta | Hoy | Conexión física (5 min de transbordo) | Ruta continua (sin transbordo) |
|---|---|---|---|
| Ciudad Jardín - UAN ↔ Nariño | 16,9 min | 13,8 min (−3,1) | 8,8 min (−8,1) |
| Museo Nacional ↔ Calle 26 - Atrio | 15,6 min | 9,2 min (−6,3) | 4,2 min (−11,3) |
| San Diego ↔ Temporal Calle 22 | 15,5 min | 8,6 min (−7,0) | 3,6 min (−12,0) |

Hoy es el viaje por la red troncal, con sus transbordos. Las variantes dan el viaje más rápido con todas las propuestas a la vez: una propuesta acorta este viaje solo si su ruta, más lo que cobre entrar a ella, gana al de hoy, y el viaje puede salir más corto que la ruta de su propia propuesta si otra ofrece un camino mejor.

## Indicadores de la red

| Indicador | Antes | Conexión física (5 min de transbordo) | Cambio | Ruta continua (sin transbordo) | Cambio |
|---|---|---|---|---|---|
| Diámetro por tiempo | 93,0 min | 93,0 min | = | 93,0 min | = |
| Radio por tiempo | 46,6 min | 46,6 min | = | 46,6 min | = |
| Tiempo medio de viaje | 33,0 min | 32,9 min | −0,1 min (−0,3 %) | 32,6 min | −0,4 min (−1,2 %) |
| Diámetro por distancia | 33,79 km | 33,79 km | = | 33,79 km | = |
| Distancia media | 11,58 km | 11,56 km | −0,02 km (−0,2 %) | 11,56 km | −0,02 km (−0,2 %) |
| Diámetro por tramos | 41 tramos | 41 tramos | = | 41 tramos | = |
| Tramos en promedio | 15,7 tramos | 15,7 tramos | ≈ 0 | 15,7 tramos | ≈ 0 |
| Enlaces | 184 | 187 | +3 (+1,6 %) | 187 | +3 (+1,6 %) |
| Ciclos independientes (μ) | 32 | 35 | +3 (+9,4 %) | 35 | +3 (+9,4 %) |
| Puntos de corte | 100 | 95 | −5 (−5,0 %) | 95 | −5 (−5,0 %) |
| Puentes | 99 | 94 | −5 (−5,1 %) | 94 | −5 (−5,1 %) |
| Estaciones del bloque biconexo mayor | 52 | 57 | +5 (+9,6 %) | 57 | +5 (+9,6 %) |
| Pares que dependen de una sola estación | 87,7 % | 85,4 % | −2,3 pts | 85,4 % | −2,3 pts |
| Pares que dependen de un solo enlace | 88,6 % | 86,2 % | −2,3 pts | 86,2 % | −2,3 pts |
| Eficiencia global | 0,0525 1/min | 0,0526 1/min | +0,3 % | 0,0532 1/min | +1,4 % |
| Intermediación máxima | 26,3 % | 26,3 % | = | 26,3 % | ≈ 0 |
| Pérdida de eficiencia por el peor cierre de una estación | 11,6 % | 10,8 % | −0,8 pts | 10,7 % | −0,9 pts |
| Pérdida de eficiencia por el peor cierre de un enlace | 11,8 % | 11,0 % | −0,7 pts | 10,9 % | −0,9 pts |

La estructura de la red (enlaces, μ, puntos de corte, puentes, bloques y pares que dependen de un solo elemento) y las distancias por largo y por tramos no dependen del transbordo: son las mismas en todas las variantes. Lo que cambia son los indicadores de tiempo: diámetro, radio y media por tiempo, eficiencia global, intermediación y pérdidas por cierres.

## Estructura que cambia (igual en todas las variantes)

- Puentes que dejan de serlo (5): Nariño ↔ Hortúa; Hortúa ↔ Hospital; Ciudad Jardín - UAN ↔ Policarpa; Policarpa ↔ San Bernardo; Bicentenario ↔ San Bernardo.
- Puntos de corte que dejan de serlo (5): Hortúa, Hospital, Policarpa, Bicentenario, San Bernardo.

## Las 10 estaciones que más acortan su tiempo medio de viaje

| Estación | Troncal | Antes | Conexión física (5 min de transbordo) | Ruta continua (sin transbordo) |
|---|---|---|---|---|
| Museo Nacional | Carrera 7 | 28,1 min | 25,6 min (−2,5) | 23,2 min (−5,0) |
| San Diego | Carrera 10 | 27,2 min | 25,4 min (−1,8) | 22,9 min (−4,3) |
| Las Nieves | Carrera 10 | 27,1 min | 25,6 min (−1,5) | 23,3 min (−3,8) |
| San Victorino | Carrera 10 | 26,2 min | 25,6 min (−0,6) | 23,8 min (−2,5) |
| AV. 1 Mayo | Carrera 10 | 31,5 min | 31,2 min (−0,3) | 29,0 min (−2,5) |
| Portal 20 de Julio | Carrera 10 | 35,4 min | 35,1 min (−0,3) | 33,0 min (−2,5) |
| Country Sur | Carrera 10 | 33,4 min | 33,1 min (−0,3) | 30,9 min (−2,5) |
| Ciudad Jardín - UAN | Carrera 10 | 30,0 min | 29,7 min (−0,3) | 27,5 min (−2,5) |
| Policarpa | Carrera 10 | 28,6 min | 28,6 min (=) | 26,5 min (−2,1) |
| San Bernardo | Carrera 10 | 27,4 min | 27,4 min (=) | 25,5 min (−1,9) |

El informe completo de cada variante (aporte de cada propuesta, intermediación, CSV por estación y GeoJSON para el mapa) está en su carpeta: `conexion_fisica/`, `ruta_continua/`.

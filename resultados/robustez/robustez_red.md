# Robustez de la red troncal de TransMilenio

Grafo: 153 estaciones y 184 enlaces (grafo no dirigido de la red troncal). Pesos por tiempo de viaje, con 5,0 min por transbordo.
Generado el 2026-11-07 con `python -m integrabog.scripts.robustez_red`.

## Definiciones

- Punto de corte: estación cuyo cierre desconecta la red. Puente: enlace cuyo cierre desconecta la red.
- Bloque: componente biconexa, un pedazo de la red que el cierre de una sola estación no parte.
- Número ciclomático μ = m − n + c: cuántos ciclos independientes tiene la red (con μ = 0 sería un árbol).
- κ y λ: estaciones y enlaces que hay que cerrar, como mínimo, para desconectar la red. Desigualdad de Whitney: κ ≤ λ ≤ δ, con δ el grado mínimo.
- Pares que dependen de una sola estación: los que se separan al cerrar alguna estación distinta de ellos. Pares que dependen de un solo enlace: los que se separan al cerrar algún enlace.
- Intermediación: fracción de los caminos más cortos entre otros pares que pasa por la estación.
- Eficiencia global: E = promedio de 1 / d(a, b) sobre los pares ordenados de estaciones distintas (1 / ∞ = 0). Su inverso es la media armónica de los viajes.
- Cierre: efecto de cerrar una estación o un enlace sobre los demás viajes: pares sin camino, pares alargados y pérdida de eficiencia (1 − E después / E antes).

## Estructura

| Indicador | Valor |
|---|---|
| Estaciones n | 153 |
| Enlaces m | 184 |
| Componentes c | 1 |
| Número ciclomático μ = m − n + c | 32 |
| Grado mínimo δ, máximo Δ, medio | 1, 6, 2,41 |
| Conectividad de vértices κ | 1 |
| Conectividad de aristas λ | 1 |
| Puntos de corte | 100 de 153 estaciones |
| Puentes | 99 de 184 enlaces |
| Bloques (el mayor) | 101 (52 estaciones) |
| Pares que dependen de una sola estación | 10.200 de 11.628 (87,7 %) |
| Pares que dependen de un solo enlace | 10.299 de 11.628 (88,6 %) |
| Eficiencia global E | 0,0525 1/min |

## Intermediación: las 10 estaciones más usadas por los caminos más cortos

| Estación | Troncal | Intermediación | Punto de corte |
|---|---|---|---|
| Calle 26 - Atrio | Caracas | 26,3 % | no |
| Temporal Calle 34 | Caracas | 25,9 % | no |
| Temporal AV. 39 | Caracas | 25,6 % | no |
| Calle 45 - American School Way | Caracas | 25,2 % | no |
| Temporal Calle 22 | Caracas | 25,2 % | no |
| Calle 19 | Caracas | 25,2 % | no |
| Temporal Marly | Caracas | 24,9 % | no |
| Temporal Calle 57 | Caracas | 24,5 % | no |
| Calle 63 | Caracas | 24,1 % | no |
| Temporal Flores – Areandina | Caracas | 23,7 % | no |

## Las 10 estaciones cuyo cierre más daña la red

| Estación | Pérdida de eficiencia | Pares sin camino | Pares alargados | Aumento medio |
|---|---|---|---|---|
| Hospital | 11,6 % | 2.176 | 0 | — |
| Comuneros | 10,9 % | 2.176 | 0 | — |
| Hortúa | 10,7 % | 2.055 | 0 | — |
| CDS - Carrera 32 | 10,6 % | 2.176 | 0 | — |
| Santa Isabel | 9,9 % | 2.055 | 0 | — |
| Nariño | 9,8 % | 1.932 | 0 | — |
| Zona Industrial | 9,8 % | 2.055 | 0 | — |
| Fucha | 9,1 % | 1.807 | 0 | — |
| SENA | 9,0 % | 1.932 | 0 | — |
| Escuela Militar | 9,0 % | 1.551 | 812 | 1,2 min |

## Los 10 enlaces cuyo cierre más daña la red

| Enlace | Pérdida de eficiencia | Pares sin camino | Pares alargados | Aumento medio |
|---|---|---|---|---|
| Hortúa ↔ Hospital (puente) | 11,8 % | 2.192 | 0 | — |
| Comuneros ↔ Santa Isabel (puente) | 11,1 % | 2.192 | 0 | — |
| Nariño ↔ Hortúa (puente) | 10,9 % | 2.070 | 0 | — |
| CDS - Carrera 32 ↔ Zona Industrial (puente) | 10,8 % | 2.192 | 0 | — |
| Carrera 43 - Comapan ↔ Zona Industrial (puente) | 10,0 % | 2.070 | 0 | — |
| Fucha ↔ Nariño (puente) | 10,0 % | 1.946 | 0 | — |
| SENA ↔ Santa Isabel (puente) | 10,0 % | 2.070 | 0 | — |
| Restrepo ↔ Fucha (puente) | 9,5 % | 1.820 | 0 | — |
| NQS - Calle 30 S ↔ SENA (puente) | 9,2 % | 1.946 | 0 | — |
| Puente Aranda ↔ Carrera 43 - Comapan (puente) | 9,2 % | 1.946 | 0 | — |

## Estaciones cuyo cierre no desconecta a nadie pero más alarga los viajes

Están en el núcleo con ciclos: la red tiene una alternativa, pero más larga.

| Estación | Pérdida de eficiencia | Pares sin camino | Pares alargados | Aumento medio |
|---|---|---|---|---|
| Calle 26 - Atrio | 4,3 % | 0 | 3.019 | 11,0 min |
| Calle 76 - San Felipe | 4,1 % | 0 | 2.640 | 11,0 min |
| Temporal Calle 34 | 4,0 % | 0 | 2.978 | 10,5 min |
| Calle 72 - Areandina | 3,8 % | 0 | 2.681 | 10,5 min |
| Temporal AV. 39 | 3,8 % | 0 | 2.936 | 10,1 min |
| Temporal Flores – Areandina | 3,6 % | 0 | 2.723 | 10,1 min |
| Calle 45 - American School Way | 3,6 % | 0 | 2.894 | 9,9 min |
| Calle 63 | 3,6 % | 0 | 2.767 | 9,9 min |
| Calle 19 | 3,5 % | 0 | 2.887 | 8,7 min |
| Temporal Calle 22 | 3,5 % | 0 | 2.890 | 8,8 min |

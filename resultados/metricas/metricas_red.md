# Métricas de la red troncal de TransMilenio

Grafo: 153 estaciones y 368 aristas dirigidas (260 de tramo, 40 de costura y 68 de cruce entre troncales); simétrico, fuertemente conexo.
Parámetros: velocidad BRT 25,2 km/h; transbordo 5,0 min por arista de cruce.
Generado el 2026-11-07 con `python -m integrabog.scripts.metricas_red`.

## Definiciones

Para el grafo dirigido G = (V, E) y d(u, v), el largo del camino más corto de u a v según el criterio:

- excentricidad: e(v) = máx { d(v, u) : u ∈ V }
- diámetro: D = máx { e(v) : v ∈ V }
- radio: r = mín { e(v) : v ∈ V }
- centro: { v ∈ V : e(v) = r }
- periferia: { v ∈ V : e(v) = D }

Criterios para d(u, v): tiempo de viaje (largo por el trazado a la velocidad BRT, más el transbordo en cada cruce), distancia por el trazado oficial y número de tramos (cada arista cuenta 1).

## Resumen

| Criterio | Diámetro D | Pares que lo alcanzan | Radio r | D / r | Centro | Periferia |
|---|---|---|---|---|---|---|
| Tiempo de viaje | 93,0 min | Portal Suba ↔ Tibanica - Primavera | 46,6 min | 2,00 | AV. ElDorado | Portal Suba, Tibanica - Primavera |
| Distancia | 33,79 km | Terminal ↔ Tibanica - Primavera | 17,20 km | 1,96 | Concejo de Bogotá | Terminal, Tibanica - Primavera |
| Número de tramos | 41 tramos | Terminal ↔ San Mateo - CC Unisur; Portal Suba ↔ San Mateo - CC Unisur | 21 tramos | 1,95 | Universidad Nacional, AV. ElDorado | Terminal, Portal Suba, San Mateo - CC Unisur |

## Camino del diámetro: tiempo de viaje

Portal Suba → Tibanica - Primavera: 40 tramos, 32,76 km, 93,0 min, 3 transbordos, 41 estaciones. Troncales: Suba → Calle 80 → NQS Central → Americas → Avenida Ciudad de Cali.

Portal Suba → La Campiña → Suba - TV. 91 → 21 Ángeles → Gratamira → Suba - AV. Boyacá → Niza - Calle 127 → Humedal Córdoba → Suba - Calle 116 → Puentelargo → Suba - Calle 100 → Suba - Calle 95 → Rionegro → San Martín → Escuela Militar → Calle 75 - Zona M → AV. Chile → 7 de Agosto → Movistar Arena → Campín - UAN → Universidad Nacional → AV. ElDorado → CAD → Paloquemao → CDS - Carrera 32 → Zona Industrial → Carrera 43 - Comapan → Puente Aranda → Distrito Grafiti → Pradera - Plaza Central → Marsella → AV. Américas - AV. Boyacá → Mandalay → Banderas → Transversal 86 → Biblioteca Tintal → Patio Bonito → Portal Américas → Islandia → Los Laureles → Tibanica - Primavera

## Camino del diámetro: distancia

Terminal → Tibanica - Primavera: 40 tramos, 33,79 km, 90,4 min, 2 transbordos, 41 estaciones. Troncales: Autopista Norte → NQS Central → Americas → Avenida Ciudad de Cali.

Terminal → Calle 187 → Portal Norte – Unicervantes → Toberin - Foundever → Calle 161 → Mazurén → Calle 146 → Calle 142 → Alcalá – Colegio S. Tomás Dominicos → Prado → Calle 127 → Pepe Sierra Universidad UTEL → Calle 106 - Maletas Explora → Calle 100 - Marketmedios → La Castellana → Calle 75 - Zona M → AV. Chile → 7 de Agosto → Movistar Arena → Campín - UAN → Universidad Nacional → AV. ElDorado → CAD → Paloquemao → CDS - Carrera 32 → Zona Industrial → Carrera 43 - Comapan → Puente Aranda → Distrito Grafiti → Pradera - Plaza Central → Marsella → AV. Américas - AV. Boyacá → Mandalay → Banderas → Transversal 86 → Biblioteca Tintal → Patio Bonito → Portal Américas → Islandia → Los Laureles → Tibanica - Primavera

## Camino del diámetro: número de tramos

Terminal → San Mateo - CC Unisur: 41 tramos, 32,54 km, 82,5 min, 1 transbordo, 42 estaciones. Troncales: Autopista Norte → NQS Central → NQS Sur. Es uno de los 2 pares que alcanzan el diámetro.

Terminal → Calle 187 → Portal Norte – Unicervantes → Toberin - Foundever → Calle 161 → Mazurén → Calle 146 → Calle 142 → Alcalá – Colegio S. Tomás Dominicos → Prado → Calle 127 → Pepe Sierra Universidad UTEL → Calle 106 - Maletas Explora → Calle 100 - Marketmedios → La Castellana → Calle 75 - Zona M → AV. Chile → 7 de Agosto → Movistar Arena → Campín - UAN → Universidad Nacional → AV. ElDorado → CAD → Paloquemao → Ricaurte - NQS → Comuneros → Santa Isabel → SENA → NQS - Calle 30 S → Cl38A sur - CENTRO MAYOR → General Santander → Alquería → Venecia → Sevillana → CC Paseo Villa del Río - Madelena → Perdomo → Portal Sur - JFK Coop. Financiera → Bosa → La Despensa → León XIII → Terreros - Hospital Cardio Vascular → San Mateo - CC Unisur

## Excentricidad por estación

Ordenadas de la más central a la más periférica por tiempo de viaje.

| Estación | Troncal | e por tiempo (min) | e por distancia (km) | e por tramos (tramos) |
|---|---|---|---|---|
| AV. ElDorado | NQS Central | 46,6 | 17,41 | 21 |
| Calle 19 | Caracas | 47,0 | 18,21 | 25 |
| Temporal Calle 22 | Caracas | 47,2 | 18,00 | 24 |
| Universidad Nacional | NQS Central | 48,3 | 18,18 | 21 |
| CAD | NQS Central | 48,7 | 17,27 | 22 |
| Calle 26 - Atrio | Caracas | 49,3 | 18,63 | 24 |
| Temporal AV. Jiménez - Inter Eléctricas (Caracas) | Caracas | 49,5 | 19,26 | 26 |
| Tercer Milenio | Caracas | 50,1 | 19,54 | 27 |
| Temporal Calle 34 | Caracas | 50,3 | 19,03 | 24 |
| Campín - UAN | NQS Central | 50,5 | 19,10 | 22 |
| Paloquemao | NQS Central | 50,9 | 18,21 | 23 |
| Hospital | Caracas Sur | 51,2 | 19,97 | 27 |
| Movistar Arena | NQS Central | 51,7 | 19,59 | 23 |
| Temporal AV. 39 | Caracas | 52,1 | 19,79 | 24 |
| Ricaurte - NQS | NQS Central | 52,7 | 18,96 | 24 |
| Centro Memoria | Calle 26 | 52,7 | 17,95 | 23 |
| Hortúa | Caracas Sur | 52,7 | 20,63 | 28 |
| Concejo de Bogotá | Calle 26 | 52,8 | 17,20 | 22 |
| Calle 45 - American School Way | Caracas | 53,4 | 20,35 | 25 |
| Ciudad Universitaria - Lotería de Bogotá | Calle 26 | 53,6 | 17,54 | 22 |
| 7 de Agosto | NQS Central | 53,6 | 20,42 | 24 |
| Temporal AV. Jiménez - Inter Eléctricas (Eje Ambiental) | Eje Ambiental | 53,6 | 18,91 | 26 |
| De La Sabana | Americas | 54,1 | 19,08 | 26 |
| Nariño | Caracas Sur | 54,3 | 21,27 | 29 |
| Temporal Marly | Caracas | 54,7 | 20,89 | 26 |
| Museo del Oro | Eje Ambiental | 55,4 | 19,64 | 26 |
| Corferias | Calle 26 | 55,6 | 18,38 | 23 |
| Comuneros | NQS Sur | 55,7 | 20,20 | 25 |
| San Facon Carrera 22 | Americas | 55,8 | 19,35 | 25 |
| Guatoque - Veraguas | NQS Central | 55,9 | 20,29 | 25 |
| Fucha | Caracas Sur | 56,0 | 22,01 | 30 |
| AV. Chile | NQS Central | 56,2 | 21,49 | 25 |
| Restrepo | Caracas Sur | 56,6 | 22,24 | 31 |
| Universidades – CityU | Calle 26 | 56,6 | 19,86 | 24 |
| Santa Isabel | NQS Sur | 56,7 | 20,65 | 26 |
| Quinta Paredes | Calle 26 | 56,8 | 18,88 | 24 |
| Tygua - San José | NQS Central | 56,8 | 20,23 | 26 |
| Las Aguas - Centro Colombo Americano | Eje Ambiental | 56,9 | 20,12 | 25 |
| Ricaurte - CL 13 | Americas | 57,0 | 18,85 | 24 |
| Temporal Calle 57 | Caracas | 57,1 | 21,87 | 27 |
| Calle 75 - Zona M | NQS Central | 57,5 | 22,05 | 26 |
| CDS - Carrera 32 | Americas | 57,6 | 18,92 | 24 |
| Calle 63 | Caracas | 58,0 | 22,25 | 28 |
| Olaya | Caracas Sur | 58,3 | 22,98 | 32 |
| Gobernación | Calle 26 | 58,5 | 19,61 | 25 |
| Temporal Flores – Areandina | Caracas | 59,1 | 22,74 | 29 |
| SENA | NQS Sur | 59,2 | 21,67 | 27 |
| Zona Industrial | Americas | 59,3 | 19,62 | 25 |
| San Diego | Carrera 10 | 59,4 | 18,92 | 24 |
| San Victorino | Carrera 10 | 59,7 | 19,34 | 26 |
| CAN | Calle 26 | 59,7 | 20,11 | 26 |
| La Castellana | NQS Central | 59,8 | 23,03 | 27 |
| Bicentenario | Carrera 10 | 59,8 | 20,38 | 27 |
| Museo Nacional | Carrera 7 | 59,9 | 19,15 | 24 |
| Carrera 43 - Comapan | Americas | 60,3 | 20,03 | 26 |
| Quiroga | Caracas Sur | 60,3 | 23,79 | 33 |
| Las Nieves | Carrera 10 | 60,5 | 19,54 | 25 |
| Calle 72 - Areandina | Caracas | 60,7 | 23,39 | 29 |
| San Bernardo | Carrera 10 | 60,8 | 20,79 | 28 |
| Salitre - El Greco | Calle 26 | 61,0 | 20,65 | 27 |
| NQS - Calle 30 S | NQS Sur | 61,3 | 22,55 | 28 |
| Puente Aranda | Americas | 61,4 | 20,51 | 27 |
| Calle 40 Sur | Caracas Sur | 61,8 | 24,43 | 34 |
| Calle 76 - San Felipe | Caracas | 62,0 | 23,93 | 28 |
| Policarpa | Carrera 10 | 62,1 | 21,33 | 29 |
| Cl38A sur - CENTRO MAYOR | NQS Sur | 62,8 | 23,19 | 29 |
| El Tiempo – Cámara de Comercio de Bogotá | Calle 26 | 62,9 | 21,46 | 28 |
| Héroes - Colmena Seguros | Autopista Norte | 63,3 | 24,11 | 28 |
| Distrito Grafiti | Americas | 63,4 | 21,36 | 28 |
| Ciudad Jardín - UAN | Carrera 10 | 63,6 | 21,96 | 30 |
| Santa Lucía | Caracas Sur | 63,7 | 25,25 | 35 |
| Polo - FINCOMERCIO | Calle 80 | 64,2 | 23,17 | 27 |
| Avenida Rojas - UNISALESIANA | Calle 26 | 64,4 | 22,10 | 29 |
| Calle 85 | Autopista Norte | 64,5 | 24,57 | 29 |
| General Santander | NQS Sur | 64,5 | 23,90 | 30 |
| Escuela Militar | Calle 80 | 64,7 | 22,96 | 27 |
| AV. 1 Mayo | Carrera 10 | 65,1 | 22,59 | 31 |
| Pradera - Plaza Central | Americas | 65,3 | 22,15 | 29 |
| Virrey | Autopista Norte | 65,4 | 24,99 | 29 |
| Alquería | NQS Sur | 65,6 | 24,36 | 31 |
| Socorro | Caracas Sur | 65,6 | 26,03 | 36 |
| Carrera 47 | Calle 80 | 65,7 | 23,41 | 28 |
| Normandía | Calle 26 | 66,6 | 23,02 | 30 |
| Consuelo | Caracas Sur | 66,9 | 26,58 | 37 |
| Country Sur | Carrera 10 | 67,1 | 23,41 | 32 |
| Carrera 53 | Calle 80 | 67,3 | 24,06 | 29 |
| Calle 100 - Marketmedios | Autopista Norte | 67,6 | 24,33 | 28 |
| Molinos | Caracas Sur | 67,9 | 26,98 | 38 |
| Venecia | NQS Sur | 67,9 | 25,33 | 32 |
| Marsella | Americas | 68,3 | 23,43 | 30 |
| Modelia | Calle 26 | 68,5 | 23,82 | 31 |
| AV. 68 | Calle 80 | 68,7 | 24,67 | 30 |
| Sevillana | NQS Sur | 69,1 | 25,84 | 33 |
| Portal 20 de Julio | Carrera 10 | 69,1 | 24,27 | 33 |
| AV. Américas - AV. Boyacá | Americas | 69,4 | 23,88 | 31 |
| Calle 106 - Maletas Explora | Autopista Norte | 70,0 | 25,34 | 29 |
| Ferias | Calle 80 | 70,4 | 25,35 | 31 |
| Portal El Dorado – C.C. Nuestro Bogotá | Calle 26 | 70,6 | 24,68 | 32 |
| San Martín | Suba | 70,7 | 23,38 | 28 |
| Biblioteca | Caracas Sur | 70,7 | 26,06 | 36 |
| Danubio | Caracas Sur | 70,8 | 28,20 | 39 |
| AV. Boyacá | Calle 80 | 71,3 | 25,73 | 32 |
| Mandalay | Americas | 71,3 | 24,67 | 32 |
| Pepe Sierra Universidad UTEL | Autopista Norte | 71,4 | 25,92 | 30 |
| CC Paseo Villa del Río - Madelena | NQS Sur | 71,6 | 26,91 | 34 |
| Rionegro | Suba | 71,9 | 23,89 | 29 |
| Parque | Caracas Sur | 72,1 | 26,66 | 37 |
| Banderas | Americas | 72,5 | 25,17 | 33 |
| Minuto de Dios | Calle 80 | 72,9 | 26,42 | 33 |
| Calle 127 | Autopista Norte | 73,1 | 26,65 | 31 |
| Portal Tunal | Caracas Sur | 73,1 | 27,09 | 38 |
| Suba - Calle 95 | Suba | 73,2 | 24,45 | 30 |
| Perdomo | NQS Sur | 73,8 | 27,81 | 35 |
| Suba - Calle 100 | Suba | 73,8 | 24,70 | 31 |
| Granja - Kr 77 | Calle 80 | 74,1 | 26,93 | 34 |
| Transversal 86 | Americas | 74,4 | 25,97 | 34 |
| Portal Usme | Caracas Sur | 74,8 | 29,88 | 40 |
| Portal Sur - JFK Coop. Financiera | NQS Sur | 75,0 | 28,31 | 36 |
| AV. Cali | Calle 80 | 75,4 | 27,48 | 35 |
| Prado | Autopista Norte | 75,7 | 27,76 | 32 |
| Puentelargo | Suba | 75,8 | 25,52 | 32 |
| Carrera 90 | Calle 80 | 77,0 | 28,13 | 36 |
| Biblioteca Tintal | Americas | 77,3 | 27,20 | 35 |
| Suba - Calle 116 | Suba | 77,4 | 26,23 | 33 |
| Alcalá – Colegio S. Tomás Dominicos | Autopista Norte | 77,5 | 28,50 | 33 |
| Quirigua | Calle 80 | 78,1 | 28,59 | 37 |
| Bosa | NQS Sur | 78,1 | 29,62 | 37 |
| Portal 80 | Calle 80 | 79,0 | 28,97 | 38 |
| Calle 142 | Autopista Norte | 79,0 | 29,14 | 34 |
| Patio Bonito | Americas | 79,3 | 28,04 | 36 |
| Humedal Córdoba | Suba | 79,4 | 27,07 | 34 |
| La Despensa | NQS Sur | 80,0 | 30,44 | 38 |
| Calle 146 | Autopista Norte | 80,1 | 29,59 | 35 |
| Niza - Calle 127 | Suba | 80,9 | 27,67 | 35 |
| Mazurén | Autopista Norte | 81,1 | 30,01 | 36 |
| León XIII | NQS Sur | 81,5 | 31,05 | 39 |
| Portal Américas | Americas | 81,8 | 29,10 | 37 |
| Calle 161 | Autopista Norte | 83,0 | 30,83 | 37 |
| Terreros - Hospital Cardio Vascular | NQS Sur | 83,4 | 31,85 | 40 |
| Suba - AV. Boyacá | Suba | 83,4 | 28,74 | 36 |
| Toberin - Foundever | Autopista Norte | 84,2 | 31,31 | 38 |
| San Mateo - CC Unisur | NQS Sur | 85,0 | 32,54 | 41 |
| Gratamira | Suba | 85,0 | 29,42 | 37 |
| Portal Norte – Unicervantes | Autopista Norte | 86,4 | 32,25 | 39 |
| 21 Ángeles | Suba | 88,2 | 30,73 | 38 |
| Calle 187 | Autopista Norte | 88,6 | 33,18 | 40 |
| Islandia | Avenida Ciudad de Cali | 88,7 | 31,99 | 38 |
| Terminal | Autopista Norte | 90,1 | 33,79 | 41 |
| Suba - TV. 91 | Suba | 90,2 | 31,59 | 39 |
| Los Laureles | Avenida Ciudad de Cali | 91,4 | 33,13 | 39 |
| La Campiña | Suba | 91,6 | 32,19 | 40 |
| Portal Suba | Suba | 93,0 | 32,76 | 41 |
| Tibanica - Primavera | Avenida Ciudad de Cali | 93,0 | 33,79 | 40 |

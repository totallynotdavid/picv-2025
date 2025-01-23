! Crea un archivo en Latex reporte.tex automatico en Fortran
! Cesar Jimenez 23 Mar 2022
! Modificado: 29 Jul 2023

integer i,j,k,pos,I0,J0
integer hh1,hh2,hh3,mm1,mm2,mm3
real    xo,yo,xep,yep,a,b,slip,L,W,Az,echado,rake,h,M0,Mw
real    max01, max02, max03, ttt1, ttt2, ttt3

OPEN(1,FILE='meca.dat',STATUS='OLD')
READ(1,*) xep, yep, zep, Az, echado, rake, Mw
CLOSE(1)
if (xep > 180.0) then
   xep = xep-360.0
end if
OPEN(3,FILE='ttt_max.dat',STATUS='OLD')
READ(3,*) ttt1, max01
READ(3,*) ttt2, max02
READ(3,*) ttt3, max03
CLOSE(3)
hh01 = real(ttt1)/60.0
hh02 = real(ttt2)/60.0
hh03 = real(ttt3)/60.0

hh1 = ttt1/60
mm1 = mod(ttt1,60.0)
hh2 = ttt2/60
mm2 = mod(ttt2,60.0)
hh3 = ttt3/60
mm3 = mod(ttt3,60.0)

OPEN(2,FILE='reporte.tex')
write(2,*) '\documentclass[a4paper,11pt]{article}'
write(2,*) '\usepackage{latexsym}'
write(2,*) '\usepackage[utf8]{inputenc}'
write(2,*) '\usepackage[activeacute,spanish]{babel}'
write(2,*) '\RequirePackage{graphicx}'
write(2,*) '\RequirePackage{booktabs}'
write(2,*) '\title{REPORTE: ESTIMACIÓN DE PARÁMETROS DE TSUNAMI DE ORIGEN LEJANO}'
write(2,*) '\author{Cesar Jimenez \\'
write(2,*) '(Version: 1.2)}'
write(2,*) '\frenchspacing'
write(2,*) '\begin{document}'
write(2,*) '\renewcommand{\tablename}{Tabla}'
write(2,*) '\maketitle'
write(2,*) '\section*{Introducción}'
write(2,*) '\noindent'
write(2,*) 'Este reporte preliminar de tsunami de origen lejano ha sido '
write(2,*) 'elaborado en forma automática por el modelo numérico TSDHN-2022.'
write(2,*) 'Las dimensiones de la fuente sísmica se calculan a partir de las ecuaciones de Papazachos et al. (2004).'
write(2,*) 'El mecanismo focal del terremoto se toma de la base de datos del Global CMT.'
write(2,*) 'El campo de deformación se obtiene a partir de las ecuaciones analíticas de'
write(2,*) ' Okada (1992).'
write(2,*) ' '
write(2,*) 'La simulación de la propagación del tsunami se realiza con el modelo '
write(2,*) 'numérico TUNAMI, modelo lineal y en coordenadas esféricas (Imamura et al.,'
write(2,*) ' 2006). La grilla batimétrica computacional abarca todo el Océano Pacífico, '
write(2,*) 'con una resolución de 4 min o 240 s. El cálculo de las isócronas de '
write(2,*) 'tiempos de arribo para todo el Océano Pacífico se realizó con el modelo '
write(2,*) 'Tsunami Travel Time (Wessel, 2009).'
write(2,*) ' '
write(2,*) 'Se han colocado 3 mareógrafos virtuales en los puertos de Talara, Callao y '
write(2,*) 'Matarani. Se utilizó la ley de Green para la corrección de la amplitud de '
write(2,*) 'los mareogramas, debido a que los nodos computacionales no coinciden '
write(2,*) 'necesariamente con la ubicación de las estaciones mareográficas costeras '
write(2,*) '(Satake, 2015).'
write(2,*) ' '
write(2,*) 'El tiempo promedio de cómputo para una PC i7 es de 15 min para una ventana '
write(2,*) 'de tiempo de simulación de 28 horas (Figura 1). Sin embargo, el '
write(2,*) 'supercomputador DHN demora menos de 2 minutos. \\'
write(2,*) ' '
write(2,*) '\noindent \textbf{Nota:} El resultado del modelo TSDHN-2022 es una estimación referencial y de preferencia debe ser utilizado para'
write(2,*) 'obtener los parámetros de tsunamis de origen lejano, es decir fuera de las fronteras del litoral de Perú.'
write(2,*) 'Para eventos de origen cercano, se debe utilizar el modelo Pre-Tsunami (Jimenez et al., 2018).'

write(2,*) '\begin{table*}'
write(2,*) '\centerline{'
write(2,*) '\begin{tabular}[t]{lp{0.5cm}l}'
write(2,*) '\toprule'
!write(2,*) 'Date       & & Oct 17, 1966 \\'
write(2,*) 'Parámetro   & & Valor \\'
write(2,*) '\midrule'
!write(2,*) 'Origin time UTC    & & 21:41:51    \\  '  
write(2,100) 'Latitud     & & ',yep,'$^\circ$  \\'
write(2,100) 'Longitud    & & ',xep,'$^\circ$  \\'
write(2,101) 'Profundidad & & ',zep,' km       \\'
write(2,101) 'Magnitud    & & ',Mw ,' Mw       \\'
write(2,*) '\midrule'
write(2,101) 'Strike      & & ',Az ,'$^\circ$  \\'
write(2,101) 'Dip         & & ',echado,'$^\circ$  \\'   
write(2,101) 'Rake        & & ',rake,'$^\circ$  \\'
write(2,*) '\bottomrule'
write(2,*) '\end{tabular}}'
write(2,*) '\caption{Parámetros hipocentrales y mecanismo focal del terremoto.}'
write(2,*) '\end{table*}'

write(2,*) '\begin{figure}'
write(2,*) '\centerline{\includegraphics[scale=0.88]{maxola.eps}}'
write(2,*) '\caption{Mapa de máxima altura de propagación del tsunami. La esfera' 
write(2,*) 'focal representa el epicentro. Los triángulos azules representan ' 
write(2,*) 'a las estaciones mareográficas.}'
write(2,*) '\label{max_ola}'
write(2,*) '\end{figure}'

write(2,*) '\section*{Análisis}'
write(2,*) 'La Tabla 1 muestra los parámetros hipocentrales y el mecanismo focal del '
write(2,*) 'terremoto. La Figura 1 muestra el mapa de propagacion de la máxima energía,'
write(2,*) 'la ubicación del epicentro está representado por la esfera focal y las '
write(2,*) 'estaciones mareográficas están representadas por los triángulos azules'
write(2,*) ' '
write(2,*) 'La Figura 2 muestra las isócronas de los tiempos de arribo del tsunami para '
write(2,*) 'todo el Oceano Pacifico. La Figura 3 muestra los mareogramas simulados para '
write(2,*) 'las estaciones del litoral del Perú, de norte a sur: Talara, Callao y '
write(2,*) 'Matarani. La Tabla 2 muestra los valores de los tiempos de arribo y la '
write(2,*) 'máxima altura del tsunami en las estaciones mareográficas del litoral '
write(2,*) 'Peruano.'

write(2,*) '\begin{figure}'
write(2,*) '\centerline{\includegraphics[scale=0.78]{ttt.eps}}'
write(2,*) '\caption{Mapa de tiempo de arribo del tsunami. La esfera focal representa el '
write(2,*) 'epicentro.}' 
write(2,*) '\label{ttt}'
write(2,*) '\end{figure}'

write(2,*) '\begin{figure}'
write(2,*) '\centerline{\includegraphics[scale=0.84]{mareograma.eps}}'
write(2,*) '\caption{Mareogramas simulados en las estaciones de Talara, Callao y Matarani.}'
write(2,*) '\end{figure}'

write(2,*) '\begin{table*}'
write(2,*) '\centerline{'
write(2,*) '\begin{tabular}[t]{lcc}'
write(2,*) '\toprule'
write(2,*) 'Estación     & Tiempo de arribo & Máximo (m) \\'
write(2,*) '\midrule'
if (mm1 >= 10) then
   write(2,200) 'Talara     &',hh1,':',mm1,' & ',max01,'  \\'
   else if (mm1 < 10) then
   write(2,201) 'Talara     &',hh1,':0',mm1,' & ',max01,'  \\'
end if
if (mm2 >= 10) then
   write(2,200) 'Callao     &',hh2,':',mm2,' & ',max02,'  \\'
   else if (mm2 < 10) then
   write(2,201) 'Callao     &',hh2,':0',mm2,' & ',max02,'  \\'
end if
if (mm3 >= 10) then
   write(2,200) 'Matarani   &',hh3,':',mm3,' & ',max03,'  \\'
   else if (mm3 < 10) then
   write(2,201) 'Matarani   &',hh3,':0',mm3,' & ',max03,'  \\'
end if   
write(2,*) '\bottomrule'
write(2,*) '\end{tabular}}'
write(2,*) '\caption{Tiempo de arribo (hh:mm) y máxima amplitud del tsunami.}'
write(2,*) '\end{table*}'

write(2,*) '\begin{thebibliography}{99}'
write(2,*) '\bibitem{1} B. Papazachos, E. Scordilis, C. Panagiotopoulus and G. Karakaisis. Global relations between seismic'
write(2,*) 'fault parameters and moment magnitude of earthquakes. Bulletin of Geological '
write(2,*) 'Society of Greece, vol XXXVI, pp 1482-1489 (2004).'
write(2,*) '\bibitem{2} Y. Okada. Internal deformation in a half space. Bull. Seismol. Soc.Am. {82}(2) 1018-1040 (1992).'
write(2,*) '\bibitem{3} F. Imamura, A. Yalciner and G. Ozyurt. Tsunami Modelling Manual'
write(2,*) '(TUNAMI model). Tohoku University, Sendai. (2006).'
write(2,*) '\bibitem{4} P. Wessel. Analysis of observed and predicted tsunami travel times for the Pacific and Indian Oceans. Pure Appl. Geophys., vol 166, pp 301--324 (2009).'
write(2,*) '\bibitem{5} K. Satake. Tsunamis, inverse problem of. Encyclopedia of Complexity and Systems Science, pp 1--20 (2015).'
write(2,*) '\bibitem{6} C. Jiménez, C. Carbonel and J. Rojas. Numerical procedure to forecast the tsunami parameters from a'
write(2,*) 'database of pre-simulated seismic unit sources. Pure Appl. Geophys., vol 175, pp 1473--1483 (2018).'
write(2,*) '\end{thebibliography}'

write(2,*) '\end{document}'
100 format (A16 f7.2 A12)
101 format (A16 f6.1 A12)
200 format (A12,I2,A1,I2,A3,f6.2,A4) 
201 format (A12,I2,A2,I1,A3,f6.2,A4) 
CLOSE(2)
write(*,*)'Se creó el archivo reporte.tex'
 
end


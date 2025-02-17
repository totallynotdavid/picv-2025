! Crea un archivo en Latex reporte.tex automatico en Fortran
! Cesar Jimenez 23 Mar 2022
! Modificado: 23 Mar 2024

integer i,j,k,pos,I0,J0
integer hh1,hh2,hh3,hh4,hh5,hh6,hh7,hh8,hh9,hh10,hh11,hh12,hh13,hh14,hh15,hh16,hh17
integer mm1,mm2,mm3,mm4,mm5,mm6,mm7,mm8,mm9,mm10,mm11,mm12,mm13,mm14,mm15,mm16,mm17,cero1,cero2
integer :: value(8)
real  xo,yo,xep,yep,a,b,slip,L,W,Az,echado,rake,h,M0,Mw
real  max01,max02,max03,max04,max05,max06,max07,max08,max09, max10,max11,max12,max13,max14,max15,max16,max17 
real  ttt1,ttt2,ttt3,ttt4,ttt5,ttt6,ttt7,ttt8,ttt9,ttt10,ttt11,ttt12,ttt13,ttt14,ttt15,ttt16,ttt17
character(len=4) :: t0
character(8) :: date
character(10):: time
character(5) :: zone
character(3) :: mes

OPEN(1,FILE='meca.dat',STATUS='OLD')
READ(1,*) xep, yep, zep, Az, echado, rake, Mw, cero1, cero2, t0
CLOSE(1)
if (xep > 180.0) then
   xep = xep-360.0
end if
OPEN(3,FILE='ttt_max.dat',STATUS='OLD')
READ(3,*) ttt1, max01
READ(3,*) ttt2, max02
READ(3,*) ttt3, max03
READ(3,*) ttt4, max04
READ(3,*) ttt5, max05
READ(3,*) ttt6, max06
READ(3,*) ttt7, max07
READ(3,*) ttt8, max08
READ(3,*) ttt9, max09
READ(3,*) ttt10, max10
READ(3,*) ttt11, max11
READ(3,*) ttt12, max12
READ(3,*) ttt13, max13
READ(3,*) ttt14, max14
READ(3,*) ttt15, max15
READ(3,*) ttt16, max16
READ(3,*) ttt17, max17
CLOSE(3)
hh01 = real(ttt1)/60.0
hh02 = real(ttt2)/60.0
hh03 = real(ttt3)/60.0
hh04 = real(ttt4)/60.0
hh05 = real(ttt5)/60.0
hh06 = real(ttt6)/60.0
hh07 = real(ttt7)/60.0
hh08 = real(ttt8)/60.0
hh09 = real(ttt9)/60.0
hh10 = real(ttt10)/60.0
hh11 = real(ttt11)/60.0
hh12 = real(ttt12)/60.0
hh13 = real(ttt13)/60.0
hh14 = real(ttt14)/60.0
hh15 = real(ttt15)/60.0
hh16 = real(ttt16)/60.0
hh17 = real(ttt17)/60.0

hh1 = ttt1/60
mm1 = mod(ttt1,60.0)
hh2 = ttt2/60
mm2 = mod(ttt2,60.0)
hh3 = ttt3/60
mm3 = mod(ttt3,60.0)
hh4 = ttt4/60
mm4 = mod(ttt4,60.0)
hh5 = ttt5/60
mm5 = mod(ttt5,60.0)
hh6 = ttt6/60
mm6 = mod(ttt6,60.0)
hh7 = ttt7/60
mm7 = mod(ttt7,60.0)
hh8 = ttt8/60
mm8 = mod(ttt8,60.0)
hh9 = ttt9/60
mm9 = mod(ttt9,60.0)
hh10 = ttt10/60
mm10 = mod(ttt10,60.0)
hh11 = ttt11/60
mm11 = mod(ttt11,60.0)
hh12 = ttt12/60
mm12 = mod(ttt12,60.0)
hh13 = ttt13/60
mm13 = mod(ttt13,60.0)
hh14 = ttt14/60
mm14= mod(ttt14,60.0)
hh15 = ttt15/60
mm15 = mod(ttt15,60.0)
hh16 = ttt16/60
mm16 = mod(ttt16,60.0)
hh17 = ttt17/60
mm17 = mod(ttt17,60.0)


OPEN(2,FILE='reporte.tex')
write(2,*) '\documentclass[a4paper,11pt]{article}'
write(2,*) '\usepackage{latexsym}'
write(2,*) '\usepackage[utf8]{inputenc}'
write(2,*) '\usepackage[activeacute,spanish]{babel}'
write(2,*) '\RequirePackage{graphicx}'
write(2,*) '\RequirePackage{booktabs}'
write(2,*) '\title{REPORTE: ESTIMACIÓN DE PARÁMETROS DE TSUNAMI DE ORIGEN LEJANO}'
write(2,*) '\author{Cesar Jimenez \\'
write(2,*) '(Version: 1.3)}'
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
write(2,*) '\noindent \textbf{Nota:} El resultado del modelo TSDHN-2022 es una estimación'
write(2,*) 'referencial y de preferencia debe ser utilizado para obtener los parámetros'
write(2,*) 'de tsunamis de origen lejano, es decir fuera de las fronteras del litoral de Perú.'
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
if (mm2 >= 10) then
   write(2,200) 'Talara     &',hh2,':',mm2,' & ',max02,'  \\'
   else if (mm2 < 10) then
   write(2,201) 'Talara     &',hh2,':0',mm2,' & ',max02,'  \\'
end if
if (mm9 >= 10) then
   write(2,200) 'Callao     &',hh9,':',mm9,' & ',max09,'  \\'
   else if (mm9 < 10) then
   write(2,201) 'Callao     &',hh9,':0',mm9,' & ',max09,'  \\'
end if
if (mm15 >= 10) then
   write(2,200) 'Matarani   &',hh15,':',mm15,' & ',max15,'  \\'
   else if (mm15 < 10) then
   write(2,201) 'Matarani   &',hh15,':0',mm15,' & ',max15,'  \\'
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
write(2,*) '\bibitem{4} P. Wessel. Analysis of observed and predicted tsunami travel times'
write(2,*) 'for the Pacific and Indian Oceans. Pure Appl. Geophys., vol 166, pp 301--324 (2009).'
write(2,*) '\bibitem{5} K. Satake. Tsunamis, inverse problem of. Encyclopedia of Complexity and Systems Science, pp 1--20 (2015).'
write(2,*) '\bibitem{6} C. Jimenez, C. Carbonel and J. Rojas. Numerical procedure to forecast the tsunami parameters from a'
write(2,*) 'database of pre-simulated seismic unit sources. Pure Appl. Geophys., vol 175, pp 1473--1483 (2018).'
write(2,*) '\end{thebibliography}'

write(2,*) '\end{document}'
100 format (A16 f7.2 A12)
101 format (A16 f6.1 A12)
200 format (A12,I2,A1,I2,A3,f6.2,A4) 
201 format (A12,I2,A2,I1,A3,f6.2,A4) 
CLOSE(2)
write(*,*)'Se creó el archivo reporte.tex'

call Date_and_Time(date, time, zone, value)
if (value(2) ==  1) then 
  mes = 'Ene' 
endif
if (value(2) ==  2) then 
  mes = 'Feb' 
endif
if (value(2) ==  3) then 
  mes = 'Mar'  
endif
if (value(2) ==  4) then 
  mes = 'Abr' 
endif
if (value(2) ==  5) then 
  mes = 'May' 
endif
if (value(2) ==  6) then 
  mes = 'Jun' 
endif
if (value(2) ==  7) then 
  mes = 'Jul' 
endif
if (value(2) ==  8) then 
  mes = 'Ago' 
endif
if (value(2) ==  9) then 
  mes = 'Set' 
endif
if (value(2) == 10) then  
  mes = 'Oct' 
endif
if (value(2) == 11) then 
  mes = 'Nov' 
endif
if (value(2) == 12) then 
  mes = 'Dic' 
endif

OPEN(4,FILE='salida.txt')
write(4,'(A43)') 'ESTIMACION DEL TIEMPO DE ARRIBO DE TSUNAMIS'
write(4,'(A26)') 'Coordenadas del epicentro: '
write(4,399) 'Fecha    = ',value(3),' ',mes,' ',value(1)
write(4,'(A11,A4)') 'Hora     = ',t0
write(4,400) 'Latitud  =  ',yep
write(4,400) 'Longitud =  ',xep
write(4,401) 'Profund  =  ',zep,' km'
write(4,402) 'Magnitud =  ',Mw
write(4,'(A15,A8,A1,A4)') 'Tiempo actual: ',date,' ',time
write(4,'(A55)') 'Departamento Puertos    Hora_llegada  Hmax(m)  T_arribo'
!write(4,403)'Piura       Talara         ',hh1,':',mm1,'   ',max01,'     ',hh1,':',mm1
!write(4,403)'Lima        Callao         ',hh2,':',mm2,'   ',max02,'     ',hh2,':',mm2
!write(4,403)'Arequipa    Matarani        ',hh3,':',mm3,'   ',max03,'     ',hh3,':',mm3
write(4,403)'Tumbes      La Cruz         ',hh1,':',mm1,'   ',max01,'     ',hh1,':',mm1
write(4,403)'Piura       Talara          ',hh2,':',mm2,'   ',max02,'     ',hh2,':',mm2
write(4,403)'Piura       Paita           ',hh3,':',mm3,'   ',max03,'     ',hh3,':',mm3
write(4,403)'Lambayeque  Pimentel        ',hh4,':',mm4,'   ',max04,'     ',hh4,':',mm4
write(4,403)'La_Libertad Salaverry       ',hh5,':',mm5,'   ',max05,'     ',hh5,':',mm5
write(4,403)'Ancash      Chimbote        ',hh6,':',mm6,'   ',max06,'     ',hh6,':',mm6
write(4,403)'Ancash      Huarmey         ',hh7,':',mm7,'   ',max07,'     ',hh7,':',mm7
write(4,403)'Lima        Huacho          ',hh8,':',mm8,'   ',max08,'     ',hh8,':',mm8
write(4,403)'Lima        Callao          ',hh9,':',mm9,'   ',max09,'     ',hh9,':',mm9
write(4,403)'Lima        Cerro Azul      ',hh10,':',mm10,'   ',max10,'     ',hh10,':',mm10
write(4,403)'Ica         Pisco           ',hh11,':',mm11,'   ',max11,'     ',hh11,':',mm11
write(4,403)'Ica         San Juan        ',hh12,':',mm12,'   ',max12,'     ',hh12,':',mm12
write(4,403)'Arequipa    Atico           ',hh13,':',mm13,'   ',max13,'     ',hh13,':',mm13
write(4,403)'Arequipa    Camana          ',hh14,':',mm14,'   ',max14,'     ',hh14,':',mm14
write(4,403)'Arequipa    Matarani        ',hh15,':',mm15,'   ',max15,'     ',hh15,':',mm15
write(4,403)'Moquegua    Ilo             ',hh16,':',mm16,'   ',max16,'     ',hh16,':',mm16
write(4,403)'Chile       Arica           ',hh17,':',mm17,'   ',max17,'     ',hh17,':',mm17

write(4,'(A65)') '* La altura estimada NO considera la fase lunar ni oleaje anomalo'
399 format (A11,I2,A1,A3,A1,I4)
400 format (A11,f7.2) 
401 format (A11,f5.1,A3) 
402 format (A11,f3.1) 
403 format (A27,I2,A1,I2,A4,f6.2,A5,I2,A1,I2) 
CLOSE(4)
end


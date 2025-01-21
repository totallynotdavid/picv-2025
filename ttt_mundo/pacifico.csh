#!/bin/csh

set REGION1=120.0/180.0/-80.0/89.0
set REGION2=-180.0/-60.0/-80.0/89.0
set BATHYFILE0=/media/cjimenez/datos/Topografia/gebco30/GridOne.nc
set BATHYFILE1=cortado1.grd
set BATHYFILE2=cortado2.grd

#echo cut the bathymetry domain...
gmt grdcut $BATHYFILE0 -G$BATHYFILE1 -R$REGION1 -V 
# Resample the bathymetry
gmt grdsample $BATHYFILE1 -Gtemp1.grd -I240c/240c -R$REGION1 -V 
gmt grdmath temp1.grd -1 MUL -V = temp3.grd
gmt grd2xyz temp3.grd -R$REGION1 -s -fig -fog -V > salida1.xyz

#echo cut the bathymetry domain...
gmt grdcut $BATHYFILE0 -G$BATHYFILE2 -R$REGION2 -V 
# Resample the bathymetry
gmt grdsample $BATHYFILE2 -Gtemp1.grd -I240c/240c -R$REGION2 -V 
gmt grdmath temp1.grd -1 MUL -V = temp3.grd
gmt grd2xyz temp3.grd -R$REGION2 -s -fig -fog -V > salida2.xyz

rm temp*.*
rm cortado1.grd
rm cortado2.grd

#unir los 2 archivos
cat salida1.xyz salida2.xyz > salida.xyz
awk '{ print $1, $2, -$3 }' salida.xyz > pacifico.xyz
#convertir de xyz a grd
gmt xyz2grd pacifico.xyz -D+xm+ym+zm -Gpacifico.grd -R120/300/-80/89 -I240s

rm salida1.xyz
rm salida2.xyz
rm salida.xyz
rm pacifico.xyz


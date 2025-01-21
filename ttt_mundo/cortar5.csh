#!/bin/csh

set REGION = 180.0/300.0/-70.0/70.0
set BATHYFILE0=/media/cjimenez/datos/Topografia/gebco30/GridOne.nc
set BATHYFILE1=cortado.grd

#echo cut the bathymetry domain...
gmt grdcut $BATHYFILE0 -G$BATHYFILE1 -R$REGION -V 
#grd2xyz $BATHYFILE1 -R$REGION -s -fig -fog -V > salida.asc

# Resample the bathymetry
gmt grdsample $BATHYFILE1 -Gtemp1.grd -I120s/120s -R$REGION -V 
gmt grdmath temp1.grd -1 MUL -V = temp3.grd
gmt grd2xyz temp3.grd -R$REGION -s -fig -fog -V > salida2.xyz

#echo Transform to raster...
#set PSPATH=c:\programs\gs9.02\bin\gswin64c
#ps2raster %PSFILE% -A -Tg -V -G%PSPATH%    

#rm temp*.*
#rm cortado.grd

# Convertir xyz a grd
#gmt xyz2grd salida.xyz -Gsalida.grd -V -R130/292/-60/60 -I120s/120s
#gmt grdmath salida.grd -1 MUL -V = salida2.grd

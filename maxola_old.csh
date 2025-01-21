#!/bin/csh
#rm .gmtdefaults4 
#rm .gmtcommands4 
rm *.ps

set lon0 = 210
set lat0 = -10
set REGION = -230.0/-68.0/-60.0/55.0
set AXIS = a20f10.0/a20f10.0WesN
set SIZE = A$lon0/$lat0/5.0i
#set SIZE = M15c
set dspgrid = maxola.grd
set psfile = maxola.ps
set cptfile1 = depth.cpt
set cptfile2 = hgt.cpt
set cmtfile = meca.dat

gmt set MAP_FRAME_TYPE=plain
gmt set FONT_ANNOT_PRIMARY = 12
gmt set FONT_LABEL = 12
gmt set FONT_TITLE = 12
gmt set PS_MEDIA A4

gmt makecpt -Cglobe > $cptfile1
gmt makecpt -Cpolar -T-0.001/0.001/0.0001 -Z >! $cptfile2
echo B 0 0 255 >> $cptfile2
echo F 255 0 0 >> $cptfile2
echo N 255 255 255 >> $cptfile2

./espejo
gmt grdconvert maximo.grd -Gmaxola.grd -V

gmt grdimage $dspgrid -R$REGION -J$SIZE -C$cptfile2 -X4.2c -Y10.0c -P -K -V >> $psfile

#Maxima altura de ola		 
gmt pscoast -R -J$SIZE -B$AXIS -N1 -Dc -A1000 -Dl -W0.5 -Ggray -P -O -K >> $psfile
#gmt pscoast -J$SIZE -R$REGION -B$AXIS -N1 -Dc -W0.5 -K -V -O -Lf-100.0/-52.0/-77.5/16.0/2000+lkm >> $psfile

# Mareografos
awk '{ print $1-1, $2 }' tidal.txt | gmt psxy -J$SIZE -R$REGION -St0.35c -G0/0/255 -W0.5 -K -O -V >> $psfile

gmt pstext -R -J$SIZE -Wwhite -O -K <<EOF>> $psfile
-78.45 -01.50 10 0 1 LT Tala
-76.00 -09.50 10 0 1 LT Call
-71.00 -14.50 10 0 1 LT Mata
EOF

#Mecanismo Focal CMT (-77.04 -13.73 33.8 321 28 63 8.0 0 0)
gmt psmeca $cmtfile -R$REGION -J$SIZE -Sa0.23c -G0/0/255 -P -O -V -K >> $psfile
#gmt psmeca -R$REGION -J$SIZE -Sa0.19c -G0/0/255 -P -O -V -K <<EOF>> $psfile
#-72.00  -36.0  22.0 360 18 90 9.0 0 0 
#EOF

gmt pstext -R -J$SIZE -P -O -V -K <<EOF>> $psfile
$lon0 $lat0 16 0 0 CT +
#$lon0 -90 16 0 0 CT *
$lon0 10.0 10 0 1 CT PACIFIC OCEAN
EOF

ps2eps $psfile -f
#evince $psfile &
rm maximo.grd
rm $psfile &

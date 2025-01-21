#!/bin/csh -f
set datafile = ./zfolder/green_rev.dat
set SIZE = 15.0c/3.0c
set psfile = mareograma.ps
set dy = 4.2c
set tdur = 28 #1680

gmt set MAP_FRAME_TYPE=plain
gmt set FONT_ANNOT_PRIMARY 9
gmt set FONT_LABEL 9
gmt set FONT_TITLE 9
gmt set PS_MEDIA A4

set nametage2 = Talara
set REGION = 0/$tdur/-$1/$1
set AXIS = a2g1:"":/a$1g1.:"":SW
gmt psbasemap -JX$SIZE -R$REGION -B$AXIS -P -K -X3.0c -Y24.0c > $psfile
awk '{ print $1,$2 }' $datafile | gmt psxy -W.5,blue -JX$SIZE -R$REGION -K -O -P >> $psfile
gmt pstext -JX$SIZE -R0/10/0/4 -K -O << END >> $psfile
0.2 4.0 11 0 0 LT $nametage2
END

set nametage2 = Callao
set REGION = 0/$tdur/-$1/$1
set AXIS = a2g1:"":/a$1g1.:"H\40(m)":SW
gmt psbasemap -JX$SIZE -R$REGION -B$AXIS -P -K -X0 -Y-$dy -O >> $psfile
awk '{ print $1,$3 }' $datafile | gmt psxy -W.5,blue -JX$SIZE -R$REGION -K -O -P >> $psfile
gmt pstext -JX$SIZE -R0/10/0/4 -K -O -V << END >> $psfile
0.2 4.0 11 0 0 LT $nametage2
END

set nametage2 = Matarani
set REGION = 0/$tdur/-$1/$1
set AXIS = a2g1:"Time\40(h)":/a$1g1.:"":SW
gmt psbasemap -JX$SIZE -R$REGION -B$AXIS -P -K -X0 -Y-$dy -O >> $psfile
awk '{ print $1,$4 }' $datafile | gmt psxy -W.5,blue -JX$SIZE -R$REGION -K -O -P >> $psfile
gmt pstext -JX$SIZE -R0/10/0/4 -K -O -V << END >> $psfile
0.2 4.0 11 0 0 LT $nametage2
END

#evince $psfile &
ps2eps $psfile -f
#ps2pdf mareograma.eps
rm $psfile &


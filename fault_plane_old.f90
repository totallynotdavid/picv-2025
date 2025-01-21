! fault_plane automatico en Fortran
! Cesar Jimenez 23 Mar 2022
! IA,JA : dimensiones de la grilla de batimetria
! m n   : dimensiones del archivo mecfoc.dat
! Modificado: 15 Nov 2022

PARAMETER (IA=2461, JA=2056, m=310, n=11)
DIMENSION xa(IA),dx(IA),ya(JA),dy(JA),lon(m),lat(m),dist(m)
real, dimension(:,:), allocatable:: A1
integer i,j,k,pos,I0,J0
real    xo,yo,xep,yep,a,b,slip,L,W,Az,echado,rake,h,M0,Mw

write (*,*) 'Parametros hipocentrales'
write (*,*) 'Longitud = '
read (*,*) xep
write (*,*) 'Latitud = '
read (*,*) yep
write (*,*) 'Profundidad (km)= '
read (*,*) zep
write (*,*) 'Magnitud = '
read (*,*) Mw

pi = 4.0*atan(1.0)
if (xep < 0.0) then 
  xep = xep+360.0 
end if 

L = 10**(0.55*Mw-2.19)*1e3 ! (m) Papazachos 2004
W = 10**(0.31*Mw-0.63)*1e3 ! (m)
M0 = 10**(1.5*Mw+9.1)
u = 4.0e10 ! (N/m2) coeficiente de rigidez promedio
slip = M0/(u*L*W)

! Calcular el mecanismo focal 
 allocate (A1(m,n))
 OPEN(1,FILE='mecfoc.dat',STATUS='OLD')
 DO I=1,m
   READ(1,*) (A1(I,J),J=1,n)
 end do
CLOSE(1)

do k =1,m
  lon(k) = A1(k,1)
  lat(k) = A1(k,2)
  if (lon(k) < 0) then 
    lon(k) = lon(k)+360 
  end if 
  dist(k) = sqrt((lon(k)-xep)**2+(lat(k)-yep)**2)
end do 

pos = minloc(dist,1)
Az = A1(pos,3) ! strike
echado = A1(pos,4) !dip
rake = 90 ! A1(pos,5);
deallocate (A1)

W1 = W*cos(echado*pi/180) 
beta = atan(W1/L)*180/pi 
alfa = Az - 270 
h = sqrt(L*L+W1*W1) 
a = 0.5*h*sin((alfa+beta)*pi/180)/1000 
b = 0.5*h*cos((alfa+beta)*pi/180)/1000 
xo = xep+b/111.0 
yo = yep-a/111.0 

 OPEN(2,FILE='./bathy/xa.dat')
 DO I=1,IA
   READ(2,*) xa(I)
   dx(I) = abs(xa(I)-xo)
 end do
 CLOSE(2)
 OPEN(3,FILE='./bathy/ya.dat')
 DO J=1,JA
   READ(3,*) ya(J)
   dy(J) = abs(ya(J)-yo)
 end do
 CLOSE(3)

pos = minloc(dx,1)
I0 = pos
pos = minloc(dy,1)
J0 = pos

! Calculo de la profundidad de la parte superior de la falla 
delta_x = (xep-xo)*111.0
delta_y = (yep-yo)*111.0
h = zep-(delta_x*cos(-Az*pi/180.0)+delta_y*sin(-Az*pi/180.0))*tan(echado*pi/180.0)
h = h*1e3
if (h < 0) then
  h = 5000 
end if
  
! Crear archivo pfalla.inp 
 OPEN(4,FILE='pfalla.inp')
 WRITE(4,*) I0, J0, slip, L, W, Az, echado, rake, h
 close(4)

! Calculo de la grilla de deformacion: IDS IDE JDS JDE
if (Mw > 8.0) then
  cte = 1.4
else
  cte = 2.8
end if
OPEN(5,FILE='xyo.dat')
IDS = xep - (cte*L/1000)/111.0
do I=1,IA
  dx(I) = abs(xa(I)-IDS)
end do
IDS = minloc(dx,1)
IDE = xep + (cte*L/1000)/111.0
do I=1,IA
  dx(I) = abs(xa(I)-IDE)
end do
IDE = minloc(dx,1)
JDS = yep - (cte*L/1000)/111.0
do J=1,JA
  dy(J) = abs(ya(J)-JDS)
end do
JDS = minloc(dy,1)
JDE = yep + (cte*L/1000)/111.0
do J=1,JA
  dy(J) = abs(ya(J)-JDE)
end do
JDE = minloc(dy,1)
WRITE(5,*) IDS,IDE,JDS,JDE, IA, JA
close(5)
 
! Archivo de mecanismo focal para maxola.csh
!-72.00  -36.0  22.0 360 18 90 9.0 0 0 
 OPEN(6,FILE='meca.dat')
 WRITE(6,'(7f7.2 A5)') xep, yep, zep, Az, echado, rake, Mw, ' 0 0 '
 close(6)

end


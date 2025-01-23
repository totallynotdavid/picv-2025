   clear all; close all; clc

  xep = -78.0; yep=-12.0; zep =15; Mw = 8.5; % coordenadas epicentro
  if xep < 0 xep = xep+360; end
  L = 10^(0.55*Mw-2.19)*1e3;   % (m) Papazachos 2004
  W = 10^(0.31*Mw-0.63)*1e3;   % (m)
  M0 = 10^(1.5*Mw+9.1);
  u = 4.0e10; % (N/m2) coeficiente de rigidez promedio
  slip = M0/(u*L*W);
% Calcular el mecanismo focal  
  A = load('mecfoc.dat');
  [m n] = size(A);
  lon = A(:,1);
  lat = A(:,2);
  for k = 1:m
      if lon(k) < 0 lon(k) = lon(k)+360; end
      dist(k) = sqrt((lon(k)-xep)^2+(lat(k)-yep)^2);
  end
  [minimo pos] = min(dist);
  Az = A(pos,3); % strike
  echado = A(pos,4); %dip
  rake = 90; % A(pos,5); 
% *************************************************************
   W1 = W*cos(echado*pi/180); % **********************************************
   beta = atan(W1/L)*180/pi; % ***********************************************
   alfa = Az - 270;% *********************************************************
   h = sqrt(L*L+W1*W1);% *****************************************************
   a = 0.5*h*sin((alfa+beta)*pi/180)/1000;% *************************************************************
   b = 0.5*h*cos((alfa+beta)*pi/180)/1000;% *************************************************************
   xo = xep+km2deg(b);%xe = xo - km2deg(b)% *************************************************************
   yo = yep-km2deg(a);%ye = yo + km2deg(a)% *************************************************************
load xya.mat;
%load grid_a.grd;
I0=find(abs(xa-xo) == min(abs(xa-xo))); I0=I0(1)
J0=find(abs(ya-yo) == min(abs(ya-yo))); J0=J0(1)

%figure; hold on;
%contour(xa,ya,grid_a',[4500 4500],'b');
%contour(xa,ya,grid_a',[0 0],'black');
%text(282.8520 ,  -12.052,' Callao');
%axis equal; grid on;

dip=echado*pi/180; 
a1=-(Az-90)*pi/180; a2=-(Az)*pi/180;
r1=L; r2=W*cos(dip);
r1=r1/(60*1853); r2=r2/(60*1853);
sx(1)=0;          sy(1)=0;
sx(2)=r1*cos(a1); sy(2)=r1*sin(a1);
sx(4)=r2*cos(a2); sy(4)=r2*sin(a2);
sx(3)=sx(4)+sx(2);sy(3)=sy(4)+sy(2);
sx(5)=sx(1)      ;sy(5)=sy(1);

sx=sx + xa(I0); sy=sy + ya(J0);

%plot(sx,sy,'k','linewidth',2);

px=xa(I0); py=ya(J0); % origen del plano de falla de acuerdo al modelo de tsunamis
%plot(px,py,'ro',xo,yo,'bo'), grid on
%plot (xep,yep,'*'), zoom
%hold on, plot(lon,lat,'*')

% Calculo de la profundidad de la parte superior de la falla
delta_x = deg2km(xep-xo);
delta_y = deg2km(yep-yo);
h = zep-(delta_x*cos(-Az*pi/180)+delta_y*sin(-Az*pi/180))*tan(echado*pi/180);
fprintf ('%s %4.3f %s\n','Profundidad de la parte superior de la falla =',h,'km');
if h < 0
    h = 5;
    disp ('Deberia mover (xo,yo) mas hacia la costa o tomar h = ')
    disp (h)
end

% Crear archivo pfalla.inp
  fname = ['pfallax.inp'];
  fid = fopen (fname, 'w');
  fprintf (fid,'%3.0f \n',I0);
  fprintf (fid,'%3.0f \n',J0);
  fprintf (fid,'%2.1f \n',slip); 
  fprintf (fid,'%6.1f \n',L);
  fprintf (fid,'%6.1f \n',W);
  fprintf (fid,'%3.1f \n',Az);
  fprintf (fid,'%3.1f \n',echado);
  fprintf (fid,'%3.1f \n',rake);
  fprintf (fid,'%3.1f \n',h*1e3);
  fclose all;
  
% Calculo de la grilla de deformacion: IDS IDE JDS JDE
fname2 = 'xyo.txt';
fid2 = fopen (fname2, 'w');
disp ('Creando parametros: IDS IDE JDS JDE') 
IDS = xep - km2deg(1.0*L/1000);
I0=find(abs(xa-IDS) == min(abs(xa-IDS))); IDS=I0(1);
fprintf ('%s %4.0f \n','IDS = ',IDS);
IDE = xep + km2deg(1.0*L/1000);
I0=find(abs(xa-IDE) == min(abs(xa-IDE))); IDE=I0(1);
fprintf ('%s %4.0f \n','IDE = ',IDE);
JDS = yep - km2deg(1.20*L/1000);
J0=find(abs(ya-JDS) == min(abs(ya-JDS))); JDS=J0(1);
fprintf ('%s %4.0f \n','JDS = ',JDS);
JDE = yep + km2deg(1.20*L/1000);
J0=find(abs(ya-JDE) == min(abs(ya-JDE))); JDE=J0(1);
fprintf ('%s %4.0f \n','JDE = ',JDE);
fprintf (fid2,'%4.0f %4.0f %4.0f %4.0f \n',IDS,IDE,JDS,JDE);
fclose all;

save xyo.mat IDS IDE JDS JDE -mat

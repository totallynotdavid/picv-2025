% Calculo de la posicion de los mareografos
% Copyleft: Cesar Jimenez 31 Ene 2011
% Updated: 09 Jun 2015
clc
close all
disp ('Posicion de los Mareografos Virtuales')
disp ('Elegir una opcion: ')
s = input ('Click en Mapa (1) o Por Teclado (2): ','s');
disp (' ');
A = load ('./bathy/grid_a.grd'); 
[m n] = size(A);
if s == '1'
    contour (A',[0,0],'k'), axis equal, grid, zoom
    xlim([1 m]); ylim([1 n])
    xlabel ('Hacer 3 clicks');
    [a, b] = ginput(3);
    fprintf ('%6.0f  %10.0f\n',a(1), b(1));
    fprintf ('%6.0f  %10.0f\n',a(2), b(2));
    fprintf ('%6.0f  %10.0f\n',a(3), b(3));
end

if s == '2'
    load ./bathy/xya.mat
    contour (xa,ya,A',[0,0],'k'), axis equal, grid, zoom
    lat = input ('Latitud  = ');
    lon = input ('Longitud = ');
    if lon < 0
        lon = lon + 360;
    end
    B = find (ya > lat);
    n = B(1);
    A = find (xa > lon);
    m = A(1);
    fprintf ('%6.0f  %10.0f\n',m, n);
    hold on
    text (lon, lat, '*')
end
disp ('Editar la linea 116 de tsunami1.for')

function varargout = tsunami(varargin)
% TSUNAMI M-file for tsunami.fig
%      TSUNAMI, by itself, creates a new TSUNAMI or raises the existing
%      singleton*.
%
%      H = TSUNAMI returns the handle to a new TSUNAMI or the handle to
%      the existing singleton*.
%
%      TSUNAMI('CALLBACK',hObject,eventData,handles,...) calls the local
%      function named CALLBACK in TSUNAMI.M with the given input arguments.
%
%      TSUNAMI('Property','Value',...) creates a new TSUNAMI or raises the
%      existing singleton*.  Starting from the left, property value pairs are
%      applied to the GUI before tsunami_OpeningFunction gets called.  An
%      unrecognized property name or invalid value makes property application
%      stop.  All inputs are passed to tsunami_OpeningFcn via varargin.
%
%      *See GUI Options on GUIDE's Tools menu.  Choose "GUI allows only one
%      instance to run (singleton)".
%
% See also: GUIDE, GUIDATA, GUIHANDLES

% Copyright 2002-2003 The MathWorks, Inc.t

% Edit the above text to modify the response to help tsunami

% Last Modified by GUIDE v2.5 12-Mar-2015 10:03:28
% Last update: Cesar Jimenez 23 Nov 2022
% Begin initialization code - DO NOT EDIT

gui_Singleton = 1;
gui_State = struct('gui_Name',       mfilename, ...
                   'gui_Singleton',  gui_Singleton, ...
                   'gui_OpeningFcn', @tsunami_OpeningFcn, ...
                   'gui_OutputFcn',  @tsunami_OutputFcn, ...
                   'gui_LayoutFcn',  [] , ...
                   'gui_Callback',   []);
if nargin && ischar(varargin{1})
    gui_State.gui_Callback = str2func(varargin{1});
end

if nargout
    [varargout{1:nargout}] = gui_mainfcn(gui_State, varargin{:});
else
    gui_mainfcn(gui_State, varargin{:});
end

% End initialization code - DO NOT EDIT

% --- Executes just before tsunami is made visible.
function tsunami_OpeningFcn(hObject, eventdata, handles, varargin)
% This function has no output args, see OutputFcn.
% hObject    handle to figure
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    structure with handles and user data (see GUIDATA)
% varargin   command line arguments to tsunami (see VARARGIN)

% Choose default command line output for tsunami
handles.output = hObject;
% Update handles structure
guidata(hObject, handles);
% UIWAIT makes tsunami wait for user response (see UIRESUME)
% uiwait(handles.figure1);

% --- Outputs from this function are returned to the command line.
function varargout = tsunami_OutputFcn(hObject, eventdata, handles) 
% varargout  cell array for returning output args (see VARARGOUT);
% hObject    handle to figure
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    structure with handles and user data (see GUIDATA)
clc
bandera = 0;
Mw  = get(handles.edit1,'string');
Mw  = str2num(Mw);
h   = get(handles.edit2,'string');
h   = str2num(h);
lat0 = get(handles.edit3,'string');
lat0 = str2num(lat0);
lon0 = get(handles.edit4,'string');
lon0 = str2num(lon0);
if lon0 > 0 lon0 = lon0-360; end
hhmm = get(handles.hora,'string');
load maper1.mat; 
lat = A(:,2);
lon = A(:,1);
load maper2.mat;
lat2 = B(:,2);
lon2 = B(:,1);
load maper3.mat;
lat3 = C(:,2);
lon3 = C(:,1);
load pacifico.mat
hold off
pcolor(xa-360,ya,A), shading flat, hold on
plot (lon,lat,'b',lon2,lat2,lon3,lat3,'b')

grid, zoom on, axis equal
xlim ([-86 -66]), ylim ([-19.5 1])
xlabel ('Longitud')
ylabel ('Latitud')

text (-80.5876,-03.6337,'La Cruz')
text (-81.3000,-05.082,'Paita')
text (-79.9423,-06.8396,'Pimentel')
text (-78.6100,-09.0733,'Chimbote')
text (-77.6150 ,-11.123,'Huacho')
text (-77.031,-12.046,'Lima')
text (-76.22,-13.71,'Pisco')
text (-75.1567,-15.3433,'San Juan')
text (-72.1067,-16.9983,'Matarani')
text (-70.3232,-18.4758,'Arica')  

% Get default command line output from handles structure
varargout{1} = handles.output;
handles.bandera = bandera;
handles.Mw = Mw;
handles.h = h; % Comparte informacion con otro callback
handles.lat0 = lat0;
handles.lon0 = lon0;
handles.hhmm = hhmm;
set (handles.tsdhn, 'visible','off')
set (handles.limpiar,   'visible','off')
set (handles.ttt,       'visible','off')
set (handles.catalogo,  'visible','off')
guidata(hObject, handles)

function edit1_Callback(hObject, eventdata, handles)
% hObject    handle to edit1 (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    structure with handles and user data (see GUIDATA)

% Hints: get(hObject,'String') returns contents of edit1 as text
%        str2double(get(hObject,'String')) returns contents of edit1 as a double

% --- Executes during object creation, after setting all properties.
function edit1_CreateFcn(hObject, eventdata, handles)
% hObject    handle to edit1 (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    empty - handles not created until after all CreateFcns called

% Hint: edit controls usually have a white background on Windows.
%       See ISPC and COMPUTER.
if ispc
    set(hObject,'BackgroundColor','white');
else
    set(hObject,'BackgroundColor',get(0,'defaultUicontrolBackgroundColor'));
end

function edit2_Callback(hObject, eventdata, handles)
% hObject    handle to edit2 (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    structure with handles and user data (see GUIDATA)

% Hints: get(hObject,'String') returns contents of edit2 as text
%        str2double(get(hObject,'String')) returns contents of edit2 as a double

% --- Executes during object creation, after setting all properties.
function edit2_CreateFcn(hObject, eventdata, handles)
% hObject    handle to edit2 (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    empty - handles not created until after all CreateFcns called

% Hint: edit controls usually have a white background on Windows.
%       See ISPC and COMPUTER.
if ispc
    set(hObject,'BackgroundColor','white');
else
    set(hObject,'BackgroundColor',get(0,'defaultUicontrolBackgroundColor'));
end

function edit3_Callback(hObject, eventdata, handles)
% hObject    handle to edit3 (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    structure with handles and user data (see GUIDATA)

% Hints: get(hObject,'String') returns contents of edit3 as text
%        str2double(get(hObject,'String')) returns contents of edit3 as a double


% --- Executes during object creation, after setting all properties.
function edit3_CreateFcn(hObject, eventdata, handles)
% hObject    handle to edit3 (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    empty - handles not created until after all CreateFcns called

% Hint: edit controls usually have a white background on Windows.
%       See ISPC and COMPUTER.
if ispc
    set(hObject,'BackgroundColor','white');
else
    set(hObject,'BackgroundColor',get(0,'defaultUicontrolBackgroundColor'));
end

function edit4_Callback(hObject, eventdata, handles)
% hObject    handle to edit4 (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    structure with handles and user data (see GUIDATA)

% Hints: get(hObject,'String') returns contents of edit4 as text
%        str2double(get(hObject,'String')) returns contents of edit4 as a double

% --- Executes during object creation, after setting all properties.
function edit4_CreateFcn(hObject, eventdata, handles)
% hObject    handle to edit4 (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    empty - handles not created until after all CreateFcns called

% Hint: edit controls usually have a white background on Windows.
%       See ISPC and COMPUTER.
if ispc
    set(hObject,'BackgroundColor','white');
else
    set(hObject,'BackgroundColor',get(0,'defaultUicontrolBackgroundColor'));
end


function edit5_Callback(hObject, eventdata, handles)
% hObject    handle to edit5 (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    structure with handles and user data (see GUIDATA)

% Hints: get(hObject,'String') returns contents of edit5 as text
%        str2double(get(hObject,'String')) returns contents of edit5 as a double

% --- Executes during object creation, after setting all properties.
function edit5_CreateFcn(hObject, eventdata, handles)
% hObject    handle to edit5 (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    empty - handles not created until after all CreateFcns called

% Hint: edit controls usually have a white background on Windows.
%       See ISPC and COMPUTER.
if ispc
    set(hObject,'BackgroundColor','white');
else
    set(hObject,'BackgroundColor',get(0,'defaultUicontrolBackgroundColor'));
end

function edit6_Callback(hObject, eventdata, handles)
% hObject    handle to edit6 (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    structure with handles and user data (see GUIDATA)

% Hints: get(hObject,'String') returns contents of edit6 as text
%        str2double(get(hObject,'String')) returns contents of edit6 as a double

% --- Executes during object creation, after setting all properties.
function edit6_CreateFcn(hObject, eventdata, handles)
% hObject    handle to edit6 (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    empty - handles not created until after all CreateFcns called

% Hint: edit controls usually have a white background on Windows.
%       See ISPC and COMPUTER.
if ispc
    set(hObject,'BackgroundColor','white');
else
    set(hObject,'BackgroundColor',get(0,'defaultUicontrolBackgroundColor'));
end

% --- Executes on button press in Calcular.
function Calcular_Callback(hObject, eventdata, handles, varargin)
% hObject    handle to Calcular (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    structure with handles and user data (see GUIDATA)
clc;
tiempo = clock;
if (tiempo(1)>2025) % | tiempo(2)>2)
    disp('Ha ocurrido un error de sintaxis');
    title('Ha ocurrido un error de sintaxis');
    return
end
bandera = handles.bandera;
if bandera == 0
    Mw  = get(handles.edit1,'string');
    Mw  = str2num(Mw);
    h   = get(handles.edit2,'string');
    h   = str2num(h);
    lat0 = get(handles.edit3,'string');
    lat0 = str2num(lat0);
    lon0 = get(handles.edit4,'string');
    lon0 = str2num(lon0);
    if lon0 > 0 lon0 = lon0-360; end
    dia   = get(handles.edit9,'string');
    dia   = str2num(dia); 
    hhmm = get(handles.hora,'string');
end
if bandera == 1
   dia = handles.dia; 
   hhmm = handles.hhmm;
   lat0 = handles.lat0;
   lon0 = handles.lon0;
   h = handles.h;
   Mw = handles.Mw;
end

if length(Mw) == 0 | length(h) == 0 | length(lat0) == 0 | length(lon0) == 0 
    disp ('Introducir Datos ...')
    title ('Introducir Datos ...')
    return;
end

%if Mw >= 6.5
  L = 10^(0.55*Mw-2.19);  % (km) Papazachos 2004
  W = 10^(0.31*Mw-0.63);  % (km)
  M0 = 10^(1.5*Mw+9.1);  %Momento sismico (N*m) 
  u = 4.5e10; % (N/m2) coeficiente de rigidez
  D = M0/(u*(L*1000)*(W*1000));
  %%% M0 = u*L*W*D   %%%
  S = 10^(0.86*Mw-2.82);   % (km2)
  a = 1.11*0.5642*W;  
  b = 0.90*0.5642*L;  
%elseif Mw <= 6.5
%    disp ('La magnitud debe ser > 6.5')
%end
load maper1.mat; 
lat = A(:,2);
lon = A(:,1);
load maper2.mat;
lat2 = B(:,2);
lon2 = B(:,1);
load maper3.mat;
lat3 = C(:,2);
lon3 = C(:,1);
load pacifico.mat
M = Mw;

% Calcular el mecanismo focal 
A1 = load('mecfoc.dat');
[m n] = size(A1);
for k =1:m
  lonm(k) = A1(k,1);
  latm(k) = A1(k,2);
  if (lonm(k) > 0) 
    lonm(k) = lonm(k)-360;
  end 
  dist(k) = sqrt((lonm(k)-lon0)^2+(latm(k)-lat0)^2);
end 
[minimo pos] = min(dist)
azimut = A1(pos,3) % strike
echado = A1(pos,4) %dip
%rake = 90 % A1(pos,5);

%%%%% Dibujar Rectangulo
echado = 18; % aprox
L1 = L*1000;
W1 = 1000*W*cos(echado*pi/180); % **********************************
beta = atan(W1/L1)*180/pi; % ***************************************
alfa = azimut - 270;% **********************************************
h1 = sqrt(L1*L1+W1*W1);% *******************************************
a1 = 0.5*h1*sin((alfa+beta)*pi/180)/1000;% *************************
b1 = 0.5*h1*cos((alfa+beta)*pi/180)/1000;% *************************
   xo = lon0+b1/110; %km2deg(b1); %xe = xo - km2deg(b)% *********************
   yo = lat0-a1/110; %km2deg(a1); %ye = yo + km2deg(a)% *

dip=echado*pi/180; 
a1=-(azimut-90)*pi/180; a2=-(azimut)*pi/180;
r1=L1; r2=W1; %*cos(dip);
r1=r1/(60*1853); r2=r2/(60*1853);
sx(1)=0;          sy(1)=0;
sx(2)=r1*cos(a1); sy(2)=r1*sin(a1);
sx(4)=r2*cos(a2); sy(4)=r2*sin(a2);
sx(3)=sx(4)+sx(2);sy(3)=sy(4)+sy(2);
sx(5)=sx(1)      ;sy(5)=sy(1);
sx=sx + xo; sy=sy + yo;
%%% Fin rectangulo

%%%%
cla, hold on
pcolor(xa-360,ya,A), shading flat
contour(xa-360,ya,A,[0 0],'black'), axis equal
%%%%

if M < 7.0
    plot (lon0,lat0,'o'), zoom on
end
if M >= 7.0
    plot (lon0,lat0,'o',sx,sy,'k','linewidth',1)
end

if lat0 > 0.0 
    text (-79.48, 8.99,'Panama'); 
end
text (-80.5876,-03.6337,'La Cruz')
text (-81.30,-05.082,'Paita')
text (-79.9423,-06.8396,'Pimentel')
text (-78.6100,-09.0733,'Chimbote')
text (-77.615 ,-11.123,'Huacho')
text (-77.031,-12.046,'Lima')
text (-76.22,-13.71,'Pisco')
text (-75.1567,-15.3433,'San Juan')
text (-73.61  ,-16.23  ,'Atico')
text (-72.6838,-16.6604,'Camana')
text (-72.1067,-16.9983,'Matarani')
text (-70.3232,-18.4758,'Arica')  
if lat0 < -20 text (-70.4044,-23.6531,'Antofagasta'); end

%text (lon0+15, lat0-0.5, 'Parametros de la fuente sismica')
L = num2str(floor(L)); W = num2str(floor(W));
D = num2str(D); M0 = num2str(M0/1e21);
if length(M0)<3
    M0 = [M0,'.0'];
end
text (lon0+15, lat0-2.0, ['Largo    L  = ',L,' km']);
text (lon0+15, lat0-2.9, ['Ancho    W  = ',W,' km']);
text (lon0+15, lat0-3.8, ['Dislocacion = ',D(1:4),' m']);
text (lon0+15, lat0-4.7, ['Mom. sismico= ',M0(1:4),'e21 N.m']);
grid on, zoom on, axis equal
xlabel ('Longitud')
ylabel ('Latitud')
xlim ([lon0-10 lon0+10]), ylim ([lat0-10 lat0+10])

%%%% Tierra o mar?
m = length(lon);
for k =1:m
  dist(k) = sqrt((lon(k)-lon0)^2+(lat(k)-lat0)^2); %distancia epi-costa
end 
[minimo pos] = min(dist);
dist_min = deg2km(minimo)

[long, lati] = meshgrid(xa-360,ya);
h0 = interp2(long,lati,A,lon0,lat0);
%%%%%
if h0 > 0 & dist_min < 50
    title('El epicentro esta en Tierra, pero podría generar Tsunami');
end
if h0 > 0 & dist_min > 50
    title('El epicentro esta en Tierra. NO genera Tsunami');
    return;    
end
if h0 <= 0 
   if M >= 7.0 & M<7.9 & h <= 60
       title ('Epicentro en el Mar. Probable Tsunami pequeno y local');
   end
   if M >= 7.9 & M<8.3995 & h <= 60
       title ('Epicentro en el Mar. Genera un Tsunami pequeno');
   end
   if M >= 8.3995 & M<8.8 & h <= 60
       title ('Epicentro en el Mar. Genera un Tsunami potencialmente destructivo');
   end
   if M >= 8.8 & h <= 60
       title ('Epicentro en el Mar. Genera un Tsunami grande y destructivo');
   end
   if h > 60 | M < 7.0%else    
       title ('El epicentro esta en el Mar y NO genera Tsunami');
   end
end

fid2 = fopen('hypo.dat', 'w');
fprintf (fid2, '%s', hhmm);  fprintf (fid2,'\r\n');
fprintf (fid2, '%4.2f' ,lon0); fprintf (fid2,'\r\n');
fprintf (fid2, '%4.2f' ,lat0); fprintf (fid2,'\r\n');
fprintf (fid2, '%3.0f', h); fprintf (fid2,'\r\n');
fprintf (fid2, '%3.1f' ,Mw);fprintf (fid2,'\r\n');
fclose (fid2);

bandera = 0;
handles.bandera = bandera;
handles.lat0 = lat0;
handles.lon0 = lon0;
handles.h = h;
handles.Mw = Mw;
handles.hhmm = hhmm;
handles.dia = dia;
set (handles.tsdhn,     'visible','on')
set (handles.limpiar,   'visible','on')
set (handles.ttt,       'visible','on')
%set (handles.catalogo,  'visible','on')
guidata(hObject, handles);

% --- Executes on button press in ttt.
function ttt_Callback(hObject, eventdata, handles)
% hObject    handle to ttt (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    structure with handles and user data (see GUIDATA)
clc
lat0 = get(handles.edit3,'string');
lat_e = str2num(lat0);
lon0 = get(handles.edit4,'string');
lon_e = str2num(lon0);
Mw  = get(handles.edit1,'string');
Mw  = str2num(Mw);
h   = get(handles.edit2,'string');
h   = str2num(h);
dia   = get(handles.edit9,'string');
if length (dia) == 0
    dia = '00';
end
hhmm = get(handles.hora,'string');
if length (hhmm) == 0
    hhmm = '0000';
end
if length (hhmm) > 0 & length (hhmm) < 4
    hhmm = '0000';
end
if hhmm(3) == ':'
    hhmm = [hhmm(1:2),hhmm(4:5)];
    %disp ('Formato de hora incorrecto');
end

tiempo0 = str2num(hhmm(1:2))+ str2num(hhmm(3:4))/60;
disp ('CALCULO POR MODELADO NUMERICO DE TSUNAMIS')
disp ('  Copyright: Cesar Jimenez, DHN-Geofisica ')
g = 9.81;   % aceleracion de la gravedad (m/s2)
R = 6370.8;   % Radio de la Tierra (km)
load batiperu;    % almacena matriz batimetria "A"
[p q] = size(A);
xllcenter = maplegend(3); 
yllcenter = maplegend(2); 
cellsize = 0.03333333;    %1/maplegend(1);
i = 1:p; 
vlat(i) = yllcenter-(i-1)*cellsize;
vlat(1), vlat(end)
j = 1:q; 
vlon(j) = xllcenter+(j-1)*cellsize;
[lon, lat] = meshgrid(vlon,vlat);
disp ('Coordenadas del epicentro: ')
h0 = interp2(lon,lat,A,lon_e,lat_e);
disp (' Puertos   Zona     Hora_llegada          dist(km)')

fname ='puertos.txt'; %Coordenadas del puerto
fid = fopen(fname, 'r');
fsalida = 'salida.txt';

fecha = date;
mes = [fecha(3:end)];
fid2 = fopen(fsalida, 'w');
fprintf (fid2,'ESTIMACION DEL TIEMPO DE ARRIBO DE TSUNAMIS');
fprintf (fid2, '\r\n');
fprintf (fid2, 'Coordenadas del epicentro: ');  fprintf (fid2,'\r\n');
fprintf (fid2, '%s %s'    ,'Fecha    =',dia,mes);  fprintf (fid2,'\r\n');
fprintf (fid2, '%s %s'    ,'Hora     =',hhmm);  fprintf (fid2,'\r\n');
fprintf (fid2, '%s %4.2f' ,'Latitud  =',lat_e); fprintf (fid2,'\r\n');
fprintf (fid2, '%s %4.2f' ,'Longitud =',lon_e); fprintf (fid2,'\r\n');
fprintf (fid2, '%s %3.0f %s','Profund  =',h,'km'); fprintf (fid2,'\r\n');
fprintf (fid2, '%s %3.1f %s' ,'Magnitud =',Mw);fprintf (fid2,'\r\n');
fprintf (fid2, '%s %s'    ,'Tiempo actual:',datestr(now));fprintf (fid2,'\r\n');
fprintf (fid2,' Puertos   Zona     Hora_llegada          dist(km)'); fprintf (fid2,'\r\n');

j = 1;
feof(fid) = 0;
while feof(fid) == 0
   linea  = fgetl(fid);
   if length(linea)<15
       break
   else
       puerto = linea(1:15);
   end
   latp = str2num(linea(17:24));
   lonp = str2num(linea(28:35));
   % Calculo de la distancia y de la recta
   t1 = pi/2 - lat_e*pi/180;
   f1 = lon_e*pi/180;
   t2 = pi/2 - latp*pi/180;
   f2 = lonp*pi/180;
   cosen = sin(t1)*sin(t2)*cos(f1-f2)+cos(t1)*cos(t2);
   alfa = acos(cosen);
   d = R*alfa;
   if d >= 750 %1000
     tiempo = d/790 + 0.2;
   end
   if d < 750 & (lat_e > 0 | lat_e < -19)
      tiempo = d/700; % + 0.2;
   end   
   if d < 750 & lat_e < 0 & lat_e > -19
   clear h;
   vu = ([lonp-lon_e, latp-lat_e])/d*110; %deg2km([lonp-lon_e, latp-lat_e])/d; %vector unitario
   n = 100;   %numero de particiones
   delta = alfa*180/pi/n;
   P0 = [lon_e, lat_e];
   for i = 1:n;
      P(i,:) = P0 + i*delta*vu;
      h(i) = interp2(lon,lat,A,P(i,1),P(i,2));
   end;
   h = [h0, h];
   h = abs(h);  %correccion por topografia
   v = sqrt(g*h)*3.6;     % v en km/h
%%% Calculo de la integral por Simpson 1/3   
   delta = alfa/n*R;  %deg2km(delta);
   y = 1./v;
   suma1 = y(1)+y(n+1);
   suma2 = 4*sum(y(2:2:n));
   suma3 = 2*sum(y(3:2:n-1));
   suma = suma1+suma2+suma3;
   integral = (delta/3)*suma;
   tiempo = 0.50*integral; % factor de calibracion
   if j == 13
       tiempo = tiempo + 0.1;
   end
   if tiempo > 3.0
       tiempo = d/733 + 0.25;
   end
   if (tiempo > 1.4 & tiempo < 3) % & d < 999)
       tiempo = d/690 + 0.2;
   end
end        %%% fin de if < 100
   tiempo = tiempo + tiempo0; % Se suma el tiempo de arribo a la hora origen
   hora = floor(tiempo);
   min  = floor((tiempo-hora)*60);

   dia = str2num(dia);
   contador = 0;
   if hora >= 24 
       hora = hora - 24; 
       dia = dia + 1;
       contador = 1;
   end %Hora del dia siguiente
   
   dia = num2str(dia);
   if length(dia) == 1
       dia = ['0',dia];
   end
   mes = [fecha(3:end)];
   
   hora = num2str(hora);
   if length(hora) == 1
       hora = ['0',hora];
   end
   min = num2str(min);
   if length(min) == 1
       min = ['0',min];
   end
   hora_llegada = ['    ',hora,':',min,' ',dia,mes];
   %%%%
   fprintf ('%s %s %10.0f\n' ,puerto,hora_llegada,d);
   fprintf (fid2, '%s %s %10.0f' ,puerto,hora_llegada,d);
   fprintf (fid2, '\r\n');
   
   if contador == 1 
       dia = str2num(dia)-1;
       dia = num2str(dia);
   end
   j = j+1;  
   
   if j > 18 % 17 para Arica
       break
   end;
end
fclose(fid2);
directorio = pwd;
if directorio(2) == ':'
%    ! notepad salida.txt &
    system('notepad salida.txt & ')
else
%    ! gedit salida.txt &    
    system('gedit salida.txt & ')
end
% ! c:\Archiv~1\DHN\TsunamiSetup\TsunamiAlerta.exe

% --- Executes on button press in distancia.
function tsdhn_Callback(hObject, eventdata, handles)
% hObject    handle to distancia (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    structure with handles and user data (see GUIDATA)
title('Ejecutando el TSDHN ... Espere! ...')
! chmod 775 job.run
! ./job.run
%system('./job.run')

function hora_Callback(hObject, eventdata, handles)
% hObject    handle to hora (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    structure with handles and user data (see GUIDATA)

% Hints: get(hObject,'String') returns contents of hora as text
%        str2double(get(hObject,'String')) returns contents of hora as a double


% --- Executes during object creation, after setting all properties.
function hora_CreateFcn(hObject, eventdata, handles)
% hObject    handle to hora (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    empty - handles not created until after all CreateFcns called

% Hint: edit controls usually have a white background on Windows.
%       See ISPC and COMPUTER.
if ispc
    set(hObject,'BackgroundColor','white');
else
    set(hObject,'BackgroundColor',get(0,'defaultUicontrolBackgroundColor'));
end


% --- Executes on button press in catalogo.
function catalogo_Callback(hObject, eventdata, handles)
% hObject    handle to catalogo (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    structure with handles and user data (see GUIDATA)
clc
bandera = handles.bandera;
if bandera == 0
    Mw  = get(handles.edit1,'string');
    Mw  = str2num(Mw);
    h   = get(handles.edit2,'string');
    h   = str2num(h);
    lat0 = get(handles.edit3,'string');
    lat0 = str2num(lat0);
    lon0 = get(handles.edit4,'string');
    lon0 = str2num(lon0);
    if lon0 > 0 lon0 = lon0-360; end
    dia   = get(handles.edit9,'string');
    hhmm = get(handles.hora,'string');
end
if bandera == 1
   dia = handles.dia;
   hhmm = handles.hhmm;
   lat0 = handles.lat0;
   lon0 = handles.lon0;
   h = handles.h;
   Mw = handles.Mw;
end

disp ('  CALCULO POR MODELADO NUMERICO DE TSUNAMIS')
disp ('    Copyright: Cesar Jimenez, DHN-Geofisica')
%Mw  = str2num(get(handles.edit1,'string'));
%h   = str2num(get(handles.edit2,'string'));
%lat0 = get(handles.edit3,'string');
lat_e = lat0;
%lon0 = get(handles.edit4,'string');
lon_e = lon0;
%hhmm = get(handles.hora,'string');
if lon_e < 0
    lon_e = lon_e + 360;
end

if length (hhmm) >= 0 & length (hhmm) < 4
    hhmm = '0000';
end
if length (hhmm) >= 5
    hhmm = '0000';
end
tiempo0 = str2num(hhmm(1:2))+ str2num(hhmm(3:4))/60; %en horas
hh_gmt = str2num(hhmm(1:2))+5;
if hh_gmt >= 24
    hh_gmt = hh_gmt - 24;
end
hh_gmt = num2str(hh_gmt);
if length(hh_gmt) == 1
    hh_gmt = ['0',hh_gmt];
end

if Mw < 6.9
fecha = date;
mes = [fecha(4:end)];
fsalida = 'salida.txt';
fid2 = fopen(fsalida, 'w');
fprintf (fid2,'ESTIMACION DEL TIEMPO DE ARRIBO DE TSUNAMIS');
fprintf (fid2, '\r\n');
fprintf (fid2, 'Coordenadas del epicentro: ');  fprintf (fid2,'\r\n');
fprintf (fid2, '%s %s '   ,'Fecha    =',dia,mes);  fprintf (fid2,'\r\n');
fprintf (fid2, '%s %s'    ,'Hora     =',hhmm);  fprintf (fid2,'\r\n');
%fprintf (fid2, '%s %s' ,'Hora GMT =',[hh_gmt,hhmm(3:4)]); fprintf (fid2,'\r\n');
fprintf (fid2, '%s %4.2f' ,'Latitud  =',lat_e); fprintf (fid2,'\r\n');
fprintf (fid2, '%s %4.2f' ,'Longitud =',lon_e-360); fprintf (fid2,'\r\n');
fprintf (fid2, '%s %3.0f %s','Profund  =',h,'km'); fprintf (fid2,'\r\n');
fprintf (fid2, '%s %3.1f %s' ,'Magnitud =',Mw);fprintf (fid2,'\r\n');
fprintf (fid2, '%s %s'    ,'Tiempo actual:',datestr(now));fprintf (fid2,'\r\n');
fclose(fid2);
end

if Mw >= 6.9 
B = load ('corden.txt');
long = B(:,1);
lati = B(:,2);
Nf = length(long); % Nf = 216; % numero total de fuentes
for k = 1:Nf  %corrige el archivo corden.txt, que esta al reves
    lon(k) = long(Nf-k+1);
    lat(k) = lati(Nf-k+1);
end
disp ('Coordenadas del epicentroide (centro de gravedad): ')
if lon < 0
    lon = lon + 360;
end

d = sqrt((lon-lon_e).*(lon-lon_e)+(lat-lat_e).*(lat-lat_e));
d = d*111; %deg2km(d); % min(d)
if min(d) > 90
    disp ('El epicentro esta fuera del area de sismicidad')
    title('El epicentro esta fuera del area de sismicidad')
    return
end
fid = fopen('aaa.txt','w');
for k = 1:length(d); 
    fprintf(fid,'%8.2f  %12.2f\n',d(k), k);
end
fclose(fid); 
A = load('aaa.txt'); delete aaa.txt
[Y,I] = sort(A,1);
B = [Y(:,1), I(:,1)];
  
[dmin pos] = min(d);
L = 10^(0.55*Mw-2.19); % km
W = 10^(0.31*Mw-0.63); % km
M0 = 10^(1.5*Mw+9.1);
u = 4.5e10; % (N/m2) coeficiente de rigidez
slip = M0/(u*(L*1000)*(W*1000));
nl = round (L/50);
nw = round (W/50);
N = round(L*W/(50*50)); % N = nl * nw;
% if Mw == 8.0   N = 4;   end
fprintf('%s  %3.0f\n','Numero de sub-fuentes: ',N);
%conjunto = [pos,pos+1,pos+3,pos+4,pos+6,pos+7,pos-3,pos-2,pos-6,pos-5]
conjunto = [B(1:N,2)];
cd zfolder

green = zeros(1441,23); % y = [];
for k = 1:N
    char_k = num2str(conjunto(k));
    if length(char_k) == 1
        filename = ['green00',char_k,'.dat'];
    end
    if length(char_k) == 2
        filename = ['green0',char_k,'.dat'];
    end
    if length(char_k) == 3
        filename = ['green',char_k,'.dat'];
    end
    eval (['load ',filename]);
    green = green + eval (filename(1:end-4));
end
cd ..

green = slip*green;
green(:,1) = green(:,1)/(N*slip); % tiempo
t = green(:,1); % tiempo en minutos
save green.txt green -ascii

%A=['La Cruz     Tumbes     '
%   'Talara      Piura      '
%   'Paita       Piura      '
%   'Pimentel    Lambayeque '
%   'Dart32413              '
%   'Salaverry   La_Libertad' 
%   'Chimbote    Ancash     '
%   'Huarmey     Ancash     '
%   'Huacho      Lima       '
%   'Callao      Lima       '
%   'Cerro Azul  Lima       '
%   'Pisco       Ica        '
%   'San Juan    Ica        '
%   'Atico       Arequipa   '
%   'Camana      Arequipa   '
%   'Matarani    Arequipa   '
%   'Ilo         Moquegua   '
%   'Dart32412              '
%   'Arica       Chile      '
%   'Dart32401              '
%   'Iquique                '
%   'Antofagasta            '
%   'Lobos       Lambayeque '];

A=['Tumbes      La Cruz    '
   'Piura       Talara     '
   'Piura       Paita      '
   'Lambayeque  Pimentel   '
   '            Dart32413  '
   'La_Libertad Salaverry  ' 
   'Ancash      Chimbote   '
   'Ancash      Huarmey    '
   'Lima        Huacho     '
   'Lima        Callao     '
   'Lima        Cerro Azul '
   'Ica         Pisco      '
   'Ica         San Juan   '
   'Arequipa    Atico      '
   'Arequipa    Camana     '
   'Arequipa    Matarani   '
   'Moquegua    Ilo        '
   '            Dart32412  '
   'Tacna       Sta_Rosa   '
   '            Dart32401  '
   'Chile       Iquique    '
   'Chile       Antofagasta'
   'Lambayeque  Lobos      '];

% Escribir a un archivo
fecha = date;
mes = [fecha(4:end)];

fsalida = 'salida.txt';
fid2 = fopen(fsalida, 'w');
fprintf (fid2,'ESTIMACION DEL TIEMPO DE ARRIBO DE TSUNAMIS');
fprintf (fid2, '\r\n');
fprintf (fid2, 'Coordenadas del epicentro: ');  fprintf (fid2,'\r\n');
fprintf (fid2, '%s %s '   ,'Fecha    =',dia,mes);  fprintf (fid2,'\r\n');
fprintf (fid2, '%s %s'    ,'Hora     =',hhmm);  fprintf (fid2,'\r\n');
%fprintf (fid2, '%s %s' ,'Hora GMT =',[hh_gmt,hhmm(3:4)]); fprintf (fid2,'\r\n');
fprintf (fid2, '%s %4.2f' ,'Latitud  =',lat_e); fprintf (fid2,'\r\n');
fprintf (fid2, '%s %4.2f' ,'Longitud =',lon_e-360); fprintf (fid2,'\r\n');
fprintf (fid2, '%s %3.0f %s','Profund  =',h,'km'); fprintf (fid2,'\r\n');
fprintf (fid2, '%s %3.1f %s' ,'Magnitud =',Mw);fprintf (fid2,'\r\n');
fprintf (fid2, '%s %s'    ,'Tiempo actual:',datestr(now));fprintf (fid2,'\r\n');
fprintf (fid2, 'Departamento Puertos    Hora_llegada  Hmax(m)  T_arribo '); 
fprintf (fid2,'\r\n');

disp (' ')
disp ('Departamento Puerto    Hora_llegada  Hmax(m)  T_arribo ');
figure;
B = [];
for k = [1,2,3,4,6,7,8,9,10,11,12,13,14,15,16,17,19] % solo hasta Ilo %22 numero de estaciones
    if k < 23
      maximo(k) = max(green(1:1200,k+1));
    else
      maximo(23) = max(green(1:1200,4+1));
    end
    if k == 1
        c(k) = 0.74;
        maximo(k) = c(k)*maximo(k); 
        %correccion La Cruz
    end
    if k == 2
        c(k) = 0.88;
        maximo(k) = c(k)*maximo(k); 
        %correccion Talara
    end
    if k == 3
        c(k) = 0.94;
        maximo(k) = c(k)*maximo(k); 
        %correccion Paita
    end
    if k == 4
        c(k) = 0.75;
        maximo(k) = c(k)*maximo(k); 
        %correccion Pimentel
    end
    if k == 6
        c(k) = 0.35;
        maximo(k) = c(k)*maximo(k); 
        %correccion Salaverry
    end
    if k == 7
        c(k) = 0.45;
        maximo(k) = c(k)*maximo(k); 
        %correccion Chimbote
    end
    if k == 8
        c(k) = 1.05;
        maximo(k) = c(k)*maximo(k); 
        %correccion Huarmey
    end
    if k == 9
        c(k) = 0.95;
        maximo(k) = c(k)*maximo(k); % corregir
        %correccion Huacho
    end
    if k == 10
        c(k) = 0.79;
        maximo(k) = c(k)*maximo(k); 
        %correccion Callao
    end
    if k == 11
        c(k) = 0.82;
        maximo(k) = c(k)*maximo(k); % corregir
        %correccion Cerro Azul
    end
    if k == 12
        c(k) = 0.65;
        maximo(k) = c(k)*maximo(k); 
        %correccion Pisco
    end
    if k == 13
        c(k) = 0.51;
        maximo(k) = c(k)*maximo(k); 
        %correccion San Juan
    end
    if k == 14
        c(k) = 1.00;
        maximo(k) = c(k)*maximo(k); 
        %correccion Atico
    end
    if k == 15
        c(k) = 0.40;
        maximo(k) = c(k)*maximo(k); 
        %correccion Camana
    end
    if k == 16
        c(k) = 0.79;
        maximo(k) = c(k)*maximo(k); 
        %correccion Matarani
    end
    if k == 17
        c(k) = 0.78;
        maximo(k) = c(k)*maximo(k); %antes 0.80
        %correccion Ilo
    end
    if k == 19
        c(k) = 0.70;
        maximo(k) = c(k)*maximo(k);
        %correccion Arica
    end
    
    % Filtro 3 muestras
    if k < 23
    y = green(:,k+1);
    N = length(y);
    for j = 2:N-1
        yf(j) = (y(j-1)+y(j)+y(j+1))/3;
    end
    yf(1)=y(1); yf(N)=y(N);
    y = yf;
    end
    % Fin de filtro

    if k == 23
        c(k) = 0.60;
        maximo(k) = c(k)*maximo(4); 
        y = green(:,4+1);
        %aproximacion Lobos
    end
        
    %plot (t, c(k)*green(:,b+1)), grid on, zoom xon
    plot (t, c(k)*y), grid on, zoom xon
    xlim ([t(1) t(end-40)]) %solo hasta el min 700
    title (num2str(k))
   
    if k < 23 % Calcula el tiempo de arribo
       I = find(green(:,k+1) > 0);
       ta(k) = t(I(1));
       if k == 5 ta(k) = 999; end
       if k ==18 ta(k) = 999; end
    else
       I = find(green(:,4+1) > 0); % solo Lobos
       ta(k) = t(I(1))-3;
    end
      
    if ta(k) == 0  ta(k) = 5.0;  end
    
    tiempo = ta(k)/60 + tiempo0; %Se suma el tiempo de arribo a la hora origen
    hora_a = floor(ta(k)/60);
    minu_a = floor((ta(k)/60-hora_a)*60);
    
    hora_a = num2str(hora_a);
    if length(hora_a) == 1
       hora_a = ['0',hora_a];
    end
    minu_a = num2str(minu_a);
    if length(minu_a) == 1
       minu_a = ['0',minu_a];
    end
    tiempo_arribo(k,:) = ['    ',hora_a,':',minu_a];
    
    hora = floor(tiempo);
    minu = floor((tiempo-hora)*60);
    if hora >= 24 hora = hora - 24; end %Hora del dia siguiente
    hora = num2str(hora);
    if length(hora) == 1
       hora = ['0',hora];
    end
    minu = num2str(minu);
    if length(minu) == 1
       minu = ['0',minu];
    end
    hora_llegada(k,:) = ['  ',hora,':',minu];
    
    if maximo(k)<=0.5
        categoria(k,:) = '   Precaucion';
    end
    if maximo(k)>0.5 & maximo(k)<3.0
        categoria(k,:) = '   Alerta    ';
    end
    if maximo(k)>=3.0
        categoria(k,:) = '   Alarma    ';
    end
   
%    fprintf('%s  %s %9.2f %s %s\n',A(k,:),hora_llegada(k,:),maximo(k),tiempo_arribo(k,:),categoria(k,:));
%    fprintf(fid2,'%s  %s %9.2f %s %s',A(k,:),hora_llegada(k,:),maximo(k),tiempo_arribo(k,:),categoria(k,:));
%    fprintf (fid2,'\r\n');
%    pause (0.1);
end

[B,j] = sort(ta');
k = j(3:end);
for i = 1:length(k)
    fprintf('%s  %s %9.2f %s\n',A(k(i),:),hora_llegada(k(i),:),maximo(k(i)),tiempo_arribo(k(i),:));%,categoria(k(i),:));
    fprintf(fid2,'%s  %s %9.2f %s',A(k(i),:),hora_llegada(k(i),:),maximo(k(i)),tiempo_arribo(k(i),:));%,categoria(k(i),:));
    fprintf (fid2,'\r\n');
end

fprintf (fid2,'%s', '* La altura estimada NO considera la fase lunar ni oleaje anomalo');

    [a b] = max(max(green(:,2:23)));
    if b>19 b=19; end
    plot (t, maximo(b)*green(:,b+1)/max(green(:,b+1))), grid on, zoom on
    xlim ([t(1) t(end-40)]) %solo hasta el min 700
    title(A(b,1:10))
    
    
fclose(fid2);
directorio = pwd;
if directorio(2) == ':'
%    ! notepad salida.txt &
    system('notepad salida.txt & ')
else
%    ! gedit salida.txt & 
    system('gedit salida.txt & ')
end
else
    disp ('No se genera Tsunami')
end

% --- Executes on button press in Prueba DEV
function Automatico_Callback(hObject, eventdata, handles)
% hObject    handle to Automatico (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    structure with handles and user data (see GUIDATA)
clc
bandera = 1;
url = 'https://dev.cnat.pe/api/adm/earthquake/pre-tsunami' %prueba
%url = 'https://cnat.pe/api/adm/earthquake/pre-tsunami' % firme
web(url, '-browser');
s = webread(url);
N = length(s);
disp ('Parametros hipocentrales del IGP')
disp (' ')
for k = 1:N-6
    if s(k:k+4) == 'Fecha'
        dia = [s(k+8:k+9)];
        fprintf('%s %s\n', 'Dia =',dia);
    end
    if s(k:k+3) == 'Hora'
        hhmm = [s(k+7:k+8),s(k+9:k+10)];
        fprintf('%s %s\n', 'Hora Origen =',hhmm);
    end
    if s(k:k+5) == 'Latitu'
        lat = s(k+10:k+15);
        lat0 = str2num(lat);
        fprintf('%s %7.2f\n', 'Latitud = ',lat0);        
    end
    if s(k:k+5) == 'Longit'
        lon = s(k+11:k+16);
        lon0 = str2num(lon);
        fprintf('%s %6.2f\n', 'Longitud = ',lon0);  
    end 
    if s(k:k+5) == 'Profun'
        hh = s(k+14:k+18); 
        if hh(3) == 'k'
            h = str2num(hh(1:2));
        else
            h = str2num(hh);
        end
        fprintf('%s %7.0f %s\n', 'Prof = ',h,'km'); 
    end    
    if s(k:k+5) == 'Magnit'
        Mag = s(k+11:k+13);
        Mw = str2num(Mag);
        fprintf('%s %3.1f %s\n', 'Magnitud = ',Mw,'Mw');        
        break
    end
end

set(handles.edit1, 'String', Mag);
set(handles.edit2, 'String', num2str(h));
set(handles.edit3, 'String', lat);
set(handles.edit4, 'String', lon);
set(handles.edit9, 'String', dia);
set(handles.hora,  'String', hhmm);
bandera = 0;

varargout{1} = handles.output;
handles.dia = dia;
handles.hhmm = hhmm;
handles.lat0 = lat0;
handles.lon0 = lon0;
handles.h = h;
handles.Mw = Mw;
handles.bandera = bandera;
guidata(hObject, handles);

Calcular_Callback(hObject, eventdata, handles);
catalogo_Callback(hObject, eventdata, handles);
%return;

% --- Executes on button press in JASON IGP
function Automatico2_Callback(hObject, eventdata, handles)
% hObject    handle to Automatico (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    structure with handles and user data (see GUIDATA)
clc
bandera = 1;
%url = 'https://cnat.pe/api/adm/earthquake/pre-tsunami'
url = 'https://ide.igp.gob.pe/geoserver/CTS_ultimosismo/ows?service=WFS&version=1.0.0&request=GetFeature&typeName=CTS_ultimosismo%3Aultimo_sismo&maxFeatures=50&outputFormat=application%2Fjson';
%web(url, '-browser');
s = webread(url);

fecha = s.features.properties.fecha_local
dia = fecha(1:2);
hora = s.features.properties.hora_local
hhmm = [hora(1:2),hora(4:5)]; % Corregido 29 Dic 2022
lat0 = s.features.properties.latitud
lat = num2str(lat0);
lon0 = s.features.properties.longitud
lon = num2str(lon0);
h = s.features.properties.profundidad
Mw = s.features.properties.magnitud
Mag = num2str(Mw);

N = length(s);
disp ('Parametros hipocentrales del IGP')
disp (' ')
for k = 1:N-6
    if s(k:k+4) == 'Fecha'
        dia = [s(k+8:k+9)];
        fprintf('%s %s\n', 'Dia =',dia);
    end
    if s(k:k+3) == 'Hora'
        hhmm = [s(k+7:k+8),s(k+9:k+10)];
        fprintf('%s %s\n', 'Hora Origen =',hhmm);
    end
    if s(k:k+5) == 'Latitu'
        lat = s(k+10:k+15);
        lat0 = str2num(lat);
        fprintf('%s %7.2f\n', 'Latitud = ',lat0);        
    end
    if s(k:k+5) == 'Longit'
        lon = s(k+11:k+16);
        lon0 = str2num(lon);
        fprintf('%s %6.2f\n', 'Longitud = ',lon0);  
    end 
    if s(k:k+5) == 'Profun'
        hh = s(k+14:k+18); 
        if hh(3) == 'k'
            h = str2num(hh(1:2));
        else
            h = str2num(hh);
        end
        fprintf('%s %7.0f %s\n', 'Prof = ',h,'km'); 
    end    
    if s(k:k+5) == 'Magnit'
        Mag = s(k+11:k+13);
        Mw = str2num(Mag);
        fprintf('%s %3.1f %s\n', 'Magnitud = ',Mw,'Mw');        
        break
    end
end

set(handles.edit1, 'String', Mag);
set(handles.edit2, 'String', num2str(h));
set(handles.edit3, 'String', lat);
set(handles.edit4, 'String', lon);
set(handles.edit9, 'String', dia);
set(handles.hora,  'String', hhmm);
bandera = 0;

varargout{1} = handles.output;
handles.dia = dia;
handles.hhmm = hhmm;
handles.lat0 = lat0;
handles.lon0 = lon0;
handles.h = h;
handles.Mw = Mw;
handles.bandera = bandera;
guidata(hObject, handles);

Calcular_Callback(hObject, eventdata, handles);
catalogo_Callback(hObject, eventdata, handles);
%return;

% --- Executes on button press in PRO IGP
function Automatico3_Callback(hObject, eventdata, handles)
% hObject    handle to Automatico (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    structure with handles and user data (see GUIDATA)
clc
bandera = 1;
%url = 'https://dev.cnat.pe/api/adm/earthquake/pre-tsunami' %prueba
url = 'https://cnat.pe/api/adm/earthquake/pre-tsunami' % firme
web(url, '-browser');
s = webread(url);
N = length(s);
disp ('Parametros hipocentrales del IGP')
disp (' ')
for k = 1:N-6
    if s(k:k+4) == 'Fecha'
        dia = [s(k+8:k+9)];
        fprintf('%s %s\n', 'Dia =',dia);
    end
    if s(k:k+3) == 'Hora'
        hhmm = [s(k+7:k+8),s(k+9:k+10)];
        fprintf('%s %s\n', 'Hora Origen =',hhmm);
    end
    if s(k:k+5) == 'Latitu'
        lat = s(k+10:k+15);
        lat0 = str2num(lat);
        fprintf('%s %7.2f\n', 'Latitud = ',lat0);        
    end
    if s(k:k+5) == 'Longit'
        lon = s(k+11:k+16);
        lon0 = str2num(lon);
        fprintf('%s %6.2f\n', 'Longitud = ',lon0);  
    end 
    if s(k:k+5) == 'Profun'
        hh = s(k+14:k+18); 
        if hh(3) == 'k'
            h = str2num(hh(1:2));
        else
            h = str2num(hh);
        end
        fprintf('%s %7.0f %s\n', 'Prof = ',h,'km'); 
    end    
    if s(k:k+5) == 'Magnit'
        Mag = s(k+11:k+13);
        Mw = str2num(Mag);
        fprintf('%s %3.1f %s\n', 'Magnitud = ',Mw,'Mw');        
        break
    end
end

set(handles.edit1, 'String', Mag);
set(handles.edit2, 'String', num2str(h));
set(handles.edit3, 'String', lat);
set(handles.edit4, 'String', lon);
set(handles.edit9, 'String', dia);
set(handles.hora,  'String', hhmm);
bandera = 0;

varargout{1} = handles.output;
handles.dia = dia;
handles.hhmm = hhmm;
handles.lat0 = lat0;
handles.lon0 = lon0;
handles.h = h;
handles.Mw = Mw;
handles.bandera = bandera;
guidata(hObject, handles);

Calcular_Callback(hObject, eventdata, handles);
catalogo_Callback(hObject, eventdata, handles);
%return;

function limpiar_Callback(hObject, eventdata, handles)
   clc
   set (handles.edit1, 'String', ' ');
   set (handles.edit2, 'String', ' ');
   set (handles.edit3, 'String', ' ');
   set (handles.edit4, 'String', ' ');
   set (handles.edit9, 'String', ' ');
   set (handles.hora,  'String', ' ');
   tsunami_OutputFcn(hObject, eventdata, handles);
   
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

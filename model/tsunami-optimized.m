% Input parameters: Mw, h, lat0, lon0, hhmm, dia
Mw = 9.0;       % Magnitude
h = 12;         % Depth in km
lat0 = 56;      % Latitude
lon0 = -156;    % Longitude 
hhmm = '0000';  % Time in HHMM format
dia = 23;       % Day

% Adjust longitude if needed
if lon0 > 0 
    lon0 = lon0 - 360;
end

% Load map data
load maper1.mat
lat = A(:,2);
lon = A(:,1);
load maper2.mat;
lat2 = B(:,2);
lon2 = B(:,1);
load maper3.mat;
lat3 = C(:,2);
lon3 = C(:,1);
load pacifico.mat

% Create figure for plotting
figure('Position', [100, 100, 800, 600])

% Plot base map
hold off
pcolor(xa-360, ya, A)
shading flat
hold on
plot(lon, lat, 'b', lon2, lat2, lon3, lat3, 'b')
grid on
axis equal
xlim([-86 -66])
ylim([-19.5 1])
xlabel('Longitud')
ylabel('Latitud')

% Calculate earthquake parameters
L = 10^(0.55*Mw-2.19);  % (km) Papazachos 2004
W = 10^(0.31*Mw-0.63);  % (km)
M0 = 10^(1.5*Mw+9.1);   % Momento sismico (N*m) 
u = 4.5e10;             % (N/m2) coeficiente de rigidez
D = M0/(u*(L*1000)*(W*1000));
S = 10^(0.86*Mw-2.82);  % (km2)
a = 1.11*0.5642*W;  
b = 0.90*0.5642*L;  

% Calculate focal mechanism
A1 = load('mecfoc.dat');
[m, n] = size(A1);
for k = 1:m
    lonm(k) = A1(k,1);
    latm(k) = A1(k,2);
    if lonm(k) > 0 
        lonm(k) = lonm(k)-360;
    end 
    dist(k) = sqrt((lonm(k)-lon0)^2+(latm(k)-lat0)^2);
end 
[minimo, pos] = min(dist);
azimut = A1(pos,3); % strike
echado = 18;        % dip - see line 79

% Calculate rectangle parameters
L1 = L*1000;
W1 = 1000*W*cos(echado*pi/180);
beta = atan(W1/L1)*180/pi;
alfa = azimut - 270;
h1 = sqrt(L1*L1+W1*W1);
a1 = 0.5*h1*sin((alfa+beta)*pi/180)/1000;
b1 = 0.5*h1*cos((alfa+beta)*pi/180)/1000;
xo = lon0+b1/110;
yo = lat0-a1/110;

% Calculate rectangle corners
dip = echado*pi/180; 
a1 = -(azimut-90)*pi/180;
a2 = -(azimut)*pi/180;
r1 = L1/(60*1853);
r2 = W1/(60*1853);
sx = [0, r1*cos(a1), r1*cos(a1)+r2*cos(a2), r2*cos(a2), 0] + xo;
sy = [0, r1*sin(a1), r1*sin(a1)+r2*sin(a2), r2*sin(a2), 0] + yo;

% Clear current plot and redraw
cla
hold on
pcolor(xa-360, ya, A)
shading flat
contour(xa-360, ya, A, [0 0], 'black')
axis equal

% Plot epicenter and fault plane
if Mw < 7.0
    plot(lon0, lat0, 'o')
    zoom on
else
    plot(lon0, lat0, 'o', sx, sy, 'k', 'linewidth', 1)
end

% Add city labels
if lat0 > 0.0 
    text(-79.48, 8.99, 'Panama')
end
text(-80.5876, -03.6337, 'La Cruz')
text(-81.30, -05.082, 'Paita')
text(-79.9423, -06.8396, 'Pimentel')
text(-78.6100, -09.0733, 'Chimbote')
text(-77.615, -11.123, 'Huacho')
text(-77.031, -12.046, 'Lima')
text(-76.22, -13.71, 'Pisco')
text(-75.1567, -15.3433, 'San Juan')
text(-73.61, -16.23, 'Atico')
text(-72.6838, -16.6604, 'Camana')
text(-72.1067, -16.9983, 'Matarani')
text(-70.3232, -18.4758, 'Arica')
if lat0 < -20 
    text(-70.4044, -23.6531, 'Antofagasta')
end

% Add source parameters text
text(lon0+15, lat0-2.0, ['Largo    L  = ', num2str(floor(L)), ' km'])
text(lon0+15, lat0-2.9, ['Ancho    W  = ', num2str(floor(W)), ' km'])
text(lon0+15, lat0-3.8, ['Dislocacion = ', num2str(D, 4), ' m'])
M0_str = num2str(M0/1e21);
if length(M0_str) < 3
    M0_str = [M0_str, '.0'];
end
text(lon0+15, lat0-4.7, ['Mom. sismico= ', M0_str(1:4), 'e21 N.m'])

% Set plot properties
grid on
zoom on
axis equal
xlabel('Longitud')
ylabel('Latitud')
xlim([lon0-10 lon0+10])
ylim([lat0-10 lat0+10])

% Check if epicenter is on land or sea
m = length(lon);
for k = 1:m
    dist(k) = sqrt((lon(k)-lon0)^2+(lat(k)-lat0)^2); % distance epicenter-coast
end 
[minimo, pos] = min(dist);
dist_min = deg2km(minimo);

[long, lati] = meshgrid(xa-360, ya);
h0 = interp2(long, lati, A, lon0, lat0);

% Set title based on conditions
if h0 > 0 && dist_min < 50
    title('El epicentro esta en Tierra, pero podría generar Tsunami')
elseif h0 > 0 && dist_min > 50
    title('El epicentro esta en Tierra. NO genera Tsunami')
    return    
elseif h0 <= 0 
    if Mw >= 7.0 && Mw < 7.9 && h <= 60
        title('Epicentro en el Mar. Probable Tsunami pequeno y local')
    elseif Mw >= 7.9 && Mw < 8.3995 && h <= 60
        title('Epicentro en el Mar. Genera un Tsunami pequeno')
    elseif Mw >= 8.3995 && Mw < 8.8 && h <= 60
        title('Epicentro en el Mar. Genera un Tsunami potencialmente destructivo')
    elseif Mw >= 8.8 && h <= 60
        title('Epicentro en el Mar. Genera un Tsunami grande y destructivo')
    else    
        title('El epicentro esta en el Mar y NO genera Tsunami')
    end
end

% Write parameters to file
fid2 = fopen('hypo.dat', 'w');
fprintf(fid2, '%s\r\n', hhmm);
fprintf(fid2, '%4.2f\r\n', lon0);
fprintf(fid2, '%4.2f\r\n', lat0);
fprintf(fid2, '%3.0f\r\n', h);
fprintf(fid2, '%3.1f\r\n', Mw);
fclose(fid2);

% Prepare the TSDHN run
system('chmod 775 job.run');
system('./job.run');

% This version of the original script is used to generate the log file for the test case
% As such, it is very focused on logging the input parameters and intermediate values and does not do any plotting
% In case you need to run this, move this file to model folder

% Input parameters: Mw, h, lat0, lon0, hhmm, dia
Mw = 9.0;       % Magnitude
h = 12;         % Depth in km
lat0 = 56;      % Latitude
lon0 = -156;    % Longitude 
hhmm = '0000';  % Time in HHMM format
dia = 23;       % Day

% Create log file for testing
log_fid = fopen('tsunami_values.log', 'w');

% Log input parameters
fprintf(log_fid, 'INPUT_PARAMETERS\n');
fprintf(log_fid, 'Mw=%f\n', Mw);
fprintf(log_fid, 'h=%f\n', h);
fprintf(log_fid, 'lat0=%f\n', lat0);
fprintf(log_fid, 'lon0=%f\n', lon0);
fprintf(log_fid, 'hhmm=%s\n', hhmm);
fprintf(log_fid, 'dia=%d\n', dia);

% Adjust longitude if needed
if lon0 > 0 
    lon0 = lon0 - 360;
end
fprintf(log_fid, 'adjusted_lon0=%f\n', lon0);

% Load and log maper1.mat data
fprintf(log_fid, '\nMAPER1_DATA\n');
load maper1.mat
lat = A(:,2);
lon = A(:,1);
fprintf(log_fid, 'First 5 rows of maper1:\n');
for i = 1:min(5,size(A,1))
    fprintf(log_fid, '%f,%f\n', lon(i), lat(i));
end

% Load and log maper2.mat data
fprintf(log_fid, '\nMAPER2_DATA\n');
load maper2.mat
lat2 = B(:,2);
lon2 = B(:,1);
fprintf(log_fid, 'First 5 rows of maper2:\n');
for i = 1:min(5,size(B,1))
    fprintf(log_fid, '%f,%f\n', lon2(i), lat2(i));
end

% Load and log maper3.mat data
fprintf(log_fid, '\nMAPER3_DATA\n');
load maper3.mat
lat3 = C(:,2);
lon3 = C(:,1);
fprintf(log_fid, 'First 5 rows of maper3:\n');
for i = 1:min(5,size(C,1))
    fprintf(log_fid, '%f,%f\n', lon3(i), lat3(i));
end

% Load and log pacifico.mat data
fprintf(log_fid, '\nPACIFICO_DATA\n');
load pacifico.mat
fprintf(log_fid, 'Dimensions: xa=%dx%d, ya=%dx%d, A=%dx%d\n', ...
    size(xa,1), size(xa,2), size(ya,1), size(ya,2), size(A,1), size(A,2));
fprintf(log_fid, 'First 5x5 values of xa,ya,A:\n');
for i = 1:min(5,size(xa,1))
    for j = 1:min(5,size(xa,2))
        fprintf(log_fid, '%f,%f,%f\n', xa(i,j), ya(i,j), A(i,j));
    end
end

% Calculate earthquake parameters
fprintf(log_fid, '\nEARTHQUAKE_PARAMETERS\n');
L = 10^(0.55*Mw-2.19);  % (km) Papazachos 2004
W = 10^(0.31*Mw-0.63);  % (km)
M0 = 10^(1.5*Mw+9.1);   % Momento sismico (N*m) 
u = 4.5e10;             % (N/m2) coeficiente de rigidez
D = M0/(u*(L*1000)*(W*1000));
S = 10^(0.86*Mw-2.82);  % (km2)
a = 1.11*0.5642*W;  
b = 0.90*0.5642*L;  

fprintf(log_fid, 'L=%f\n', L);
fprintf(log_fid, 'W=%f\n', W);
fprintf(log_fid, 'M0=%e\n', M0);
fprintf(log_fid, 'u=%e\n', u);
fprintf(log_fid, 'D=%f\n', D);
fprintf(log_fid, 'S=%f\n', S);
fprintf(log_fid, 'a=%f\n', a);
fprintf(log_fid, 'b=%f\n', b);

% Load and calculate focal mechanism
fprintf(log_fid, '\nMECFOC_DATA\n');
A1 = load('mecfoc.dat');
fprintf(log_fid, 'First 5 rows of mecfoc.dat:\n');
for i = 1:min(5,size(A1,1))
    fprintf(log_fid, '%f,%f,%f\n', A1(i,1), A1(i,2), A1(i,3));
end

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
echado = 18;        % dip

fprintf(log_fid, '\nFOCAL_MECHANISM_CALCULATIONS\n');
fprintf(log_fid, 'azimut=%f\n', azimut);
fprintf(log_fid, 'echado=%f\n', echado);
fprintf(log_fid, 'minimo=%f\n', minimo);
fprintf(log_fid, 'pos=%d\n', pos);

% Calculate rectangle parameters
fprintf(log_fid, '\nRECTANGLE_PARAMETERS\n');
L1 = L*1000;
W1 = 1000*W*cos(echado*pi/180);
beta = atan(W1/L1)*180/pi;
alfa = azimut - 270;
h1 = sqrt(L1*L1+W1*W1);
a1 = 0.5*h1*sin((alfa+beta)*pi/180)/1000;
b1 = 0.5*h1*cos((alfa+beta)*pi/180)/1000;
xo = lon0+b1/110;
yo = lat0-a1/110;

fprintf(log_fid, 'L1=%f\n', L1);
fprintf(log_fid, 'W1=%f\n', W1);
fprintf(log_fid, 'beta=%f\n', beta);
fprintf(log_fid, 'alfa=%f\n', alfa);
fprintf(log_fid, 'h1=%f\n', h1);
fprintf(log_fid, 'a1=%f\n', a1);
fprintf(log_fid, 'b1=%f\n', b1);
fprintf(log_fid, 'xo=%f\n', xo);
fprintf(log_fid, 'yo=%f\n', yo);

% Calculate rectangle corners
dip = echado*pi/180; 
a1 = -(azimut-90)*pi/180;
a2 = -(azimut)*pi/180;
r1 = L1/(60*1853);
r2 = W1/(60*1853);
sx = [0, r1*cos(a1), r1*cos(a1)+r2*cos(a2), r2*cos(a2), 0] + xo;
sy = [0, r1*sin(a1), r1*sin(a1)+r2*sin(a2), r2*sin(a2), 0] + yo;

fprintf(log_fid, '\nRECTANGLE_CORNERS\n');
for i = 1:length(sx)
    fprintf(log_fid, 'corner_%d=%f,%f\n', i, sx(i), sy(i));
end

% Calculate epicenter parameters
m = length(lon);
for k = 1:m
    dist(k) = sqrt((lon(k)-lon0)^2+(lat(k)-lat0)^2);
end 
[minimo, pos] = min(dist);
dist_min = deg2km(minimo);

[long, lati] = meshgrid(xa-360, ya);
h0 = interp2(long, lati, A, lon0, lat0);

fprintf(log_fid, '\nEPICENTER_PARAMETERS\n');
fprintf(log_fid, 'dist_min=%f\n', dist_min);
fprintf(log_fid, 'h0=%f\n', h0);

% Close log file
fclose(log_fid);

% Write parameters to hypo.dat
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
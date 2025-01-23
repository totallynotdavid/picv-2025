VER=ifort
com=-parallel

deform: deform.for
	$(VER) -O deform.for -o deform $(com)
espejo: espejo.f
	$(VER) -O espejo.f -o espejo $(com) 
fault_plane: fault_plane.f90
	$(VER) -O fault_plane.f90 -o fault_plane $(com) 
reporte: reporte.f90
	$(VER) -O reporte.f90 -o reporte 
ttt_max: ttt_max.f90
	$(VER) -O ttt_max.f90 -o ttt_max $(com) 
tsunami: tsunami1.for
	$(VER) -O tsunami1.for -o tsunami $(com) -qopenmp
	

! Cambio de formato de zmax_a.grd para GMT
! Modificado cjimenez 11 Nov 2022

      PARAMETER (IA=2461, JA=2056)
!     PARAMETER (IA=1921, JA=1441)      
      PARAMETER (DX=7412.9951096)
!     PARAMETER (DX=9266.243887)      
      real, dimension(:,:), allocatable:: A, B, C
      real Mw, maximo

      OPEN(2,FILE='meca.dat',STATUS='OLD')
      READ(2,*) xep, yep, zep, Az, echado, rake, Mw
      CLOSE(2)

! Leer archivo zmax 
      allocate (A(IA,JA),B(JA,IA),C(JA,IA))
      OPEN(1,FILE='./zfolder/zmax_a.grd',STATUS='OLD')
      DO I=1,IA
        READ(1,*) (A(I,J),J=1,JA)
      end do
      CLOSE(1)

      B = transpose(A)
      deallocate(A)
      m = size(B,dim=1)
      n = size(B,dim=2)
      do i = 1,m
        do j = 1,n
          k = m-i+1;
          C(i,j) = B(k,j);
        end do
      end do
      deallocate(B)      
! Valor maximo y normalizar
      maximo = maxval(C)
      write(*,*) maximo
      C = 12.0*C/maximo
!      if (Mw<8.0) then
!        C = 1.2*C
!      end if
!      if (Mw>7.5 .and. Mw.le.8.0) then
!        C = 10.0*C/maximo
!      end if
!      if (Mw>8.9) then
!        C = 0.8*C
!      end if
      
      OPEN(2,FILE='maximo.grd')
      write(2,'(a,I7)') 'ncols', IA
      write(2,'(a,I7)') 'nrows', JA
      write(2,'(a,F9.4)') 'xllcorner', 128.027778
!     write(2,'(a,F9.4)') 'xllcorner', 129.958333      
      write(2,'(a,F9.4)') 'yllcorner', -76.005555
!     write(2,'(a,F9.4)') 'yllcorner', -59.958333      
      write(2,'(a,1F10.6)') 'cellsize', DX/1000.0/111.1994
      write(2,'(a)') 'nodata_value -9999'
    
      DO I=1,m
        write(2,'(2000F8.2)') (C(I,J),J=1,n)
      end do
      CLOSE(2)

      write(*,*) 'Se creo el archivo maximo.grd'
      
      end


! Ejecucion del inverse para calculo de ttt
! Modificado cjimenez 25 Ago 2024

      real xep, yep, Mw
      character*6 yep_str
      character(len=23) :: linea

      OPEN(2,FILE='../meca.dat',STATUS='OLD')
      READ(2,*) xep, yep, zep, Az, echado, rake, Mw
      CLOSE(2)
!     write(yep_str,'(f6.2)') yep
!     N = len(yep_str)
!     write(*,*) N

      if (yep<=-10.0) then
        write(*,10) './inverse ',xep,'/',yep
        write(linea,10) './inverse ',xep,'/',yep     
      end if
      if (yep<0.0 .and. yep>-10.0) then
        write(*,20) './inverse ',xep,'/',yep
        write(linea,20) './inverse ',xep,'/',yep     
      end if
      if (yep>0.0 .and. yep<10.0) then
        write(*,30) './inverse ',xep,'/',yep
        write(linea,30) './inverse ',xep,'/',yep     
      end if
      if (yep>=10.0) then
        write(*,20) './inverse ',xep,'/',yep
        write(linea,20) './inverse ',xep,'/',yep     
      end if
10    FORMAT (a10,f6.2,A1,f6.2)      
20    FORMAT (a10,f6.2,A1,f5.2)   
30    FORMAT (a10,f6.2,A1,f4.2)      
      call system(linea)
      
      write(*,*) 'Se ejecutó inverse'
      
      end

c      character*10 string
c      a=3.1416
c      write(string,30)a
c30    format (F10.2)
C     now print your string...
c      print *,string

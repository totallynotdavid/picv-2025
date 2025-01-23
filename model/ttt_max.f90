! 
! Cesar Jimenez 23 Mar 2022
! m n   : dimensiones del archivo green.dat
! Modificado: 23 Mar 2024

PARAMETER (m=1681, n=18)
real :: juan(m), mata(m), iloo(m)
DIMENSION cruz(m),tala(m),pait(m),pime(m),sala(m),chim(m),huar(m),huac(m),cala(m), cerr(m),pisc(m),atic(m),cama(m),aric(m)
dimension tiem(m), big(n-1)
real, dimension(:,:), allocatable:: A
integer i,j,k,pos,ttt1,ttt2,ttt3,ttt4,ttt5,ttt6,ttt7,ttt8,ttt9,ttt10, ttt11,ttt12,ttt13,ttt14,ttt15,ttt16,ttt17
real max01,max02,max03,max04,max05,max06,max07,max08,max09,max10, max11,max12,max13,max14,max15,max16,max17,maxmax

! Leer el archivo green.dat 
 allocate (A(m,n))
 OPEN(1,FILE='./zfolder/green.dat',STATUS='OLD')
 DO I=1,m
   READ(1,*) (A(I,J),J=1,n)
 end do
 CLOSE(1)

do k =1,m
  tiem(k) = A(k,1)
  cruz(k) = A(k,2)
  tala(k) = A(k,3)
  pait(k) = A(k,4)
  pime(k) = A(k,5)
  sala(k) = A(k,6)
  chim(k) = A(k,7)
  huar(k) = A(k,8)
  huac(k) = A(k,9)
  cala(k) = A(k,10)
  cerr(k) = A(k,11)
  pisc(k) = A(k,12)
  juan(k) = A(k,13)
  atic(k) = A(k,14)
  cama(k) = A(k,15)
  mata(k) = A(k,16)
  iloo(k) = A(k,17)
  aric(k) = A(k,18)
end do 
deallocate (A)

! Relacion de Green
 cruz =  (12.9/14.0)**(0.25)*cruz
 tala = (183.1/20.0)**(0.25)*tala
 pait = (50.0/210.0)**(0.25)*pait
 pime =  (26.2/54.0)**(0.25)*pime
 sala = (247.1/24.0)**(0.25)*sala
 chim =  (51.7/28.0)**(0.25)*chim
 huar =  (69.7/14.0)**(0.25)*huar
 huac = (148.9/12.0)**(0.25)*huac
 cala =  (76.0/16.0)**(0.25)*cala
 cerr = (125.4/12.0)**(0.25)*cerr
 pisc =  (25.0/36.0)**(0.25)*pisc
 juan =  (222.2/8.0)**(0.25)*juan
 atic = (163.5/84.0)**(0.25)*atic
 cama = (46.1/350.0)**(0.25)*cama
 mata =(313.4/112.0)**(0.25)*mata
 iloo = (455.9/26.0)**(0.25)*iloo
 aric =  (48.0/10.0)**(0.25)*aric

OPEN(3,FILE='./zfolder/green_rev.dat')
DO k=1,m
  write(3,*) tiem(k)/60.0,tala(k),cala(k),mata(k)
! write(3,*) tiem(k)/60.0,cruz(k),tala(k),pait(k),pime(k),sala(k),chim(k),huar(k),huac(k),cala(k),cerr(k),pisc(k),juan(k),atic(k),cama(k),mata(k),iloo(k),aric(k)
end do
close(3)

DO k=1,m
  if (cruz(k)>0.0) then
    ttt1 = k
    goto 10
  end if
end do

10 continue
DO k=1,m
  if (tala(k)>0.0) then
    ttt2 = k
    goto 20
  end if
end do

20 continue
DO k=1,m
  if (pait(k)>0.0) then
    ttt3 = k
    goto 30
  end if
end do

30 continue
DO k=1,m
  if (pime(k)>0.0) then
    ttt4 = k
    goto 40
  end if
end do

40 continue
DO k=1,m
  if (sala(k)>0.0) then
    ttt5 = k
    goto 50
  end if
end do

50 continue
DO k=1,m
  if (chim(k)>0.0) then
    ttt6 = k
    goto 60
  end if
end do

60 continue
DO k=1,m
  if (huar(k)>0.0) then
    ttt7 = k
    goto 70
  end if
end do

70 continue
DO k=1,m
  if (huac(k)>0.0) then
    ttt8 = k
    goto 80
  end if
end do

80 continue
DO k=1,m
  if (cala(k)>0.0) then
    ttt9 = k
    goto 90
  end if
end do

90 continue
DO k=1,m
  if (cerr(k)>0.0) then
    ttt10 = k
    goto 100
  end if
end do

100 continue
DO k=1,m
  if (pisc(k)>0.0) then
    ttt11 = k
    goto 110
  end if
end do

110 continue
DO k=1,m
  if (juan(k)>0.0) then
    ttt12 = k
    goto 120
  end if
end do

120 continue
DO k=1,m
  if (atic(k)>0.0) then
    ttt13 = k
    goto 130
  end if
end do

130 continue
DO k=1,m
  if (cama(k)>0.0) then
    ttt14 = k
    goto 140
  end if
end do

140 continue
DO k=1,m
  if (mata(k)>0.0) then
    ttt15 = k
    goto 150
  end if
end do

150 continue
DO k=1,m
  if (iloo(k)>0.0) then
    ttt16 = k
    goto 160
  end if
end do

160 continue
DO k=1,m
  if (aric(k)>0.0) then
    ttt17 = k
    goto 170
  end if
end do

170 continue
max01 = maxval(cruz)
max02 = maxval(tala)
max03 = maxval(pait)
max04 = maxval(pime)
max05 = maxval(sala)
max06 = maxval(chim)
max07 = maxval(huar)
max08 = maxval(huac)
max09 = maxval(cala)
max10 = maxval(cerr)
max11 = maxval(pisc)
max12 = maxval(juan)
max13 = maxval(atic)
max14 = maxval(cama)
max15 = maxval(mata)
max16 = maxval(iloo)
max17 = maxval(aric)

big(1) = max01
big(2) = max02
big(3) = max03
big(4) = max04
big(5) = max05
big(6) = max06
big(7) = max07
big(8) = max08
big(9) = max09
big(10)= max10
big(11)= max11
big(12)= max12
big(13)= max13
big(14)= max14
big(15)= max15
big(16)= max16
big(17)= max17

maxmax = maxval(big)
write(*,*) maxmax
  
! Crear archivo ttt_max.dat
 OPEN(2,FILE='ttt_max.dat')
 WRITE(2,200) real(ttt1), max01
 WRITE(2,200) real(ttt2), max02
 WRITE(2,200) real(ttt3), max03
 WRITE(2,200) real(ttt4), max04
 WRITE(2,200) real(ttt5), max05
 WRITE(2,200) real(ttt6), max06
 WRITE(2,200) real(ttt7), max07
 WRITE(2,200) real(ttt8), max08
 WRITE(2,200) real(ttt9), max09
 WRITE(2,200) real(ttt10), max10
 WRITE(2,200) real(ttt11), max11
 WRITE(2,200) real(ttt12), max12
 WRITE(2,200) real(ttt13), max13
 WRITE(2,200) real(ttt14), max14
 WRITE(2,200) real(ttt15), max15
 WRITE(2,200) real(ttt16), max16
 WRITE(2,200) real(ttt17), max17
 close(2)
write(*,*) 'Se creó el archivo ttt_max.dat'
200 format(f6.1 f6.2)

if (maxmax <= 0.1) then
  call system('./mareograma1.csh 0.1')
end if
if (maxmax <= 0.2 .and. maxmax > 0.1) then
  call system('./mareograma1.csh 0.2')
end if
if (maxmax <= 0.6 .and. maxmax > 0.2) then
  call system('./mareograma.csh 0.6')
end if
if (maxmax <= 1.0 .and. maxmax > 0.6) then
  call system('./mareograma.csh 1.0')
end if
if (maxmax <= 2.0 .and. maxmax > 1.0) then
  call system('./mareograma.csh 2.0')
end if
if (maxmax <= 3.0 .and. maxmax > 2.0) then
  call system('./mareograma2.csh 3.0')
end if
if (maxmax <= 4.0 .and. maxmax > 3.0) then
  call system('./mareograma2.csh 4.0')
end if
if (maxmax > 4.0) then
  call system('./mareograma2.csh 5.0')
end if

end


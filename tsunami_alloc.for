C Simulacion de la propagacion del Tsunami para 1 grilla A
C**** EN LAS MALLA "A" SE USAN COORDENADAS ESFERICAS, TEORIA LINEAL
C Modificado por Cesar Jimenez, 22 Abr 2011
C Updated: 01 Mar 2022 se introducen allocated values
c IA,JA          : Dimensiones de la grilla A
c IDS,IDE,JDS,JDE: Posicion relativa de la grilla de deformacion
c DELTA          : Resolucion de la grilla (en grados)
c DT             : Paso de tiempo
c KE             : Numero total de pasos de computo
c KD             : Razon de muestreo del mareograma
c KA             : Separacion entre los snapshops
c NG             : Numero de mareografos virtuales
   
c     PARAMETER(IA=1921, JA=1441)
c     PARAMETER(IDS=1,IDE=300,JDS=1050,JDE=1350)
      PARAMETER(DELTA=240.0/3600.0)
      PARAMETER(DT=3.0)
      PARAMETER(KE=33602,KD=20,KA=300)
      PARAMETER(NG=3)
      PARAMETER(RT=6.37E+6)
c      REAL MA,NA
      CHARACTER PNAME
C  
      DIMENSION IP(NG),JP(NG)
      DIMENSION PNAME(NG),PZ(NG)
      real(4), allocatable :: ZA(:,:,:),MA(:,:,:),NA(:,:,:),ZMXA(:,:)
      real(4), allocatable :: HA(:,:),RXA(:),CJA(:),TMX(:,:),ZMX(:,:)
      real(4), allocatable :: HMA(:,:),HNA(:,:),XXA(:,:),YYA(:,:)
c      COMMON /AXA/ ZA(IA,JA,2),MA(IA,JA,2),NA(IA,JA,2),ZMXA(IA,JA)
c      COMMON /AHA/ HA(IA,JA),RXA(JA),CJA(JA),TMX(IA,JA),ZMX(IA,JA)
c      COMMON /ADA/ HMA(IA,JA),HNA(IA,JA),XXA(IA,JA),YYA(IA,JA)
C    
      call cpu_time(t0)
      OPEN(5,FILE='xyo.dat',STATUS='OLD')
        READ(5,*)IDS,IDE,JDS,JDE,IA,JA
      CLOSE(5)
      allocate(ZA(IA,JA,2),MA(IA,JA,2),NA(IA,JA,2),ZMXA(IA,JA))
      allocate(HA(IA,JA),RXA(JA),CJA(JA),TMX(IA,JA),ZMX(IA,JA))
      allocate(HMA(IA,JA),HNA(IA,JA),XXA(IA,JA),YYA(IA,JA))
      PI=4.0*ATAN(1.0)

C*****INPUT: BLAT = EXTREMO SUR DE LATITUD (EN GRADOS)
      BLATA=-76.006
C
C*****PASO DE MALLA EN RADIANES
      DA=PI*DELTA/180.0
C
      OPEN(1,FILE='./bathy/grid_a.grd')
      OPEN(2,FILE='deform_a.grd')
      OPEN(3,FILE='tidal.dat',STATUS='OLD')
      OPEN(4,FILE='zfolder/green.dat')

C ***** Input Datos de Mareografos *****
C     OPEN(3,FILE='tidal.dat',STATUS='OLD')
      DO IN=1,NG
      READ(3,*)PNAME(IN),IP(IN),JP(IN)
      END DO
      CLOSE(3)

C ********   INPUT GRID    ***********
C
      CALL INPUTA(HA,IA,JA) 
      CALL HMN(IA,JA,HA,HMA,HNA)
      CALL CEROS(IA,JA,ZA,MA,NA)
      CALL DEFORMA(IA,JA,ZA,IDS,IDE,JDS,JDE)
C
C*****CALCULOS PRELIMINARES
C
      CALL PRELIM(IA,JA,RT,DA,DT,HMA,HNA,BLATA,RXA,CJA,XXA,YYA)  
C
C ================= CHECK TIDE GAUGE LOCATION =================

      WRITE(*,'(A49)')
     &'OUTPUT POINT                  (  I,   J  )  DEPTH'
      DO IN=1,NG
      WRITE(*,'(A10,2I6,F9.1)')PNAME(IN),IP(IN),JP(IN),HA(IP(IN),JP(IN))
        IF(HA(IP(IN),JP(IN)).LT.0) THEN
        WRITE(*,*) 'Tidal gauge located on ground'
        END IF
      END DO
      WRITE(*,*)'No tidal gauge locate on ground'

C *********    MAIN CALCULATION    ********** 
C
C     OPEN(4,FILE='zfolder/green.dat')
      DO  10  K = 1 , KE
      KK=K-1
      IF(MOD(K,10).EQ.0) THEN
         WRITE(*,'(A10,I5,A7,I5)')   'Numero  : ',K,'-th de ',KE
      ENDIF       
      CALL MASS(IA,JA,ZA,MA,NA,HA,RXA,CJA)
      CALL BOUT(IA,JA,ZA,MA,NA,HA)
      CALL MMNT(IA,JA,ZA,MA,NA,HA,XXA,YYA)

      IF(MOD(KK,KD).EQ.0) THEN
      DO KG=1,NG
         PZ(KG)=ZA(IP(KG),JP(KG),2)
      END DO
      WRITE(4,'(F7.1,100F7.3)')KK*DT/60.0,(PZ(KG),KG=1,NG)
C        
            CALL ZMAX(IA,JA,ZA,ZMXA)
            CALL TMAX(IA,JA,TMX,ZMX,ZA,KK,DT)

            ELSE
            ENDIF
		  
            IF(MOD(KK,KA).EQ.0) THEN
c           CALL MOVIE(KK,KA,IA,JA,ZA)

            ELSE
            ENDIF 

      CALL CHAN(IA,JA,ZA,MA,NA)

10    CONTINUE
      CLOSE(4)

C      OPEN(5,FILE='zfolder/tmax_a.grd')
C      DO 20 I=1,IA
C20	WRITE(5,50) (TMX(I,J),J=1,JA)
C      CLOSE(5)
C
      OPEN(6,FILE='zfolder/zmax_a.grd')
      DO I=1,IA
	WRITE(6,50) (ZMXA(I,J),J=1,JA)
      end do
      CLOSE(6)
C
50	FORMAT(4000F8.3)
C Fin solo inversion
      call cpu_time(tf)
      write(*,*) t0, tf
      write(*,666)'Tiempo de corrida= ',(tf-t0)/60,' min'
666   format (A20,F6.2,A5) 
      STOP
      END
C***** DE AQUI EN DELANTE NO ALTERAR
C*******************************************************
C*******************************************************
C*******************************************************
C*******************************************************
C**** SE LEEN LA BATIMETRIA DEL DOMINIO A
      SUBROUTINE INPUTA(HA,IA,JA) 
      DIMENSION HA(IA,JA)
      
C     OPEN(1,FILE='grid_a.grd')
      DO 10 I=1,IA
10    READ(1,*) (HA(I,J),J=1,JA)
      CLOSE(1)

      DO 20 J=1,JA
      DO 20 I=1,IA
20    IF(HA(I,J).GT.0.0.AND.HA(I,J).LT.10.0) HA(I,J)=10.0
        
      RETURN
      END
C
C*****SE LEE LA DEFORMACION O CONDICION INICIAL
C
      SUBROUTINE DEFORMA(IA,JA,Z,IDS,IDE,JDS,JDE)
      DIMENSION Z(IA,JA,2)
   
C     OPEN(2,FILE='deform_a.grd')
      DO 10 I=IDS,IDE
10    READ(2,*) (Z(I,J,1),J=JDS,JDE)
      CLOSE(2)

      RETURN
      END
C
C*****MOM (MAXIMUM OF MAXIMUM)
C
	SUBROUTINE ZMAX(II,JJ,Z,ZMX)

      DIMENSION Z(II,JJ,2),ZMX(II,JJ)

      DO 10 J=1,JJ
      DO 10 I=1,II
10    IF(Z(I,J,2).GT.ZMX(I,J)) ZMX(I,J)=Z(I,J,2)

      RETURN
      END
C
C************** Tsunami Travel Time Matrix   **********************************
C
      SUBROUTINE TMAX(IA,JA,TMX,ZMX,Z,KK,DT)
C     TMX = travel time matrix (minutes)
      DIMENSION Z(IA,JA,2),ZMX(IA,JA)
      DIMENSION TMX(IA,JA)
      
      DO 10 J=2,JA
      DO 10 I=2,IA

        IF (ZMX(I,J).GT.0.9)  GO TO 10

        IF(  Z(I,J,2) .GT. 0.005) THEN
        ZMX(I,J)=1.0
        TMX(I,J)=FLOAT(KK)*DT/60.0

        ELSE
        ENDIF

10    CONTINUE

      RETURN
      END
C
C**** WRITE TSUNAMI FRAMES AT "KA" TIME STEPS
C
      SUBROUTINE MOVIE(KK,KA,IA,JA,ZA)
 	DIMENSION ZA(IA,JA,2)
    	CHARACTER NAME*50

      KT=KK/KA
   	WRITE(NAME,100) KT + 1000
100   FORMAT('zfolder/z',I4)    
      OPEN(7,FILE=NAME)
	DO 10 I=1,IA
10    WRITE(7,22) (ZA(I,J,2),J=1,JA)
      CLOSE(7)
22	FORMAT(4000F9.2)

	RETURN
      END	   
C
C****CALCULOS PRELIMINARES PARA CONSERVACION DE MASA Y MOMENTO 
C    RZ=LATITUD EN NODOS DE ELEVACION
C    RN=LATITUD EN NODOS DE VELOCIDAD MERIDIONAL
C    RT=RADIO DE LA TIERRA
C    RX=FACTOR EN CONSERVACION DE MASA
C    CJ=FACTOR EN CONSERVACION DE MASA
C    XX=FACTOR EN CONSERVACION DE MOMENTO LONGITUDINAL
C    YY=FACTOR EN CONSERVACION DE MOMENTO MERIDIONAL
C    DY=PASO DE MAYA EN RADIANES
C    DT=PASO DE TIEMPO EN SEGUNDOS
C    BLAT=EXTREMO SUR DE LATITUD EN GRADOS (+N, -S)
      SUBROUTINE PRELIM(IA,JA,RT,DY,DT,HM,HN,BLAT,RX,CJ,XX,YY) 
      DIMENSION  RX(JA),CJ(JA),HM(IA,JA),HN(IA,JA)
      DIMENSION  XX(IA,JA),YY(IA,JA)

      PI=4.0*ATAN(1.0)
      GG=9.8

	RZ=BLAT*PI/180.0
	RN=RZ+DY/2.0

      DO 30 J=1,JA
	RX(J)=DT/(RT*COS(RZ)*DY)
	CJ(J)=COS(RN)
      RZ=RZ + DY
      RN=RN + DY
30    CONTINUE

	DO 40 J=1,JA
	DO 40 I=1,IA
	XX(I,J)=RX(J)*GG*HM(I,J)
	YY(I,J)=DT*GG*HN(I,J)/(RT*DY)
40    CONTINUE

      RETURN
      END
C*****
C*****SE CALCULAN LAS PROFUNDIDADES EN LOS PUNTOS EN DONDE SE EVALUAN
C*****LAS DESCARGAS.

      SUBROUTINE HMN(IF,JF,HZ,HM,HN)
 
      DIMENSION HZ(IF,JF),HM(IF,JF),HN(IF,JF)
 
      DO 10 J=1,JF
        DO 10 I=1,IF
          IF(I.EQ.IF) GO TO 11
          HH=0.5*(HZ(I,J)+HZ(I+1,J))
       
          HM(I,J)=HH
          GO TO 12
11        HM(I,J)=HZ(I,J)
12        IF(J.EQ.JF) GO TO 13
          HH=0.5*(HZ(I,J)+HZ(I,J+1))
 
          HN(I,J)=HH
          GO TO 10
13        HN(I,J)=HZ(I,J)
10    CONTINUE
 
      RETURN
      END      
C
C*****CONSERVACION DE MASA EN ESFERICAS (LINEAL)
C
      SUBROUTINE MASS(IA,JA,Z,M,N,H,RX,CJ)

      REAL M,N
      DIMENSION Z(IA,JA,2),M(IA,JA,2),N(IA,JA,2),H(IA,JA)
      DIMENSION RX(JA),CJ(JA)

      DO 10 J=2,JA
        DO 10 I=2,IA
          IF(H(I,J).GT.0.0)THEN 
          Z(I,J,2)=Z(I,J,1)-RX(J)*( M(I,J,1)-M(I-1,J,1) )
     &  -RX(J)*( N(I,J,1)*CJ(J) - N(I,J-1,1)*CJ(J-1) )
          IF(ABS(Z(I,J,2)).LT.1.0E-5) Z(I,J,2)=0.0
          ELSE
            Z(I,J,2)=0.0
          ENDIF
   10 CONTINUE 
      RETURN
      END 
C
C***** CONSERVACION DE MOMENTO LINEAL EN ESFERICAS (SIN FRICCION)
C
      SUBROUTINE MMNT(IA,JA,Z,M,N,H,XX,YY)
	           
      REAL M,N     
      DIMENSION Z(IA,JA,2),M(IA,JA,2),N(IA,JA,2)
      DIMENSION H(IA,JA)
      DIMENSION XX(IA,JA),YY(IA,JA)

      DO 10 J=2,JA
        DO 10 I=2,IA-1        
        IF(H(I,J).GT.0.0.AND.H(I+1,J).GT.0.0)THEN
        M(I,J,2)=M(I,J,1)-XX(I,J)*( Z(I+1,J,2)-Z(I,J,2) )
          IF(ABS(M(I,J,2)).LT.1.0E-5) M(I,J,2)=0.0
          ELSE
            M(I,J,2)=0.0
          ENDIF
   10 CONTINUE
      
      DO 20 J=2,JA-1
        DO 20 I=2,IA
        IF(H(I,J).GT.0.0.AND.H(I,J+1).GT.0.0) THEN      
        N(I,J,2)=N(I,J,1)-YY(I,J)*(Z(I,J+1,2)-Z(I,J,2))
          IF(ABS(N(I,J,2)).LT.1.0E-5) N(I,J,2)=0.0
          ELSE
            N(I,J,2)=0.0
          ENDIF

   20 CONTINUE
      RETURN
      END
C
C**** CONDICIONES DE FRONTERA ABIERTA EN EL DOMINIO "A"

      SUBROUTINE BOUT(IA,JA,ZA,MA,NA,HA)

      REAL MA,NA
      DIMENSION ZA(IA,JA,2),MA(IA,JA,2),NA(IA,JA,2),HA(IA,JA)
 
      DO 10 KK=1,2
        J=2
        IF(KK.EQ.2)J=JA
        DO 10 I=2,IA-1
          IF(HA(I,J).LT.0.0)GOTO 10
          CC=SQRT(9.8*HA(I,J))
          UU=0.5*ABS(MA(I,J,2)+MA(I-1,J,2))
          IF(J.EQ.2)UU=SQRT(UU**2+NA(I,J,2)**2)
          IF(J.EQ.JA)UU=SQRT(UU**2+NA(I,J-1,2)**2)
          ZZ=UU/CC
          IF(J.EQ.2.AND.NA(I,J,2).GT.0.0)ZZ=-ZZ
          IF(J.EQ.JA.AND.NA(I,J-1,2).LT.0.0)ZZ=-ZZ
          ZA(I,J,2)=ZZ
   10 CONTINUE
      DO 20 KK=1,2
        I=2
        IF(KK.EQ.2)I=IA
        DO 20 J=2,JA-1
          IF(HA(I,J).LT.0.0)GOTO 20
          CC=SQRT(9.8*HA(I,J))
          UU=0.5*ABS(NA(I,J,2)+NA(I,J-1,2))
          IF(I.EQ.2)UU=SQRT(UU**2+MA(I,J,2)**2)
          IF(I.EQ.IA)UU=SQRT(UU**2+MA(I-1,J,2)**2)
          ZZ=UU/CC
          IF(I.EQ.2.AND.MA(I,J,2).GT.0.0)ZZ=-ZZ
          IF(I.EQ.IA.AND.MA(I-1,J,2).LT.0.0)ZZ=-ZZ
          ZA(I,J,2)=ZZ
   20 CONTINUE
 
      RETURN
      END
C****
C
      SUBROUTINE JNQ(IX,JX,IY,JY,MX,NX,MY,NY,HY,L0,BCHK)
C
      INTEGER BCHK,CHK
      REAL MX,NX,MY,NY
      DIMENSION MX(IX,JX,2),NX(IX,JX,2),HY(IY,JY)
      DIMENSION MY(IY,JY,2),NY(IY,JY,2),L0(4)
      ISS=2 
      JSS=2 
      IES=IY 
      JES=JY 
      ISL=L0(1) 
      JSL=L0(2)
      IEL=L0(3) 
      JEL=L0(4)
      CHK=BCHK
      KB=CHK/1000
      IF(KB.EQ.1)THEN
        CHK=CHK-1000
        I=ISS 
        J=JSS-1 
       II=ISL-1  
       JJ=JSL-1
        DO WHILE(I.LE.IES)
          SI=(I-ISS+2)/3.0
          IS=IFIX(SI) 
          DI=SI-IS 
          II=IS+ISL-1
          NY(I,J,2)=(1-DI)*NX(II,JJ,2)+DI*NX(II+1,JJ,2)
          IF(HY(I,J+1).LT.0.0)NY(I,J,2)=0.0
          I=I+1
        ENDDO
      ENDIF
C
      KB=CHK/100
      IF(KB.EQ.1)THEN
        CHK=CHK-100
        I=IES 
        J=JSS
       II=IEL 
       JJ=JSL-1
        DO WHILE(J.LE.JES)
          SJ=(J-JSS+2)/3.0
          JS=IFIX(SJ) 
          DJ=SJ-JS  
          JJ=JS+JSL-1
          MY(I,J,2)=(1-DJ)*MX(II,JJ,2)+DJ*MX(II,JJ+1,2)
          IF(HY(I,J).LT.0.0)MY(I,J,2)=0.0
          J=J+1
        ENDDO
      ENDIF
C
      KB=CHK/10
      IF(KB.EQ.1)THEN
        CHK=CHK-10
        I=ISS 
        J=JES 
       II=ISL-1 
       JJ=JEL
        DO WHILE(I.LE.IES)
          SI=(I-ISS+2)/3.0
          IS=IFIX(SI) 
          DI=SI-IS 
          II=IS+ISL-1
          NY(I,J,2)=(1-DI)*NX(II,JJ,2)+DI*NX(II+1,JJ,2)
          IF(HY(I,J).LT.0.0)NY(I,J,2)=0.0
          I=I+1
        ENDDO
      ENDIF
C
      IF(CHK.EQ.1)THEN
        I=ISS-1 
        J=JSS  
       II=ISL-1 
       JJ=JSL-1
        DO WHILE(J.LE.JES)
          SJ=(J-JSS+2)/3.0
          JS=IFIX(SJ) 
          DJ=SJ-JS 
          JJ=JS+JSL-1
          MY(I,J,2)=(1-DJ)*MX(II,JJ,2)+DJ*MX(II,JJ+1,2)
          IF(HY(I+1,J).LT.0.0)MY(I,J,2)=0.0
          J=J+1
        ENDDO
      ENDIF
      RETURN
      END
C
      SUBROUTINE CHAN(IF,JF,Z,M,N)
C
      REAL M,N
      DIMENSION Z(IF,JF,2),M(IF,JF,2),N(IF,JF,2)
      DO 10 J=1,JF
      DO 10 I=1,IF
      Z(I,J,1) = Z(I,J,2)
      M(I,J,1) = M(I,J,2)
      N(I,J,1) = N(I,J,2)
10    CONTINUE
      RETURN
      END
C
      SUBROUTINE CEROS(IF,JF,Z,M,N)
C
      REAL M,N
      DIMENSION Z(IF,JF,2),M(IF,JF,2),N(IF,JF,2)
        
      DO 100 L=1,2
      DO 10 J=1,JF
      DO 10 I=1,IF
      Z(I,J,L)=0.0 
      M(I,J,L)=0.0 
      N(I,J,L)=0.0           
10    CONTINUE 
100   CONTINUE
      RETURN
      END
C

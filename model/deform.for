C**** PROGRAMA PARA DEFORMAR EL DOMINIO "A" DADOS LOS PARAMETROS DE LA
C**** DISLOCACION. SE UTILIZA LA TEORIA DE L. Mansinha y D.E. Smylie
C**** Modificado: Cesar Jimenez 03 Set 2011

c.... Este programa solo se corre para el dominio exterior. Los
c...  resultados son utilizados por otro programa (INTERP??.FOR)
c...  para interpolar en los subdominios B, C, D, etc. Cuando se
c...  intepola de A a B seria INTERPAB.FOR, cuando se interpola de
c...  Ba C seria INTERPBC.FOR, y etc.

C     PARAMETROS DE ENTRADA:
C     I0; ORIGEN DE LA FALLA EN LAS COORDENADAS DE LA REJILLA
C     J0; ORIGEN DE LA FALLA
C     D0; DISLOCACION DE LA FALLA (m) (SLIP MAGNITUDE)
C     L0; LONGITUD DE LA FALLA    (m) (LENGTH)
C     W0; ANCHO DE LA FALLA       (m) (WIDTH)
C     TH; RUMBO DE LA FALLA  (grados) (STRIKE)
C     DL; ECHADO DE LA FALLA (grados) (DIP ANGLE)
C     RD; ANGULO DE DESPLAZAMIENTO SOBRE EL PLANO DE LA  FALLA (grados,
C         sitema de referencia sobre el plano inferior de la falla )
C         (SLIP DIRECTION RELATIVE TO THE STRIKE)
C     HH; PROFUNDIDAD DE LA FALLA (m) (parte superior de la misma)

      REAL L0
c... A = DOMINIO EXTERIOR
c... IA = NUMERO DE FILAS DE LA MATRIZ A LO LARGO DEL EJE DE X
c... JA = NUMERO DE COLUMNAS DE LA MATRIZ A LO LARGO DEL EJE DE Y
c... DA = TAMANO DE LA REJILLA A LO LARGO DE LOS EJES X, Y (en metro)
c... IDS,IDE = limites en el eje X de la grilla de deformacion
c... JDS,JDE = limites de el eje Y de la grilla de deformacion
c...
c     PARAMETER (IDS=1,IDE=500,JDS=1,JDE=500)
c     PARAMETER (IA=IDE-IDS+1, JA=JDE-JDS+1, DA=30.0*1853.0/60.0)
      PARAMETER (DA=240.0*1853.0/60.0)

c...  ZA(IA,JA) = condicion inicial en la superficie del mar
      real(4), allocatable :: ZA(:,:)
c     DIMENSION ZA(IA,JA)
      OPEN(1,FILE='xyo.dat',STATUS='OLD')
        READ(1,*)IDS,IDE,JDS,JDE
      CLOSE(1)
      IA=IDE-IDS+1
      JA=JDE-JDS+1
      allocate(ZA(IA,JA))
      
      OPEN(2,FILE='pfalla.inp',STATUS='OLD')
      READ(2,*)I0,J0,D0,L0,W0,TH,DL,RD,HH
        IF (ST.EQ.0.0) ST=ST+0.001
        IF (ST.EQ.360.0) ST=ST+0.001
      CLOSE(2)
      I0 = I0 - IDS + 1
      J0 = J0 - JDS + 1
C*****************************************************************
C*****************************************************************
C...  Inicializando a cero
         CALL CEROS(IA,JA,ZA)
C...  Calcula la deformacion
         RD = 180.0 - RD
         CALL DEFORM(IA,JA,ZA,I0,J0,D0,L0,W0,TH,DL,RD,HH,DA)
C...  escribe en el disco la condicion inicial de la superficie del mar
         CALL OUTPUT(IA,JA,ZA)

      STOP
      END

      SUBROUTINE OUTPUT(IF,JF,Z)

      DIMENSION Z(IF,JF)
C En la siguiente linea se introduce el nombre del archivo de salida

      DO J=1,JF
      DO I=1,IF
        IF(ABS(Z(I,J)).LT.0.02) Z(I,J)=0.0
      end do
      end do

      OPEN(2,FILE='deform_a.grd')
      DO I=1,IF
        WRITE(2,22) (Z(I,J),J=1,JF)
      end do
      CLOSE(2)
22    FORMAT(4000F9.3)
      RETURN
      END
C*****  De aqui en adelante no cambiar nada
C*****************************************************************
C*****************************************************************
C*****************************************************************

      SUBROUTINE CEROS(IF,JF,Z)
C
      DIMENSION Z(IF,JF)

      DO J=1,JF
      DO I=1,IF
         Z(I,J)=0.0
      end do
      end do
      RETURN
      END

      SUBROUTINE DEFORM(IF,JF,Z,I0,J0,D,L,W,TH,DL
     & ,RD,HH,DX)
      REAL L
      PARAMETER(A=3.141592,B=4.848E-06)
      PARAMETER(RR=6.37E+6,E=1.7453E-2)
      DIMENSION Z(IF,JF)

C      XL=A*RR*(X0-XO)*COS(E*YO)/180.0
C      YL=A*RR*(Y0-YO)/180.0
      XL=DX*(I0-1)
      YL=DX*(J0-1)
      H1=HH/SIN(E*DL)
      H2=HH/SIN(E*DL)+W
      DS=D*COS(E*RD)
      DD=D*SIN(E*RD)
C      WRITE(6,*)XL,YL,H1,H2,DS,DD
      DO J=1,JF
        DO I=1,IF
          XX=DX*(I-1)
          YY=DX*(J-1)
C         YY=A*RR*DR*(J-1)/(60.0*180)
C         XX=A*RR*DR*(I-1)*COS(E*(YO+DR*(J-1)/60.0))/(60.0*180)
          X1=(XX-XL)*SIN(E*TH)+(YY-YL)*COS(E*TH)
          X2=(XX-XL)*COS(E*TH)-(YY-YL)*SIN(E*TH)+HH/TAN(E*DL)
          X3=0.0
          CALL USCAL(X1,X2,X3,L,H2,E*DL,F1)
          CALL USCAL(X1,X2,X3,L,H1,E*DL,F2)
          CALL USCAL(X1,X2,X3,0.,H2,E*DL,F3)
          CALL USCAL(X1,X2,X3,0.,H1,E*DL,F4)
          CALL UDCAL(X1,X2,X3,L,H2,E*DL,G1)
          CALL UDCAL(X1,X2,X3,L,H1,E*DL,G2)
          CALL UDCAL(X1,X2,X3,0.,H2,E*DL,G3)
          CALL UDCAL(X1,X2,X3,0.,H1,E*DL,G4)
          US=(F1-F2-F3+F4)*DS/(12.0*A)
          UD=(G1-G2-G3+G4)*DD/(12.0*A)
          Z(I,J)=US+UD
        end do
      end do
      RETURN
      END
C
      SUBROUTINE USCAL(X1,X2,X3,C,CC,DP,F)
      REAL K
C
      SN=SIN(DP)
      CS=COS(DP)
      C1=C
      C2=CC*CS
      C3=CC*SN
      R=SQRT((X1-C1)**2+(X2-C2)**2+(X3-C3)**2)
      Q=SQRT((X1-C1)**2+(X2-C2)**2+(X3+C3)**2)
      R2=X2*SN-X3*CS
      R3=X2*CS+X3*SN
      Q2=X2*SN+X3*CS
      Q3=-X2*CS+X3*SN
      H=SQRT(Q2**2+(Q3+CC)**2)
      K=SQRT((X1-C1)**2+Q2**2)
      A1=LOG(R+R3-CC)
      A2=LOG(Q+Q3+CC)
      A3=LOG(Q+X3+C3)
      B1=1+3.0*(TAN(DP))**2
      B2=3.0*TAN(DP)/CS
      B3=2.0*R2*SN
      B4=Q2+X2*SN
      B5=2.0*R2**2*CS
      B6=R*(R+R3-CC)
      B7=4.0*Q2*X3*SN**2
      B8=2.0*(Q2+X2*SN)*(X3+Q3*SN)
      B9=Q*(Q+Q3+CC)
      B10=4.0*Q2*X3*SN
      B11=(X3+C3)-Q3*SN
      B12=4.0*Q2**2*Q3*X3*CS*SN
      B13=2.0*Q+Q3+CC
      B14=Q**3*(Q+Q3+CC)**2
      F=CS*(A1+B1*A2-B2*A3)+B3/R+2*SN*B4/Q-B5/B6+(B7-B8)/B9+B10*B11/
     &  Q**3-B12*B13/B14
      RETURN
      END
C
      SUBROUTINE UDCAL(X1,X2,X3,C,CC,DP,F)
      REAL K
C
      SN=SIN(DP)
      CS=COS(DP)
      C1=C
      C2=CC*CS
      C3=CC*SN
      R=SQRT((X1-C1)**2+(X2-C2)**2+(X3-C3)**2)
      Q=SQRT((X1-C1)**2+(X2-C2)**2+(X3+C3)**2)
      R2=X2*SN-X3*CS
      R3=X2*CS+X3*SN
      Q2=X2*SN+X3*CS
      Q3=-X2*CS+X3*SN
      H=SQRT(Q2**2+(Q3+CC)**2)
      K=SQRT((X1-C1)**2+Q2**2)
      A1=LOG(R+X1-C1)
      A2=LOG(Q+X1-C1)
      B1=Q*(Q+X1-C1)
      B2=R*(R+X1-C1)
      B3=Q*(Q+Q3+CC)
      D1=X1-C1
      D2=X2-C2
      D3=X3-C3
      D4=X3+C3
      D5=R3-CC
      D6=Q3+CC
      T1=ATN(D1*D2,(H+D4)*(Q+H))
      T2=ATN(D1*D5,R2*R)
      T3=ATN(D1*D6,Q2*Q)
      F=SN*(D2*(2*D3/B2+4*D3/B1-4*C3*X3*D4*(2*Q+D1)/(B1**2*Q))
     &  -6*T1+3*T2-6*T3)+CS*(A1-A2-2*(D3**2)/B2-4*(D4**2-C3*X3)/
     &  B1-4*C3*X3*D4**2*(2*Q+X1-C1)/(B1**2*Q))+6*X3*(CS*SN*(2*D6/B1+D1/
     &  B3)-Q2*(SN**2-CS**2)/B1)
      RETURN
      END
C
      REAL FUNCTION ATN(AX,AY)
      DATA GX/1.0E-6/
      AAX=ABS(AX)
      AAY=ABS(AY)
      P=AX*AY
      IF(AAX.LE.GX.AND.AAY.LE.GX)GOTO 10
      SR=ATAN2(AAX,AAY)
      ATN=SIGN(SR,P)
      RETURN
   10 WRITE(6,100)AX,AY
  100 FORMAT(1H ,"ATAN --    AX=",E15.7,2X,"AY=",E15.7)
      ATN=0.2
      RETURN
      END

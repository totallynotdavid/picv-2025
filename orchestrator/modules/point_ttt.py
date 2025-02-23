import subprocess
import os

def generate_ttt_map():
    # Set parameters
    region = "120.0/300.0/-65.0/61.0"
    size = "M16c"
    axis = "a20f10WsNe"
    grdfile = "cortado.i2"
    cptfile = "color.cpt"
    tttbfile = "ttt.b"
    psfile = "ttt.ps"
    cmtfile = "../meca.dat"

    # Set GMT defaults
    subprocess.run(["gmt", "set", "MAP_FRAME_TYPE=plain"])
    subprocess.run(["gmt", "set", "FONT_ANNOT_PRIMARY=9p"])
    subprocess.run(["gmt", "set", "FONT_LABEL=9p"])
    subprocess.run(["gmt", "set", "FONT_TITLE=9p"])
    subprocess.run(["gmt", "set", "PS_MEDIA=A4"])

    # Create color palette
    with open(cptfile, "w") as f:
        subprocess.run(["gmt", "makecpt", "-Cglobe", "-Z"], stdout=f)

    # Start building the PostScript file
    with open(psfile, "w") as ps:
        # Grid image
        subprocess.run([
            "gmt", "grdimage", f"{grdfile}=bs",
            "-R"+region, "-J"+size,
            "-C"+cptfile, "-K", "-P"
        ], stdout=ps)

        # Coastlines
        subprocess.run([
            "gmt", "pscoast",
            "-R"+region, "-J"+size,
            "-B"+axis, "-Dl", "-N1",
            "-W0.5,30", "-Ggray", "-P", "-O", "-K"
        ], stdout=ps)

        # Contours
        subprocess.run([
            "gmt", "grdcontour", f"{tttbfile}=bf",
            "-R"+region, "-J"+size,
            "-C1", "-A1.f1+uh",
            "-Wc1.,30,-", "-Wa1.,30,-",
            "-K", "-O", "-P", "-V"
        ], stdout=ps)

        # Focal mechanisms
        subprocess.run([
            "gmt", "psmeca", cmtfile,
            "-R"+region, "-J"+size,
            "-Sa0.29c", "-G0/0/0", "-P", "-O", "-V", "-K"
        ], stdout=ps)

    # Finalize PS file and convert to EPS
    subprocess.run(["ps2eps", "-f", psfile])
    os.remove(psfile)
